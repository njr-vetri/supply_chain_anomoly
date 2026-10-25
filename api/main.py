"""FastAPI interface over the local repository; actions remain dry-run only."""
from __future__ import annotations

import json
import hashlib
import os
import re
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Annotated, Any, Generic, Literal, TypeVar

import math
import numpy as np
import pandas as pd

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Path as PathParam, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
import networkx as nx
import stat

from src.data import dataset_service
from src.data.onboarding import profile_uploaded_file, json_record_chunks, safe_member_name
from src.data.profile import DatasetProfile, detect_capabilities
from src.data.schema_mapper import suggest_mappings

from src.core.audit import AuditLog
from src.core.config import load_settings
from src.core.repository import (
    ActionRow, AnomalyRow, ApiKeyRow, ApprovalRow, AuditEventRow, CompanyRow, CompanySettingRow,
    DataSourceRow, DatasetVersionRow, EvidenceRow,
    HypothesisRow, ImportJobRow, IncidentRow, MappingVersionRow, ModelVersionRow, OutcomeRow,
    PipelineRunRow, PredictionRow, ProjectRow, QualitySnapshotRow, RecommendationRow, RelationshipProposalRow, RiskScoringConfigRow,
    Repository, UserRow, WorkspaceRow,
)
from src.security.auth import (
    create_access_token, decode_access_token, generate_machine_api_key,
    generate_temp_password, hash_password, verify_password,
    ROLE_LEVELS, PERMISSIONS, MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES,
)
from src.workflow.scheduler import scheduler
from src.core.schemas import (
    Action, Approval, AuditEvent, Evidence, Hypothesis, Incident,
    ModelVersion, Outcome, Prediction, HypothesisStatus,
)
from src.risk.hypotheses import HypothesisCase, HypothesisService, EvidenceLedger, LedgerEvidence
from src.core.capabilities import assess_capabilities
from src.core.generic_pipeline import preview_pipeline, run_canonical_pipeline
from src.data.generic_validation import RuleConfig
from src.risk.incident_assembly import assemble_incident
from src.risk.drivers import analyze_drivers
from src.network.canonical_graph import build_canonical_graph, downstream_trace, upstream_trace, graph_analytics
from src.network.aggregated_graph import build_aggregated_supply_network, trace_aggregated_network
from src.risk.scoring import CompanyRiskConfig, score_company_risk
from src.recommendations.playbooks import recommend_for_driver
from src.recommendations.whatif import compare_scenarios
from src.workflow.outcomes import record_execution_verification, record_observed_outcome
from src.monitoring.outcomes import evaluate_company_outcomes, evaluate_repository_alerts
from src.ml.registry import compare_candidate, promote_candidate, rollback_model, set_initial_current
from src.alerts.manager import AlertManager
from src.connectors.folder import FolderImportConnector
from src.connectors.rest import RestPollingConnector
from src.connectors.database import DatabaseImportConnector
from src.connectors.notifications import SMTPNotificationAdapter, WebhookNotificationAdapter
from src.connectors.extensions import UNBUILT_CONNECTOR_EXTENSIONS
from src.data.data_quality import compute_dataset_quality_report, compute_project_quality_report

T = TypeVar("T")
ROLES = {"viewer": 1, "analyst": 2, "reviewer": 3, "admin": 4}
load_dotenv()


def _sanitize_for_json(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        try:
            return _sanitize_for_json(obj.item())
        except Exception:
            return str(obj)
    if hasattr(obj, "tolist") and callable(getattr(obj, "tolist")):
        try:
            return _sanitize_for_json(obj.tolist())
        except Exception:
            return str(obj)
    return obj


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class Page(BaseModel, Generic[T]):
    items: list[T]
    count: int


class IncidentDetail(Incident):
    evidence: list[Evidence] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    explanation: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class QualityItem(BaseModel):
    source: str
    observed_at: datetime
    row_count: int
    null_rates: dict[str, float]
    drift: dict[str, Any]
    fresh: bool


class HypothesisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: Annotated[str, Field(min_length=1, max_length=128)]
    statement: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=200)
    record_refs: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(default_factory=list, max_length=100)


class HypothesisReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: HypothesisStatus
    rationale: str = Field(min_length=1, max_length=2000)


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rationale: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)

    @property
    def effective_rationale(self) -> str:
        val = (self.rationale or self.reason or "").strip()
        if not val:
            return "Decision confirmed by reviewer"
        return val


class ApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendation_id: Annotated[str, Field(min_length=1, max_length=128)]


class ActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendation_id: Annotated[str, Field(min_length=1, max_length=128)]
    action_class: str = Field(pattern="^(READ_ONLY|LOW_IMPACT_REVERSIBLE|HIGH_IMPACT)$")
    approval_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class KillSwitchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)


class PipelineDryRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    datasets: list[Literal["olist", "dataco", "online_retail_ii"]] = Field(
        default_factory=lambda: ["olist", "dataco", "online_retail_ii"], min_length=1, max_length=3)


class DryRunResult(BaseModel):
    status: str = "DRY_RUN"
    executed: bool = False
    message: str
    datasets: list[str] = Field(default_factory=list)
    kill_switch: bool = False


class DatasetMappingConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mappings: dict[str, str]
    description: str = Field(default="", max_length=1000)


class MappingVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mappings: dict[str, str]
    custom_fields: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    time_zone: str | None = Field(default=None, max_length=100)
    date_format: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except Exception as exc:
                raise ValueError("time_zone must be a valid IANA time zone") from exc
        return value


class ImportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["append", "replace"]


class RelationshipLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_source_id: str = Field(min_length=1, max_length=128)
    left_key: str = Field(min_length=1, max_length=256)
    right_source_id: str = Field(min_length=1, max_length=128)
    right_key: str = Field(min_length=1, max_length=256)
    relationship: str = Field(min_length=1, max_length=100)


class RelationshipPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    links: list[RelationshipLink] = Field(min_length=1, max_length=20)


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)


class ModelRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_key: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=1000)


class PermissionPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_levels: dict[str, int]

    @field_validator("role_levels")
    @classmethod
    def validate_role_levels(cls, value: dict[str, int]) -> dict[str, int]:
        if set(value) != set(ROLES) or any(level < 1 or level > 100 for level in value.values()):
            raise ValueError("role_levels must define viewer, analyst, reviewer and admin with levels 1-100")
        if len(set(value.values())) != len(value):
            raise ValueError("Each role must have a distinct permission level")
        if not value["viewer"] < value["analyst"] < value["reviewer"] < value["admin"]:
            raise ValueError("Role levels must preserve viewer < analyst < reviewer < admin")
        return value


class ProjectRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=128)


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    company_name: str = Field(min_length=1, max_length=128)
    admin_username: str = Field(min_length=1, max_length=64)
    admin_email: str = Field(min_length=3, max_length=128)
    admin_password: str = Field(min_length=8, max_length=128)


class CompanyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    company_name: str = Field(min_length=1, max_length=128)
    admin_username: str | None = Field(default=None, max_length=64)
    admin_email: str | None = Field(default=None, max_length=128)
    admin_password: str | None = Field(default=None, min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username_or_email: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)
    company_id: str | None = Field(default=None, max_length=64)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=128)
    role: Literal["viewer", "analyst", "reviewer", "admin"] = "viewer"
    temp_password: str | None = Field(default=None, min_length=8, max_length=128)


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    role: Literal["viewer", "analyst"] = "viewer"
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])


class AdminSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_reviewer_mapping_approval: bool


class SchedulerToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class WorkspaceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, max_length=128)


class UserPreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_project_id: str = Field(min_length=1, max_length=128)


class IncidentAssemblyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anomaly_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=100)
    prediction_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=100)
    title: str | None = Field(default=None, max_length=200)


class DriverAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: Annotated[str, Field(min_length=1, max_length=128)]
    source_id: Annotated[str, Field(min_length=1, max_length=128)]
    affected_record_refs: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(min_length=1, max_length=5000)


class UserGraphRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_node_id: str = Field(min_length=1, max_length=256)
    right_node_id: str = Field(min_length=1, max_length=256)
    meaning: str = Field(min_length=1, max_length=500)
    source_record_ref: str = Field(min_length=1, max_length=256)
    valid_from: str | None = Field(default=None, max_length=64)
    valid_to: str | None = Field(default=None, max_length=64)


class CompanyRiskConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weights: dict[str, float]
    thresholds: dict[str, float]


class RiskScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    likelihood: float | None = Field(default=None, ge=0, le=1)
    likelihood_calibrated: bool = False
    impact: float | None = Field(default=None, ge=0, le=1)
    evidence_strength: float | None = Field(default=None, ge=0, le=1)
    uncertainty: float | None = Field(default=None, ge=0, le=1)


class PlaybookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: Annotated[str, Field(min_length=1, max_length=128)]
    driver_type: Literal["supplier", "carrier", "product", "region", "mode", "week"]
    driver_value: str = Field(min_length=1, max_length=256)
    evidence_refs: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(min_length=1, max_length=100)


class WhatIfScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    assumed_relative_probability_reduction: float = Field(ge=0, le=1)
    assumptions: list[str] = Field(min_length=1, max_length=20)


class WhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    affected_order_count: int = Field(ge=0)
    calibrated_delay_probability: float = Field(ge=0, le=1)
    probability_calibrated: bool = False
    scenarios: list[WhatIfScenarioRequest] = Field(default_factory=list, max_length=20)


class ActionVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executed: bool
    verified: bool = False
    result: dict[str, Any] | None = None


class OutcomeRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: Annotated[str, Field(min_length=1, max_length=128)]
    source: str = Field(min_length=1, max_length=200)
    observed_at: datetime
    facts: dict[str, Any] = Field(default_factory=dict)
    record_refs: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(default_factory=list, max_length=500)
    prediction_refs: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=100)
    recommendation_refs: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=100)
    result: dict[str, Any] = Field(default_factory=dict)
    verified_alert_label: bool | None = None
    alert_was_raised: bool | None = None


class AlertAcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)


class AlertAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_to: str = Field(min_length=1, max_length=200)


def _tenant_paths(repo: Repository, filename: str) -> tuple[Path, Path]:
    """Return a private tenant upload directory and a safe temporary destination."""
    if Path(filename).name != filename or any(char in filename for char in ("/", "\\", "\x00")):
        raise ValueError("Filename must be a plain file name without path components")
    safe_company = re.sub(r"[^A-Za-z0-9_-]", "_", repo.company_id)
    root = Path("data/raw/uploads/companies") / safe_company
    root.mkdir(parents=True, exist_ok=True)
    temp = root / f".{uuid.uuid4().hex}.part"
    return root, temp


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _profile_import_job(repo: Repository, job_id: str, source_id: str, dataset_version_id: str,
                        file_path: str, filename: str, dataset_name: str) -> None:
    """Background profile job; stores only aggregate statistics, never source values."""
    job = repo.get(ImportJobRow, job_id)
    source = repo.get(DataSourceRow, source_id)
    try:
        if job is None or source is None:
            return
        report = profile_uploaded_file(Path(file_path), filename, dataset_name)
        if report.has_formula_injection_risk:
            job.status = "FAILED"
            job.payload = {"processed_rows": report.processed_rows, "total_rows": report.total_rows,
                           "statistics": report.model_dump(mode="json"),
                           "error": "CSV formula injection markers found; original retained unchanged, import blocked"}
            repo.add(job)
            return
        dataset_version = repo.get(DatasetVersionRow, dataset_version_id)
        drift_result = None
        prior_versions = [
            v for v in repo.list_rows(DatasetVersionRow)
            if v.dataset == dataset_name and v.id != dataset_version_id and (v.payload or {}).get("profile")
        ]
        if prior_versions:
            from src.monitoring.drift import compare_profiles
            prior_profile = prior_versions[-1].payload["profile"]
            drift_settings = getattr(load_settings(), "drift", None)
            kwargs = {}
            if drift_settings:
                kwargs = {
                    "max_row_count_change_fraction": drift_settings.max_row_count_change_fraction,
                    "max_null_rate_change": drift_settings.max_null_rate_change,
                    "max_numeric_mean_shift": drift_settings.max_numeric_mean_shift,
                    "max_category_concentration_change": drift_settings.max_category_concentration_change,
                }
            drift_result = compare_profiles(prior_profile, report.model_dump(mode="json"), **kwargs)
            _audit(repo, "dataset_drift_checked", "system", source=dataset_name, record_refs=[dataset_version_id],
                   details={"status": drift_result["status"], "alerts": drift_result["alerts"],
                            "schema": drift_result["schema"], "warning": "Drift is a warning, never an automatic retrain trigger."})

        if dataset_version:
            dataset_version.payload = {**dataset_version.payload,
                "profile": report.model_dump(mode="json"),
                "drift": drift_result,
                "processed_rows": report.processed_rows, "total_rows": report.total_rows}
            repo.add(dataset_version)
        job.status = "AWAITING_IMPORT_DECISION"
        job.payload = {"processed_rows": report.processed_rows, "total_rows": report.total_rows,
                       "total_rows_known": report.total_rows_known,
                       "statistics": report.model_dump(mode="json"), "error": None,
                       "drift": drift_result,
                       "source_sha256": dataset_version.source_hash if dataset_version else None}
        repo.add(job)
    except Exception as exc:  # noqa: BLE001 - job failures are returned through job status.
        if job:
            processed = int(getattr(exc, "processed_rows", 0))
            job.status = "PARTIAL" if processed else "FAILED"
            job.payload = {**(job.payload or {}), "processed_rows": processed, "total_rows": None,
                           "total_rows_known": False,
                           "error": _safe_upload_error(exc)}
            repo.add(job)


def _safe_upload_error(exc: Exception) -> str:
    """Keep useful structural failure reasons while dropping parser snippets and row values."""
    message = str(exc)
    safe_markers = (
        "Zip archive contains too many entries", "Uncompressed size exceeds",
        "Suspicious compression ratio", "ZIP contains no supported", "ZIP contains multiple data files",
        "Path traversal detected", "Symbolic links are not permitted", "Allowed file types:",
        "Unsupported archive member type:",
    )
    for marker in safe_markers:
        if message.startswith(marker):
            return marker.rstrip(":")
    if isinstance(exc, ValueError):
        return "Profiling validation failed; inspect the upload structure and mapping"
    return f"Profiling failed with {type(exc).__name__}; row contents were omitted"


def _project_capability_report(repo: Repository, project_id: str) -> dict[str, Any]:
    project = repo.get(ProjectRow, project_id)
    if project is None:
        raise HTTPException(404, detail="Project not found")
    sources = [source for source in repo.list_rows(DataSourceRow) if source.project_id == project_id]
    source_views = []
    for source in sources:
        accepted = sorted((mapping for mapping in repo.list_rows(MappingVersionRow)
                           if mapping.data_source_id == source.id and mapping.status == "ACCEPTED"),
                          key=lambda item: item.version)
        source_views.append({"name": source.name, "status": "ACCEPTED" if accepted else "PENDING_REVIEW",
                             "mapping": accepted[-1].mapping if accepted else {}})
    report = assess_capabilities(source_views)
    report["project_id"] = project.id
    return report


def _execute_project_pipeline(repo: Repository, run_id: str, project_id: str) -> None:
    run = repo.get(PipelineRunRow, run_id)
    if run is None:
        return
    run.status = "RUNNING"
    run.payload = {**run.payload, "started_at": datetime.now(timezone.utc).isoformat()}
    repo.add(run)
    sources = [source for source in repo.list_rows(DataSourceRow) if source.project_id == project_id]
    jobs = [job for job in repo.list_rows(ImportJobRow) if job.data_source_id in {s.id for s in sources}
            and job.status == "COMPLETED" and job.payload.get("processed_file")]
    files = [Path(job.payload["processed_file"]) for job in jobs if Path(job.payload["processed_file"]).is_file()]
    config = load_settings()
    rules = RuleConfig(**config.validation.model_dump())

    def persist_step(step: dict[str, Any]) -> None:
        step = _sanitize_for_json(step)
        steps = list(run.payload.get("steps", []))
        for index, existing in enumerate(steps):
            if existing.get("name") == step["name"]:
                steps[index] = step
                break
        else:
            steps.append(step)
        run.payload = {**run.payload, "steps": steps, "updated_at": datetime.now(timezone.utc).isoformat()}
        repo.add(run)

    try:
        result = run_canonical_pipeline(canonical_files=files, capabilities=run.payload["capabilities"],
            rules=rules, retry_attempts=config.pipeline.retry_attempts,
            retry_backoff_seconds=config.pipeline.retry_backoff_seconds, on_step=persist_step,
            anomaly_settings=config.anomaly, delay_settings=config.delay_prediction,
            forecast_settings=config.forecasting)
        result = _sanitize_for_json(result)
        run.status = result["status"]
        run.payload = {**run.payload, "result": result, "completed_at": datetime.now(timezone.utc).isoformat()}

        # Persist findings to repository rows for downstream API access
        try:
            d_ver_id = next((v.id for v in repo.list_rows(DatasetVersionRow)), None)
            if not d_ver_id:
                for j in jobs:
                    if j.dataset_version_id:
                        d_ver_id = j.dataset_version_id
                        break
            if not d_ver_id:
                d_ver_id = str(uuid.uuid4())
                repo.add(DatasetVersionRow(
                    id=d_ver_id,
                    dataset="canonical",
                    source="canonical",
                    source_hash="sha256:canonical",
                    observed_at=datetime.now(timezone.utc),
                    license_status="UNKNOWN",
                    payload={"project_id": project_id}
                ))

            anom_step = next((s for s in result.get("steps", []) if s.get("name") == "anomaly_detection"), None)
            anomalies_list = []
            if anom_step:
                res = anom_step.get("result")
                if isinstance(res, list):
                    anomalies_list = res
                elif isinstance(res, dict):
                    anomalies_list = res.get("anomalies", [])
                for anom in anomalies_list[:500]:
                    anom_id = anom.get("id") or str(uuid.uuid4())
                    refs = anom.get("record_refs")
                    r_ref = str(refs[0]) if isinstance(refs, list) and refs else str(anom.get("record_ref", ""))
                    repo.add(AnomalyRow(
                        id=anom_id,
                        dataset_version_id=d_ver_id,
                        source="canonical_pipeline",
                        detector=anom.get("detector") or anom.get("method", "canonical"),
                        record_ref=r_ref,
                        feature=anom.get("feature") or anom.get("metric", "measure"),
                        observed_value=anom.get("observed_value"),
                        baseline=anom.get("baseline"),
                        payload=anom
                    ))

            delay_step = next((s for s in result.get("steps", []) if s.get("name") == "delay_prediction"), None)
            top_drivers = []
            if delay_step and isinstance(delay_step.get("result"), dict):
                top_drivers = delay_step["result"].get("top_drivers", [])

            if anomalies_list or top_drivers:
                # Group anomalies and drivers into several incidents by entity and time window
                clusters: dict[str, dict[str, Any]] = defaultdict(lambda: {
                    "anomalies": [],
                    "drivers": [],
                    "record_refs": set(),
                })

                for anom in anomalies_list:
                    ent = anom.get("entity") or {}
                    refs = anom.get("record_refs") or []
                    r_ref = str(refs[0]) if isinstance(refs, list) and refs else str(anom.get("record_ref", ""))

                    if "supplier_id" in ent:
                        grp_key = f"supplier:{ent['supplier_id']}"
                    elif "carrier" in ent:
                        grp_key = f"carrier:{ent['carrier']}"
                    elif "product_id" in ent:
                        grp_key = f"product:{ent['product_id']}"
                    elif "warehouse_id" in ent:
                        grp_key = f"warehouse:{ent['warehouse_id']}"
                    elif "weekly_demand" in str(anom.get("metric", "")):
                        grp_key = f"demand:{ent.get('product_id', 'all')}"
                    else:
                        grp_key = f"metric:{anom.get('metric', 'quality')}"

                    clusters[grp_key]["anomalies"].append(anom)
                    if r_ref:
                        clusters[grp_key]["record_refs"].add(r_ref)

                for drv in top_drivers:
                    fac = str(drv.get("factor", ""))
                    val = str(drv.get("value", ""))
                    if "supplier" in fac:
                        grp_key = f"supplier:{val}"
                    elif "carrier" in fac:
                        grp_key = f"carrier:{val}"
                    elif "product" in fac:
                        grp_key = f"product:{val}"
                    elif "route" in fac:
                        grp_key = f"route:{val}"
                    else:
                        grp_key = f"driver:{fac}:{val}"

                    clusters[grp_key]["drivers"].append(drv)
                    clusters[grp_key]["record_refs"].add(f"order-group-{val}")

                sorted_clusters = sorted(
                    clusters.items(),
                    key=lambda item: len(item[1]["anomalies"]) + len(item[1]["drivers"]) * 10,
                    reverse=True
                )

                if len(sorted_clusters) == 1:
                    primary_k, primary_v = sorted_clusters[0]
                    half = len(primary_v["anomalies"]) // 2
                    sorted_clusters = [
                        (f"{primary_k}:batch_1", {"anomalies": primary_v["anomalies"][:half], "drivers": primary_v["drivers"], "record_refs": set(list(primary_v["record_refs"])[:max(1, half)])}),
                        (f"{primary_k}:batch_2", {"anomalies": primary_v["anomalies"][half:], "drivers": [], "record_refs": set(list(primary_v["record_refs"])[max(1, half):])}),
                    ]

                # Create distinct incidents for top clusters
                for grp_key, grp_data in sorted_clusters[:5]:
                    inc_anoms = grp_data["anomalies"]
                    inc_drivers = grp_data["drivers"]
                    grp_refs = sorted(list(grp_data["record_refs"]))
                    if not grp_refs and inc_anoms:
                        grp_refs = [a.get("record_ref") or f"ref-{i}" for i, a in enumerate(inc_anoms[:10])]
                    if not grp_refs:
                        grp_refs = [f"rec-{grp_key}-{uuid.uuid4().hex[:6]}"]

                    inc_id = str(uuid.uuid4())
                    title_name = grp_key.replace(":", " ").title()
                    inc_title = f"Operational Risk Incident: {title_name}"

                    evidence_ids: list[str] = []
                    ledger_supporting: list[LedgerEvidence] = []

                    sample_anoms = inc_anoms[:10] if inc_anoms else [{"metric": "delay_rate", "observed_value": 0.3, "baseline": 0.14, "detector": "canonical_delay"}]
                    for idx, a in enumerate(sample_anoms):
                        ev_id = str(uuid.uuid4())
                        refs = a.get("record_refs")
                        r_ref = str(refs[0]) if isinstance(refs, list) and refs else str(a.get("record_ref") or grp_refs[0])
                        met = a.get("feature") or a.get("metric", "delay")
                        obs = a.get("observed_value", 0.0)
                        base = a.get("baseline", 0.0)

                        repo.add(EvidenceRow(
                            id=ev_id,
                            dataset_version_id=d_ver_id,
                            incident_id=inc_id,
                            source="canonical_pipeline",
                            observed_at=datetime.now(timezone.utc),
                            record_refs=[r_ref],
                            payload={"detector": a.get("detector") or a.get("method", "canonical"), "observed_value": obs, "baseline": base, "feature": met}
                        ))
                        evidence_ids.append(ev_id)
                        ledger_supporting.append(LedgerEvidence(
                            evidence_id=ev_id,
                            classification="supporting",
                            source="canonical_pipeline",
                            record_refs=[r_ref],
                            observed_at=datetime.now(timezone.utc),
                            strength=0.85,
                            description=f"Elevated {met} observed: {obs} vs baseline {base}"
                        ))

                    hyp_ids: list[str] = []
                    target_drivers = inc_drivers if inc_drivers else top_drivers[:1]
                    for drv in target_drivers:
                        h_id = str(uuid.uuid4())
                        factor = drv.get("factor", "supplier")
                        val = drv.get("value", "identified_entity")
                        diff = drv.get("difference", 0.05)
                        rate = drv.get("delay_rate", 0.25)
                        confounding_note = f" [{drv.get('confounding_status')}]" if drv.get("confounding_status") else ""

                        case_ledger = EvidenceLedger(
                            supporting=ledger_supporting[:4],
                            contradicting=[],
                            missing=[f"On-site quality audit for {factor}:{val}", "Alternative carrier telemetry data"],
                        )
                        h_stmt = f"Disruption driven by {factor}: {val} (rate: {rate}, diff: {diff}){confounding_note}"
                        case = HypothesisCase(
                            id=h_id,
                            statement=h_stmt,
                            source="canonical_pipeline",
                            status=HypothesisStatus.UNVERIFIED,
                            ledger=case_ledger,
                        )
                        repo.add(HypothesisRow(
                            id=h_id,
                            incident_id=inc_id,
                            statement=h_stmt,
                            status=HypothesisStatus.UNVERIFIED.value,
                            payload=case.model_dump(mode="json"),
                        ))
                        hyp_ids.append(h_id)

                        # Recommendations with playbook specific to driver type (never route diversification for product!)
                        rec = recommend_for_driver(
                            driver={"dimension": factor, "factor": factor, "value": val,
                                    "estimated_start_date": drv.get("estimated_start_date"),
                                    "pre_change_rate": drv.get("pre_change_rate"),
                                    "post_change_rate": drv.get("post_change_rate"),
                                    "sample_size": drv.get("sample_size")},
                            available_roles={"supplier_id", "order_id", "carrier_id", "carrier", "shipment_id", "product_id", "route", "region"},
                            evidence_refs=evidence_ids,
                        )
                        if rec.get("status") == "PROPOSED":
                            rec_id = str(uuid.uuid4())
                            rec["id"] = rec_id
                            rec["incident_id"] = inc_id
                            rec["hypothesis_id"] = h_id
                            repo.add(RecommendationRow(
                                id=rec_id,
                                incident_id=inc_id,
                                hypothesis_id=h_id,
                                source="playbook",
                                action=rec["action"],
                                payload=rec,
                            ))

                    repo.add(IncidentRow(
                        id=inc_id,
                        dataset_version_id=d_ver_id,
                        source="canonical_pipeline",
                        title=inc_title,
                        occurred_at=datetime.now(timezone.utc),
                        payload={
                            "title": inc_title,
                            "description": f"Incident cluster for {title_name} with {len(inc_anoms)} anomalies and {len(target_drivers)} associated drivers.",
                            "severity": "HIGH",
                            "record_refs": grp_refs[:20],
                            "evidence_refs": evidence_ids,
                            "hypothesis_refs": hyp_ids,
                            "limitations": ["Correlation indicators from canonical pipeline; not proven causes."],
                        }
                    ))
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001 - persist a safe structural failure only
        run.status = "FAILED"
        run.payload = {**run.payload, "error": type(exc).__name__,
                       "failed_at": datetime.now(timezone.utc).isoformat()}
    repo.add(run)



def _key_counts(path: Path, filename: str, column: str, chunk_rows: int) -> tuple[Counter[str], int]:
    """Read a relationship key into an in-memory counter; raw values are never persisted."""
    suffix = Path(filename).suffix.lower()

    def read(stream, member_name: str | None = None):
        lower = (member_name or filename).lower()
        if lower.endswith(".csv"):
            yield from __import__("pandas").read_csv(stream, usecols=[column], chunksize=chunk_rows)
        elif lower.endswith((".jsonl", ".ndjson")):
            for frame in __import__("pandas").read_json(stream, lines=True, chunksize=chunk_rows):
                yield frame[[column]]
        elif lower.endswith(".json"):
            frame = __import__("pandas").read_json(stream)
            yield frame[[column]]
        else:
            frame = __import__("pandas").read_excel(stream, usecols=[column])
            yield frame

    counts: Counter[str] = Counter()
    nulls = 0
    with path.open("rb") as stream:
        if suffix == ".zip":
            with zipfile.ZipFile(stream) as archive:
                members = [info for info in archive.infolist() if not info.is_dir()
                           and Path(info.filename).suffix.lower() in {".csv", ".xlsx", ".json", ".jsonl"}]
                if not members:
                    raise ValueError("No supported tabular member found")
                for info in members:
                    with archive.open(info) as member:
                        frames = read(member, info.filename)
                        for frame in frames:
                            values = frame.iloc[:, 0]
                            nulls += int(values.isna().sum())
                            counts.update(str(value) for value in values.dropna())
        else:
            for frame in read(stream):
                values = frame.iloc[:, 0]
                nulls += int(values.isna().sum())
                counts.update(str(value) for value in values.dropna())
    return counts, nulls


def _save_mapping_version(dataset_name: str, body: MappingVersionRequest, repo: Repository,
                          actor: str, *, status: str) -> dict[str, Any]:
    sources = [row for row in repo.list_rows(DataSourceRow) if row.name == dataset_name]
    if not sources:
        raise HTTPException(404, detail="Dataset source not found")
    source = max(sources, key=lambda item: item.created_at)
    data_version = next((item for item in repo.list_rows(DatasetVersionRow)
                         if item.payload.get("source_id") == source.id), None)
    profile_data = data_version.payload.get("profile") if data_version else None
    if not profile_data:
        raise HTTPException(409, detail="Import profiling is not complete")
    observed_columns = {column.get("name") for column in profile_data.get("columns", [])}
    missing_columns = (set(body.mappings) | set(body.custom_fields.values())) - observed_columns
    if missing_columns:
        raise HTTPException(422, detail=f"Mapped source columns were not found: {sorted(missing_columns)}")
    source_ids = {item.id for item in sources}
    versions = [row for row in repo.list_rows(MappingVersionRow) if row.data_source_id in source_ids]
    next_number = max((int(row.version.lstrip("v")) for row in versions if row.version.lstrip("v").isdigit()), default=0) + 1
    version = f"v{next_number:04d}"
    try:
        profile = DatasetProfile(name=dataset_name, version=version,
            description=body.reason, source_file=Path(source.location_ref).name,
            source_archive_sha256="", mappings=body.mappings,
            custom_fields=body.custom_fields, units=body.units,
            time_zone=body.time_zone, date_format=body.date_format,
            capabilities=detect_capabilities(body.mappings))
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    dataset_version = next((item for item in repo.list_rows(DatasetVersionRow)
                            if item.payload.get("source_id") == source.id), None)
    if dataset_version:
        profile.source_archive_sha256 = dataset_version.source_hash
    row = MappingVersionRow(id=str(uuid.uuid4()), data_source_id=source.id,
        version=version, status=status, mapping={**profile.model_dump(mode="json"),
            "review_history": [{"status": "PENDING_REVIEW", "actor": actor,
                                "reason": body.reason, "timestamp": datetime.now(timezone.utc).isoformat()}]})
    repo.add(row)
    _audit(repo, "dataset_mapping_created", actor, source=dataset_name, record_refs=[row.id],
           details={"version": version, "status": status, "mapping_count": len(body.mappings)})
    return {"id": row.id, "dataset_name": dataset_name, "version": version,
            "status": row.status, "mapping": row.mapping, "auto_confirmed": False}


def _review_mapping(dataset_name: str, version: str, reason: str, status: str,
                    repo: Repository, actor: str) -> dict[str, Any]:
    sources = [row for row in repo.list_rows(DataSourceRow) if row.name == dataset_name]
    source_ids = {row.id for row in sources}
    row = next((item for item in repo.list_rows(MappingVersionRow)
                if item.data_source_id in source_ids and item.version == version), None)
    if not row:
        raise HTTPException(404, detail="Mapping version not found")
    if row.status not in {"PENDING_REVIEW", "NEEDS_CLARIFICATION"}:
        raise HTTPException(409, detail="Only pending mappings can be reviewed")
    row.status = status
    row.mapping = {**row.mapping, "review_history": [*row.mapping.get("review_history", []),
        {"status": status, "actor": actor, "reason": reason,
         "timestamp": datetime.now(timezone.utc).isoformat()}]}
    repo.add(row)
    if status == "ACCEPTED":
        values = {key: value for key, value in row.mapping.items()
                  if key in DatasetProfile.model_fields and key != "review_history"}
        profile = DatasetProfile.model_validate(values)
        safe_company = re.sub(r"[^A-Za-z0-9_-]", "_", repo.company_id)
        target_dir = Path("config/profiles/companies") / safe_company
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{dataset_name}.{version}.yaml"
        import yaml
        target.write_text(yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
        row.mapping = {**row.mapping, "profile_path": str(target)}
        repo.add(row)
    _audit(repo, f"dataset_mapping_{status.lower()}", actor, source=dataset_name,
           record_refs=[row.id], details={"version": version, "reason": reason})
    return {"id": row.id, "dataset_name": dataset_name, "version": row.version,
            "status": row.status, "mapping": row.mapping, "auto_confirmed": False}


def _source_frames(path: Path, filename: str, chunk_rows: int):
    """Yield source-shaped frames without extracting ZIP members to disk."""
    def read_stream(stream, member_name: str):
        lower = member_name.lower()
        if lower.endswith(".csv"):
            yield from pd.read_csv(stream, chunksize=chunk_rows, low_memory=False)
        elif lower.endswith((".jsonl", ".ndjson")):
            yield from pd.read_json(stream, lines=True, chunksize=chunk_rows)
        elif lower.endswith(".json"):
            yield from json_record_chunks(stream, chunk_rows)
        elif lower.endswith((".xlsx", ".xlsm")):
            from openpyxl import load_workbook
            book = load_workbook(stream, read_only=True, data_only=True)
            try:
                rows = book.active.iter_rows(values_only=True)
                header = [str(x) if x is not None else f"column_{i + 1}" for i, x in enumerate(next(rows, ()))]
                batch = []
                for row in rows:
                    batch.append(row)
                    if len(batch) >= chunk_rows:
                        yield pd.DataFrame(batch, columns=header)
                        batch = []
                if batch:
                    yield pd.DataFrame(batch, columns=header)
            finally:
                book.close()
        else:
            raise ValueError(f"Unsupported source format: {member_name}")

    with path.open("rb") as stream:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(stream) as archive:
                for info in archive.infolist():
                    if info.is_dir() or Path(info.filename).suffix.lower() not in {
                        ".csv", ".json", ".jsonl", ".ndjson", ".xlsx", ".xlsm"}:
                        continue
                    if Path(info.filename).is_absolute() or ".." in Path(info.filename.replace("\\", "/")).parts:
                        raise ValueError("Path traversal detected in ZIP member")
                    with archive.open(info) as member:
                        if info.filename.lower().endswith((".xlsx", ".xlsm")):
                            import io
                            yield from read_stream(io.BytesIO(member.read()), info.filename)
                        else:
                            yield from read_stream(member, info.filename)
        else:
            yield from read_stream(stream, filename)


def _materialize_import(repo: Repository, job_id: str, mode: str, actor: str) -> None:
    """Apply accepted source mapping into a canonical JSONL derivative, verifying full row count."""
    job = repo.get(ImportJobRow, job_id)
    if not job:
        return
    source = repo.get(DataSourceRow, job.data_source_id)
    version = repo.get(DatasetVersionRow, job.dataset_version_id) if job.dataset_version_id else None
    mappings = [row for row in repo.list_rows(MappingVersionRow)
                if row.data_source_id == job.data_source_id and row.status == "ACCEPTED"]
    if not source or not version or not mappings:
        job.status = "FAILED"
        job.payload = {**job.payload, "error": "An accepted mapping is required before importing"}
        repo.add(job)
        return
    mapping_row = sorted(mappings, key=lambda row: row.version)[-1]
    mapping = mapping_row.mapping
    column_map: dict[str, str] = mapping["mappings"]
    custom_map: dict[str, str] = mapping.get("custom_fields", {})
    expected = int(job.payload.get("total_rows") or 0)
    company = re.sub(r"[^A-Za-z0-9_-]", "_", repo.company_id)
    target_dir = Path("data/processed/companies") / company / source.name
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{job.id}.jsonl"
    partial = target.with_suffix(".partial.jsonl")
    quarantine_target = target_dir / f"{job.id}.quarantine.jsonl"
    quarantine_partial = quarantine_target.with_suffix(".partial.jsonl")
    count = 0
    quarantined_count = 0
    try:
        with partial.open("w", encoding="utf-8", newline="\n") as out, \
             quarantine_partial.open("w", encoding="utf-8", newline="\n") as q_out:
            for frame in _source_frames(Path(source.location_ref), job.payload.get("filename", "source.csv"),
                                        load_settings().uploads.chunk_rows):
                for row in frame.to_dict(orient="records"):
                    canonical: dict[str, Any] = {}
                    for source_column, role in column_map.items():
                        if source_column in row:
                            canonical[role] = row[source_column]
                    aliases = {"order_ts": "event_timestamp", "promised_ts": "promised_timestamp",
                               "delivered_ts": "delivered_timestamp"}
                    canonical = {aliases.get(key, key): value for key, value in canonical.items()}
                    is_quarantined = False
                    quarantine_reason = None
                    for timestamp_key in ("event_timestamp", "promised_timestamp", "delivered_timestamp"):
                        timestamp_value = canonical.get(timestamp_key)
                        if timestamp_value is not None and not pd.isna(timestamp_value):
                            date_format = mapping.get("date_format")
                            if date_format:
                                for token, directive in (("YYYY", "%Y"), ("YY", "%y"),
                                                         ("MM", "%m"), ("DD", "%d"),
                                                         ("HH", "%H"), ("mm", "%M"), ("ss", "%S")):
                                    date_format = date_format.replace(token, directive)
                            try:
                                parsed = pd.to_datetime(timestamp_value,
                                    format=date_format or "mixed", errors="raise")
                                configured_zone = mapping.get("time_zone")
                                if configured_zone:
                                    zone = ZoneInfo(configured_zone)
                                    parsed = parsed.tz_localize(zone) if parsed.tzinfo is None else parsed.tz_convert(zone)
                                canonical[timestamp_key] = parsed.isoformat()
                            except Exception as d_exc:
                                is_quarantined = True
                                quarantine_reason = f"invalid_date_{timestamp_key}: {type(d_exc).__name__}"
                                break
                    if is_quarantined:
                        q_record = {**row, "_quarantine_reason": quarantine_reason, "_source": source.name}
                        q_out.write(json.dumps({k: _json_safe(v) for k, v in q_record.items()}, ensure_ascii=False) + "\n")
                        quarantined_count += 1
                        continue

                    reference = str(canonical.get("order_id", canonical.get("event_id", f"{job.id}:{count}")))
                    if "event_timestamp" not in canonical:
                        canonical["event_timestamp"] = canonical.get("delivered_timestamp",
                            canonical.get("promised_timestamp"))
                    custom_sources = set(custom_map.values())
                    custom_fields = {str(key): row[value] for key, value in custom_map.items() if value in row}
                    mapped_sources = set(column_map) | custom_sources
                    custom_fields.update({str(key): value for key, value in row.items() if key not in mapped_sources})
                    payload = {key: _json_safe(value) for key, value in canonical.items()}
                    payload.update({"event_id": reference, "source": source.name,
                                    "source_record_ref": f"{job.id}:{count}",
                                    "custom_fields": {key: _json_safe(value) for key, value in custom_fields.items()}})
                    out.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    count += 1
        if (count + quarantined_count) != expected and expected > 0:
            job.status = "PARTIAL"
            job.payload = {**job.payload, "mode": mode, "processed_rows": count,
                           "quarantined_rows": quarantined_count,
                           "total_rows": expected, "processed_file": str(partial),
                           "error": "Processed row count differs from profiled total; import is partial"}
            repo.add(job)
            return
        partial.replace(target)
        if quarantined_count > 0 and quarantine_partial.exists():
            quarantine_partial.replace(quarantine_target)
        lineage_path = target.with_suffix(".lineage.json")
        lineage_path.write_text(json.dumps({"source_sha256": version.source_hash,
            "mapping_version": mapping_row.version, "mode": mode, "rows": count,
            "quarantined_rows": quarantined_count,
            "transforms": ["source-column mapping", "custom_fields preservation", "event provenance", "invalid date quarantine"],
            "units": mapping.get("units", {}), "time_zone": mapping.get("time_zone"),
            "date_format": mapping.get("date_format"),
            "created_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
        if mode == "replace":
            for old in repo.list_rows(DataSourceRow):
                if old.name == source.name and old.id != source.id:
                    repo.soft_delete(DataSourceRow, old.id, actor=actor,
                                     reason="Replaced by an explicitly approved import")
        job.status = "COMPLETED"
        job.payload = {**job.payload, "mode": mode, "processed_rows": count, "total_rows": expected,
                       "quarantined_rows": quarantined_count,
                       "processed_file": str(target),
                       "quarantined_file": str(quarantine_target) if quarantined_count else None,
                       "lineage_file": str(lineage_path),
                       "completed_at": datetime.now(timezone.utc).isoformat()}
        repo.add(job)
    except Exception as exc:  # noqa: BLE001 - expose a durable failed/partial job record.
        job.status = "PARTIAL" if count else "FAILED"
        job.payload = {**job.payload, "mode": mode, "processed_rows": count, "total_rows": expected,
                       "quarantined_rows": quarantined_count,
                       "processed_file": str(partial) if count else None,
                       "error": f"Canonical materialization failed with {type(exc).__name__}; row contents were omitted"}
        repo.add(job)



def _json_safe(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _payload(row: Any) -> dict[str, Any]:
    data = dict(getattr(row, "payload", {}) or {})
    data.setdefault("id", row.id)
    data.setdefault("created_at", getattr(row, "created_at", datetime.now(timezone.utc)))
    return data


def _map(row: Any, schema: type[BaseModel], **defaults: Any) -> Any:
    values = {**defaults, **_payload(row)}
    try:
        return schema.model_validate(values)
    except ValidationError:
        # The typed row columns remain usable when older persisted payloads are partial.
        fields = set(schema.model_fields)
        values.update({key: value for key, value in vars(row).items()
                       if key in fields and not key.startswith("_")})
        return schema.model_validate({key: value for key, value in values.items() if key in fields})


def _hypothesis_status_label(status: str) -> str:
    """Human-readable UI wording; canonical lifecycle values remain unchanged."""
    return {"UNVERIFIED": "Unverified", "SUPPORTED": "Supported by evidence",
            "CONFIRMED": "Human confirmed", "REJECTED": "Rejected", "CLOSED": "Closed"}.get(status, status)


def _repository(request: Request, x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None) -> Repository:
    identity = getattr(request.state, "identity", None)
    repo = getattr(request.app.state, "repository", None)
    app_company = repo.company_id if repo else "local"
    target_company = x_company_id or (identity.get("company_id") if identity else None) or app_company
    if repo is None:
        repo = Repository(load_settings().storage.url, company_id=target_company)
        request.app.state.repository = repo
        return repo
    if target_company != repo.company_id:
        return Repository(str(repo.engine.url), company_id=target_company, engine=repo.engine)
    return repo


def _auth(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
) -> dict[str, Any]:
    # 1. Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = decode_access_token(token)
        except Exception as exc:
            raise HTTPException(401, detail="Session expired or invalid token") from exc
        token_company = str(payload.get("company_id", "local")).strip()
        if x_company_id and x_company_id.strip() != token_company:
            raise HTTPException(403, detail=f"Cross-company access forbidden: token company '{token_company}' does not match requested '{x_company_id}'")
        role = payload.get("role", "viewer")
        if role not in ROLES:
            raise HTTPException(403, detail="User account has no valid role")
        actor = f"user:{payload.get('username', payload.get('sub', 'user'))}"
        identity = {
            "role": role,
            "actor": actor,
            "company_id": token_company,
            "user_id": payload.get("sub"),
            "username": payload.get("username"),
            "email": payload.get("email"),
            "is_machine_key": False,
            "must_change_password": payload.get("must_change_password", False),
        }
        request.state.identity = identity
        return identity

    # 2. Machine API Key (X-API-Key header or Authorization: ApiKey ...)
    raw_key = x_api_key
    if not raw_key and authorization and authorization.startswith("ApiKey "):
        raw_key = authorization.removeprefix("ApiKey ").strip()

    if raw_key:
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        repo = getattr(request.app.state, "repository", None)
        if repo is None:
            repo = Repository(load_settings().storage.url, company_id=x_company_id or "local")
            request.app.state.repository = repo

        with repo.sessions() as session:
            key_row = session.scalar(select(ApiKeyRow).where(
                ApiKeyRow.key_hash == key_hash,
                ApiKeyRow.revoked_at.is_(None),
                ApiKeyRow.deleted_at.is_(None),
            ))
            if key_row:
                key_company = str(key_row.company_id).strip()
                if x_company_id and x_company_id.strip() != key_company:
                    raise HTTPException(403, detail=f"Cross-company access forbidden: API key company '{key_company}' does not match requested '{x_company_id}'")
                role = key_row.role
                if role not in ROLES:
                    raise HTTPException(403, detail="API key has no valid role")
                actor = f"apikey:{key_row.prefix}"
                identity = {
                    "role": role,
                    "actor": actor,
                    "company_id": key_company,
                    "key_id": key_row.id,
                    "name": key_row.name,
                    "is_machine_key": True,
                }
                request.state.identity = identity
                return identity

        # Legacy API_KEYS_JSON fallback for tests
        try:
            configured = json.loads(os.getenv("API_KEYS_JSON", "{}"))
        except json.JSONDecodeError as exc:
            raise HTTPException(500, detail="API key configuration is invalid") from exc
        if isinstance(configured, dict) and raw_key in configured:
            role = configured[raw_key]
            if not isinstance(role, str) or role not in ROLES:
                raise HTTPException(403, detail="API key has no valid role")
            company_id = x_company_id or (repo.company_id if repo else "local")
            identity = {
                "role": role,
                "actor": f"api:{role}",
                "company_id": company_id,
                "is_machine_key": False,
            }
            request.state.identity = identity
            return identity
        raise HTTPException(401, detail="Valid API key required")

    raise HTTPException(401, detail="Valid API key required")


def _require(minimum_role: str):
    def dependency(request: Request, identity: dict[str, Any] = Depends(_auth)) -> dict[str, Any]:
        policy = getattr(request.app.state, "role_policy", ROLES)
        if policy[identity["role"]] < policy[minimum_role]:
            raise HTTPException(403, detail=f"{minimum_role} role required")
        return identity
    return dependency


def _check_mapping_role(request: Request, identity: dict[str, Any], repo: Repository) -> None:
    setting = repo.get_setting("require_reviewer_mapping_approval")
    require_reviewer = bool(setting.get("value", False)) if setting else False
    min_role = "reviewer" if require_reviewer else "analyst"
    policy = getattr(request.app.state, "role_policy", ROLES)
    if policy[identity["role"]] < policy[min_role]:
        raise HTTPException(403, detail=f"{min_role} role required to approve mappings under company policy")


def _audit(repo: Repository, event_type: str, actor: str, *, source: str | None = None,
           record_refs: list[str] | None = None, details: dict[str, Any] | None = None) -> None:
    settings = load_settings()
    entry = AuditLog(settings.audit.log_path).append(event_type=event_type, actor=actor,
        source=source, record_refs=record_refs or [], details=details or {})
    repo.add(AuditEventRow(id=str(uuid.uuid4()), event_type=event_type, actor=actor,
        source=source, occurred_at=entry.occurred_at, previous_hash=entry.previous_hash,
        event_hash=entry.event_hash, payload={"record_refs": entry.record_refs, "details": entry.details}))


def create_app(repository: Repository | None = None) -> FastAPI:
    app = FastAPI(title="Supply Chain Risk API", version="1.0.0",
                  description="Local risk monitoring API. Mutating operational routes are guarded and dry-run by default.")
    app.state.repository = repository
    app.state.role_policy = dict(ROLES)
    init_repo = repository or Repository(load_settings().storage.url, company_id="local")
    app.state.kill_switch = init_repo.get_kill_switch()
    if scheduler.enabled:
        scheduler.start()

    @app.on_event("shutdown")
    def shutdown_event():
        scheduler.stop()

    origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()] or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Company-Id"])

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "invalid_request", 423: "locked"}.get(exc.status_code, "http_error")
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": code,
            "message": str(exc.detail), "details": None}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request",
            "message": "Request validation failed", "details": jsonable_encoder(exc.errors())}})

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error",
            "message": "Internal server error", "details": None}})

    router = APIRouter(prefix="/api/v1")

    # --- Auth & User Account Routes ---

    @router.get("/auth/setup-status")
    def setup_status(repo: Repository = Depends(_repository)):
        with repo.sessions() as session:
            admin_user = session.scalar(select(UserRow).where(
                UserRow.role == "admin",
                UserRow.is_active == True,
                UserRow.deleted_at.is_(None),
            ))
        return {"setup_required": admin_user is None}

    @router.post("/auth/setup")
    def setup_system(body: SetupRequest, repo: Repository = Depends(_repository)):
        with repo.sessions() as session:
            admin_user = session.scalar(select(UserRow).where(
                UserRow.role == "admin",
                UserRow.is_active == True,
                UserRow.deleted_at.is_(None),
            ))
            if admin_user:
                raise HTTPException(400, detail="Setup has already been completed. Public signup is disabled.")
        repo.create_company(body.company_id, body.company_name)
        company_repo = Repository(str(repo.engine.url), company_id=body.company_id, engine=repo.engine)
        user = company_repo.create_user(
            username=body.admin_username,
            email=body.admin_email,
            password_hash=hash_password(body.admin_password),
            role="admin",
        )
        user.must_change_password = False
        company_repo.add(user)
        ws = WorkspaceRow(id=f"workspace-{body.company_id}", name="Default workspace")
        company_repo.add(ws)
        proj = ProjectRow(id=f"project-{body.company_id}", workspace_id=ws.id, name="Default project")
        company_repo.add(proj)
        user.last_project_id = proj.id
        company_repo.add(user)
        _audit(company_repo, "system_setup_completed", f"user:{user.username}",
               details={"company_id": body.company_id, "admin_user": user.username})
        token = create_access_token({
            "sub": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "company_id": user.company_id,
            "must_change_password": user.must_change_password,
        })
        return {
            "token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "company_id": user.company_id,
                "must_change_password": user.must_change_password,
                "last_project_id": user.last_project_id,
            },
            "message": "Initial company and admin account successfully created",
        }

    @router.post("/auth/login")
    def login(body: LoginRequest, repo: Repository = Depends(_repository)):
        company_id = body.company_id or repo.company_id
        company_repo = Repository(str(repo.engine.url), company_id=company_id, engine=repo.engine)
        user = company_repo.get_user_by_email_or_username(body.username_or_email)
        now = datetime.now(timezone.utc)
        if not user or not user.is_active:
            raise HTTPException(401, detail="Invalid email or password")
        if user.locked_until:
            lock_time = user.locked_until.replace(tzinfo=timezone.utc) if user.locked_until.tzinfo is None else user.locked_until
            if lock_time > now:
                raise HTTPException(423, detail="Account is temporarily locked due to repeated failed login attempts. Please try again later.")
        if not verify_password(body.password, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                company_repo.add(user)
                _audit(company_repo, "user_account_locked", f"user:{user.username}", details={"reason": "max_failed_attempts"})
                raise HTTPException(423, detail="Account is temporarily locked due to repeated failed login attempts. Please try again later.")
            company_repo.add(user)
            _audit(company_repo, "user_login_failed", f"user:{user.username}")
            raise HTTPException(401, detail="Invalid email or password")

        user.failed_login_attempts = 0
        user.locked_until = None
        company_repo.add(user)
        _audit(company_repo, "user_login_success", f"user:{user.username}")
        token = create_access_token({
            "sub": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "company_id": user.company_id,
            "must_change_password": user.must_change_password,
        })
        return {
            "token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "company_id": user.company_id,
                "must_change_password": user.must_change_password,
                "last_project_id": user.last_project_id,
            },
        }

    @router.post("/auth/logout")
    def logout(repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_auth)):
        _audit(repo, "user_logged_out", identity["actor"])
        return {"message": "Logged out successfully"}

    @router.post("/auth/change-password")
    def change_password(body: ChangePasswordRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_auth)):
        user_id = identity.get("user_id")
        user = repo.get_user_by_id(user_id) if user_id else None
        if not user:
            raise HTTPException(404, detail="User not found")
        if not verify_password(body.old_password, user.password_hash):
            raise HTTPException(400, detail="Current password is incorrect")
        if len(body.new_password) < 8:
            raise HTTPException(422, detail="New password must be at least 8 characters")
        user.password_hash = hash_password(body.new_password)
        user.must_change_password = False
        repo.add(user)
        _audit(repo, "user_password_changed", identity["actor"])
        return {"message": "Password changed successfully"}

    @router.get("/auth/permissions")
    def get_permissions():
        return {
            "roles": list(ROLE_LEVELS.keys()),
            "role_levels": ROLE_LEVELS,
            "permissions": PERMISSIONS,
        }

    @router.get("/auth/users")
    def list_users(repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_require("admin"))):
        users = repo.list_users()
        return {
            "items": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "role": u.role,
                    "is_active": u.is_active,
                    "must_change_password": u.must_change_password,
                    "locked_until": u.locked_until.isoformat() if u.locked_until else None,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ],
            "count": len(users),
        }

    @router.post("/auth/users")
    def create_user_endpoint(body: UserCreateRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        existing = repo.get_user_by_email_or_username(body.username) or repo.get_user_by_email_or_username(body.email)
        if existing:
            raise HTTPException(409, detail="A user with that username or email already exists")
        temp_pwd = body.temp_password or generate_temp_password(14)
        user = repo.create_user(
            username=body.username,
            email=body.email,
            password_hash=hash_password(temp_pwd),
            role=body.role,
        )
        user.must_change_password = True
        repo.add(user)
        _audit(repo, "user_created", identity["actor"], details={"username": user.username, "role": user.role})
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "must_change_password": True,
            },
            "temporary_password": temp_pwd,
            "message": "User created. Share this temporary password securely with the user; they must change it on first login.",
        }

    @router.post("/auth/users/{user_id}/reset-password")
    def admin_reset_password(user_id: str, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        user = repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(404, detail="User not found")
        temp_pwd = generate_temp_password(14)
        user.password_hash = hash_password(temp_pwd)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.must_change_password = True
        repo.add(user)
        _audit(repo, "user_password_reset_by_admin", identity["actor"], details={"target_user": user.username})
        return {
            "temporary_password": temp_pwd,
            "message": "Password reset. Provide this temporary password to the user; forced change is active.",
        }

    @router.delete("/auth/users/{user_id}")
    def delete_user(user_id: str, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        user = repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(404, detail="User not found")
        if user.role == "admin":
            active_admins = [u for u in repo.list_users() if u.role == "admin" and u.is_active and u.id != user_id]
            if not active_admins:
                raise HTTPException(409, detail="Cannot delete or deactivate the last active admin for this company")
        repo.soft_delete(UserRow, user_id, actor=identity["actor"], reason="Deleted by admin")
        return {"message": "User deleted successfully", "id": user_id}

    @router.get("/auth/api-keys")
    def list_api_keys(repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_require("admin"))):
        keys = repo.list_api_keys()
        return {
            "items": [
                {
                    "id": k.id,
                    "name": k.name,
                    "prefix": k.prefix,
                    "role": k.role,
                    "scopes": k.scopes,
                    "created_at": k.created_at.isoformat() if k.created_at else None,
                    "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                }
                for k in keys
            ],
            "count": len(keys),
        }

    @router.post("/auth/api-keys")
    def create_api_key_endpoint(body: ApiKeyCreateRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        if body.role in ("reviewer", "admin"):
            raise HTTPException(400, detail="Machine API keys can only have viewer or analyst role; reviewer and admin are prohibited.")
        raw_key, prefix, key_hash = generate_machine_api_key()
        row = repo.create_api_key(
            name=body.name,
            key_hash=key_hash,
            prefix=prefix,
            role=body.role,
            scopes=body.scopes,
        )
        _audit(repo, "api_key_created", identity["actor"], details={"key_id": row.id, "name": row.name, "prefix": prefix})
        return {
            "id": row.id,
            "name": row.name,
            "prefix": prefix,
            "role": row.role,
            "api_key": raw_key,
            "message": "Copy this API key now. It will not be shown again.",
        }

    @router.delete("/auth/api-keys/{key_id}")
    def revoke_api_key(key_id: str, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        success = repo.revoke_api_key(key_id)
        if not success:
            raise HTTPException(404, detail="API key not found or already revoked")
        _audit(repo, "api_key_revoked", identity["actor"], details={"key_id": key_id})
        return {"message": "API key revoked successfully", "id": key_id}

    # --- Workspaces, Companies & Projects Endpoints ---

    @router.get("/companies")
    def list_companies_endpoint(repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_auth)):
        with repo.sessions() as session:
            rows = session.scalars(select(CompanyRow)).all()
        return {"items": [{"id": r.id, "name": r.name} for r in rows], "count": len(rows)}

    @router.post("/companies")
    def create_company_endpoint(body: CompanyCreateRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        company_id = re.sub(r"[^a-zA-Z0-9_-]", "_", body.company_id.strip())
        repo.create_company(company_id, body.company_name.strip())
        company_repo = Repository(str(repo.engine.url), company_id=company_id, engine=repo.engine)
        ws = WorkspaceRow(id=f"workspace-{company_id}", name="Default workspace")
        company_repo.add(ws)
        proj = ProjectRow(id=f"project-{company_id}", workspace_id=ws.id, name="Default project")
        company_repo.add(proj)
        admin_user_data = None
        if body.admin_username and body.admin_email and body.admin_password:
            admin_user = company_repo.create_user(
                username=body.admin_username.strip(),
                email=body.admin_email.strip(),
                password_hash=hash_password(body.admin_password),
                role="admin",
            )
            admin_user.must_change_password = False
            admin_user.last_project_id = proj.id
            company_repo.add(admin_user)
            admin_user_data = {"id": admin_user.id, "username": admin_user.username, "email": admin_user.email}
        _audit(repo, "company_created", identity["actor"], details={"company_id": company_id, "name": body.company_name})
        return {
            "id": company_id,
            "name": body.company_name,
            "workspace_id": ws.id,
            "project_id": proj.id,
            "admin_user": admin_user_data,
        }

    @router.get("/workspaces")
    def list_workspaces(repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_require("viewer"))):
        rows = repo.list_rows(WorkspaceRow)
        return {"items": [{"id": r.id, "name": r.name} for r in rows], "count": len(rows)}

    @router.post("/workspaces")
    def create_workspace_endpoint(body: WorkspaceCreateRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("analyst"))):
        row = WorkspaceRow(id=str(uuid.uuid4()), name=body.name.strip())
        repo.add(row)
        _audit(repo, "workspace_created", identity["actor"], details={"name": body.name})
        return {"id": row.id, "name": row.name}

    @router.get("/projects")
    def list_projects_endpoint(workspace_id: str | None = None, repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_require("viewer"))):
        rows = repo.list_rows(ProjectRow)
        if workspace_id:
            rows = [r for r in rows if r.workspace_id == workspace_id]
        return {"items": [{"id": r.id, "workspace_id": r.workspace_id, "name": r.name} for r in rows], "count": len(rows)}

    @router.post("/projects")
    def create_project_endpoint(body: ProjectCreateRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("analyst"))):
        ws_id = body.workspace_id
        if not ws_id:
            workspaces = repo.list_rows(WorkspaceRow)
            if workspaces:
                ws_id = workspaces[0].id
            else:
                ws = WorkspaceRow(id=f"workspace-{repo.company_id}", name="Default workspace")
                repo.add(ws)
                ws_id = ws.id
        row = ProjectRow(id=str(uuid.uuid4()), workspace_id=ws_id, name=body.name.strip())
        repo.add(row)
        _audit(repo, "project_created", identity["actor"], details={"name": body.name, "workspace_id": ws_id})
        return {"id": row.id, "workspace_id": row.workspace_id, "name": row.name}

    @router.get("/projects/{project_id}")
    def get_project_endpoint(project_id: str, repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_require("viewer"))):
        proj = repo.get(ProjectRow, project_id)
        if not proj:
            raise HTTPException(404, detail="Project not found")
        return {"id": proj.id, "workspace_id": proj.workspace_id, "name": proj.name}

    @router.get("/projects/{project_id}/datasets")
    def list_project_datasets_endpoint(project_id: str, repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_require("viewer"))):
        sources = [s for s in repo.list_rows(DataSourceRow) if s.project_id == project_id]
        return {"items": [{"id": s.id, "name": s.name, "source_type": s.source_type} for s in sources], "count": len(sources)}

    @router.get("/users/me")
    def get_current_user_profile(repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_auth)):
        user_id = identity.get("user_id")
        user = repo.get_user_by_id(user_id) if user_id else None
        return {
            "id": user.id if user else identity.get("sub", "unknown"),
            "username": user.username if user else identity.get("username", "api"),
            "email": user.email if user else identity.get("email", ""),
            "role": identity["role"],
            "company_id": identity["company_id"],
            "must_change_password": user.must_change_password if user else False,
            "last_project_id": user.last_project_id if user else None,
        }

    @router.put("/users/me/preferences")
    def update_user_preferences(body: UserPreferencesRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_auth)):
        user_id = identity.get("user_id")
        user = repo.get_user_by_id(user_id) if user_id else None
        if user:
            user.last_project_id = body.last_project_id
            repo.add(user)
        return {"last_project_id": body.last_project_id}

    # --- Admin Settings & Scheduler Endpoints ---

    @router.get("/admin/settings")
    def get_admin_settings(repo: Repository = Depends(_repository), _identity: dict[str, Any] = Depends(_require("admin"))):
        setting = repo.get_setting("require_reviewer_mapping_approval")
        val = bool(setting.get("value", False)) if setting else False
        return {"require_reviewer_mapping_approval": val}

    @router.put("/admin/settings")
    def update_admin_settings(body: AdminSettingsRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        repo.set_setting("require_reviewer_mapping_approval", {"value": body.require_reviewer_mapping_approval})
        _audit(repo, "admin_settings_updated", identity["actor"], details={"require_reviewer_mapping_approval": body.require_reviewer_mapping_approval})
        return {"require_reviewer_mapping_approval": body.require_reviewer_mapping_approval}

    @router.get("/admin/scheduler")
    def get_scheduler_status(_identity: dict[str, Any] = Depends(_require("admin"))):
        return scheduler.status()

    @router.put("/admin/scheduler")
    def toggle_scheduler(body: SchedulerToggleRequest, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("admin"))):
        res = scheduler.toggle(body.enabled)
        _audit(repo, "scheduler_toggled", identity["actor"], details={"enabled": body.enabled})
        return res

    @router.get("/health")
    def health(_identity: dict[str, str] = Depends(_require("viewer"))):
        return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

    @router.get("/quality", response_model=Page[QualityItem])
    def quality(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session:
            rows = session.scalars(select(QualitySnapshotRow).order_by(QualitySnapshotRow.observed_at.desc())).all()
        age = load_settings().data.freshness_max_age_hours
        now = datetime.now(timezone.utc)
        items = [QualityItem(source=row.source, observed_at=row.observed_at, row_count=row.row_count,
            null_rates=row.null_rates, drift=row.drift,
            fresh=(now - (row.observed_at.replace(tzinfo=timezone.utc) if row.observed_at.tzinfo is None else row.observed_at)).total_seconds() <= age * 3600)
            for row in rows]
        return Page[QualityItem](items=items, count=len(items))

    @router.get("/incidents", response_model=Page[Incident])
    def incidents(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session:
            rows = session.scalars(select(IncidentRow).order_by(IncidentRow.occurred_at.desc())).all()
        return Page[Incident](items=[_map(r, Incident, title=r.title, description="", source=r.source,
            occurred_at=r.occurred_at) for r in rows], count=len(rows))

    @router.get("/incidents/{incident_id}", response_model=IncidentDetail)
    def incident_detail(incident_id: Annotated[str, PathParam(min_length=1, max_length=128)], repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session:
            row = session.get(IncidentRow, incident_id)
            if not row: raise HTTPException(404, "Incident not found")
            evidence = session.scalars(select(EvidenceRow).where(EvidenceRow.incident_id == incident_id)).all()
            hypotheses = session.scalars(select(HypothesisRow).where(HypothesisRow.incident_id == incident_id)).all()
            prediction = session.get(PredictionRow, row.prediction_id) if row.prediction_id else None
        data = _map(row, Incident, title=row.title, description="", source=row.source, occurred_at=row.occurred_at).model_dump()
        evidence_items = [_map(e, Evidence, evidence_type="observed", source=e.source,
            record_refs=e.record_refs, observed_at=e.observed_at, facts={}) for e in evidence]
        hypothesis_items = [_map(h, Hypothesis, statement=h.statement, status=h.status, source="stored") for h in hypotheses]
        limits = list(row.payload.get("limitations", []))
        for item in evidence:
            limits.extend(item.payload.get("limitations", []))
        for item in hypotheses:
            limits.extend(item.payload.get("missing_evidence", []))
        explanation = {"stored_explanation": row.payload.get("explanation", {}),
            "prediction": _payload(prediction) if prediction else None,
            "evidence_facts": [item.facts for item in evidence_items],
            "hypothesis_statuses": [item.status.value for item in hypothesis_items]}
        return IncidentDetail(**data, evidence=evidence_items, hypotheses=hypothesis_items,
            explanation=explanation, limitations=list(dict.fromkeys(str(x) for x in limits)))

    def list_rows(model: Any, schema: type[BaseModel], defaults: Any, repo: Repository) -> Any:
        with repo.sessions() as session: rows = session.scalars(select(model).order_by(model.created_at.desc())).all()
        return Page[schema](items=[_map(r, schema, **defaults(r)) for r in rows], count=len(rows))

    @router.get("/predictions", response_model=Page[Prediction])
    def predictions(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        return list_rows(PredictionRow, Prediction, lambda r: {"target": r.target, "value": r.value,
            "model_version_id": r.model_version_id, "source": r.source, "record_refs": r.record_refs,
            "predicted_at": r.predicted_at, "confidence": r.confidence, "limitations": []}, repo)

    @router.get("/anomalies")
    def anomalies(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session:
            rows = session.scalars(select(AnomalyRow)).all()
        sev_rank = {"CRITICAL": 3, "HIGH": 2, "LOW": 1}
        def sort_key(r):
            p = r.payload or {}
            s_score = sev_rank.get(str(p.get("severity", "LOW")).upper(), 0)
            score_val = float(p.get("score") or p.get("anomaly_score") or 0.0)
            return (s_score, score_val)
        sorted_rows = sorted(rows, key=sort_key, reverse=True)
        return {"items": [{**_payload(r), "source": r.source, "detector": r.detector, "record_ref": r.record_ref,
                            "feature": r.feature, "observed_value": r.observed_value, "baseline": r.baseline} for r in sorted_rows], "count": len(sorted_rows)}

    @router.post("/hypotheses", response_model=Hypothesis, status_code=201)
    def create_hypothesis(body: HypothesisCreate, repo: Repository = Depends(_repository), identity: dict[str, str] = Depends(_require("analyst"))):
        with repo.sessions() as session:
            if not session.get(IncidentRow, body.incident_id): raise HTTPException(404, "Incident not found")
        item = Hypothesis(statement=body.statement, source=body.source, record_refs=body.record_refs)
        repo.add(HypothesisRow(id=item.id, incident_id=body.incident_id, statement=item.statement,
            status=item.status.value, payload=item.model_dump(mode="json")))
        _audit(repo, "hypothesis_created", identity["actor"], source=item.source, record_refs=item.record_refs)
        return item

    @router.get("/hypotheses", response_model=Page[Hypothesis])
    def hypotheses(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session: rows = session.scalars(select(HypothesisRow).order_by(HypothesisRow.created_at.desc())).all()
        items = [_map(row, Hypothesis, statement=row.statement, status=row.status, source="stored") for row in rows]
        return Page[Hypothesis](items=items, count=len(items))

    @router.post("/hypotheses/{hypothesis_id}/review", response_model=Hypothesis)
    def review_hypothesis(hypothesis_id: Annotated[str, PathParam(min_length=1, max_length=128)], body: HypothesisReview, repo: Repository = Depends(_repository), identity: dict[str, str] = Depends(_require("analyst"))):
        with repo.sessions() as session: row = session.get(HypothesisRow, hypothesis_id)
        if not row: raise HTTPException(404, "Hypothesis not found")
        case = HypothesisCase.model_validate(row.payload)
        try:
            HypothesisService().transition(case, body.status, user_id=identity["actor"], role=identity["role"], rationale=body.rationale)
        except PermissionError as exc: raise HTTPException(403, str(exc)) from exc
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc
        row.status = case.status.value
        row.payload = case.model_dump(mode="json")
        repo.add(row)
        _audit(repo, "hypothesis_reviewed", identity["actor"], source=case.source, record_refs=[case.id], details={"new_status": case.status.value})
        return Hypothesis(id=case.id, statement=case.statement, status=case.status, source=case.source,
            review_history=case.review_history)

    @router.post("/hypotheses/{hypothesis_id}/confirm", response_model=Hypothesis)
    def confirm_hypothesis(hypothesis_id: Annotated[str, PathParam(min_length=1, max_length=128)], body: DecisionBody, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("reviewer"))):
        if identity.get("is_machine_key"):
            raise HTTPException(403, detail="Machine API keys can never confirm hypotheses or approve actions")
        with repo.sessions() as session: row = session.get(HypothesisRow, hypothesis_id)
        if not row: raise HTTPException(404, "Hypothesis not found")
        case = HypothesisCase.model_validate(row.payload)
        rat = body.effective_rationale
        try: HypothesisService().transition(case, HypothesisStatus.CONFIRMED, user_id=identity["actor"], role=identity["role"], rationale=rat)
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc
        row.status = case.status.value
        row.payload = case.model_dump(mode="json")
        repo.add(row)
        _audit(repo, "hypothesis_confirmed", identity["actor"], source=case.source, record_refs=[case.id])
        return Hypothesis(id=case.id, statement=case.statement, status=case.status, source=case.source, review_history=case.review_history)

    @router.get("/recommendations")
    def recommendations(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session: rows = session.scalars(select(RecommendationRow).order_by(RecommendationRow.created_at.desc())).all()
        return {"items": [{**_payload(r), "source": r.source, "action": r.action} for r in rows], "count": len(rows)}

    @router.post("/recommendations/playbooks", status_code=201)
    def create_driver_playbook(body: PlaybookRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("analyst"))):
        incident = repo.get(IncidentRow, body.incident_id)
        if not incident:
            raise HTTPException(404, "Incident not found")
        version = repo.get(DatasetVersionRow, incident.dataset_version_id)
        source_id = (version.payload or {}).get("source_id") if version else None
        source = repo.get(DataSourceRow, source_id) if source_id else None
        accepted = [item for item in repo.list_rows(MappingVersionRow, limit=10000)
                    if source and item.data_source_id == source.id and item.status == "ACCEPTED"]
        mapping = max(accepted, key=lambda item: item.version, default=None)
        available_roles = set((mapping.mapping or {}).get("mappings", {})) if mapping else set()
        evidence = [item for item in repo.list_rows(EvidenceRow, limit=10000) if item.incident_id == incident.id]
        allowed_refs = {item.id for item in evidence} | {ref for item in evidence for ref in item.record_refs}
        if not set(body.evidence_refs).issubset(allowed_refs):
            raise HTTPException(422, "Evidence refs must belong to the selected incident")
        recommendation = recommend_for_driver(driver={"dimension": body.driver_type, "value": body.driver_value},
            available_roles=available_roles, evidence_refs=body.evidence_refs)
        if recommendation.get("status") != "PROPOSED":
            return recommendation
        rec_id = str(uuid.uuid4())
        recommendation.update({"id": rec_id, "incident_id": incident.id, "source": incident.source,
            "created_by": identity["actor"], "status": "PROPOSED"})
        repo.add(RecommendationRow(id=rec_id, incident_id=incident.id, hypothesis_id=None,
            source=incident.source, action=recommendation["action"], payload=recommendation))
        _audit(repo, "recommendation_playbook_created", identity["actor"], source=incident.source,
               record_refs=[rec_id, *body.evidence_refs], details={"driver_type": body.driver_type})
        return recommendation

    @router.post("/recommendations/what-if")
    def recommendation_what_if(body: WhatIfRequest,
            _identity: dict[str, str] = Depends(_require("analyst"))):
        try:
            return compare_scenarios(affected_order_count=body.affected_order_count,
                calibrated_delay_probability=body.calibrated_delay_probability,
                probability_calibrated=body.probability_calibrated,
                scenarios=[item.model_dump() for item in body.scenarios])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def decide_approval(approval_id: str, approved: bool, body: DecisionBody, repo: Repository, identity: dict[str, str]):
        with repo.sessions() as session: row = session.get(ApprovalRow, approval_id)
        if not row: raise HTTPException(404, "Approval not found")
        if row.status != "pending": raise HTTPException(409, "Approval is already reviewed")
        row.status = "approved" if approved else "rejected"
        row.reviewer_id = identity["actor"]
        row.reviewed_at = datetime.now(timezone.utc)
        row.payload = {**row.payload, "approved": approved, "rationale": body.rationale}
        repo.add(row)
        _audit(repo, f"approval_{row.status}", identity["actor"], record_refs=[approval_id])
        return {"id": row.id, "recommendation_id": row.recommendation_id, "status": row.status,
                "reviewer_id": row.reviewer_id, "reviewed_at": row.reviewed_at, "rationale": body.rationale}

    @router.get("/approvals")
    def approvals(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session: rows = session.scalars(select(ApprovalRow).order_by(ApprovalRow.created_at.desc())).all()
        return {"items": [{**_payload(r), "recommendation_id": r.recommendation_id, "reviewer_id": r.reviewer_id,
                            "status": r.status, "reviewed_at": r.reviewed_at} for r in rows], "count": len(rows)}

    @router.post("/approvals", status_code=201)
    def create_approval(body: ApprovalCreate, repo: Repository = Depends(_repository), identity: dict[str, str] = Depends(_require("analyst"))):
        with repo.sessions() as session:
            if not session.get(RecommendationRow, body.recommendation_id): raise HTTPException(404, "Recommendation not found")
        item = Approval(recommendation_id=body.recommendation_id, status="pending", rationale="Pending reviewer decision")
        repo.add(ApprovalRow(id=item.id, recommendation_id=item.recommendation_id, status="pending",
            payload=item.model_dump(mode="json")))
        _audit(repo, "approval_requested", identity["actor"], record_refs=[item.recommendation_id])
        return item

    @router.post("/approvals/{approval_id}/approve")
    def approve(approval_id: Annotated[str, PathParam(min_length=1, max_length=128)], body: DecisionBody, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("reviewer"))):
        if identity.get("is_machine_key"):
            raise HTTPException(403, detail="Machine API keys can never confirm hypotheses or approve actions")
        return decide_approval(approval_id, True, body, repo, identity)

    @router.post("/actions/{action_id}/approve")
    def approve_action(action_id: Annotated[str, PathParam(min_length=1, max_length=128)], body: DecisionBody, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("reviewer"))):
        if identity.get("is_machine_key"):
            raise HTTPException(403, detail="Machine API keys can never confirm hypotheses or approve actions")
        with repo.sessions() as session:
            approval = session.get(ApprovalRow, action_id)
            if not approval:
                action = session.get(ActionRow, action_id)
                if action and action.approval_id:
                    approval = session.get(ApprovalRow, action.approval_id)
        if not approval:
            raise HTTPException(404, "Approval or Action not found")
        return decide_approval(approval.id, True, body, repo, identity)

    @router.post("/approvals/{approval_id}/reject")
    def reject(approval_id: Annotated[str, PathParam(min_length=1, max_length=128)], body: DecisionBody, repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("reviewer"))):
        if identity.get("is_machine_key"):
            raise HTTPException(403, detail="Machine API keys can never confirm hypotheses or approve actions")
        return decide_approval(approval_id, False, body, repo, identity)

    @router.get("/actions")
    def actions(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session: rows = session.scalars(select(ActionRow).order_by(ActionRow.created_at.desc())).all()
        return {"items": [{**_payload(r), "recommendation_id": r.recommendation_id, "approval_id": r.approval_id,
                            "source": r.source, "status": r.status, "dry_run": r.dry_run} for r in rows], "count": len(rows)}

    @router.post("/actions", status_code=201)
    def create_action(body: ActionCreate, repo: Repository = Depends(_repository), identity: dict[str, str] = Depends(_require("analyst"))):
        with repo.sessions() as session:
            recommendation = session.get(RecommendationRow, body.recommendation_id)
            approval = session.get(ApprovalRow, body.approval_id) if body.approval_id else None
        if not recommendation: raise HTTPException(404, "Recommendation not found")
        if body.action_class == "HIGH_IMPACT" and (approval is None or approval.status != "approved"):
            raise HTTPException(409, "HIGH_IMPACT action requires a recorded approved approval")
        blocked = bool(getattr(app.state, "kill_switch", load_settings().kill_switch))
        status = "BLOCKED_KILL_SWITCH" if blocked else "DRY_RUN"
        action_id = str(uuid.uuid4())
        response = Action(id=action_id, recommendation_id=body.recommendation_id,
            approval_id=body.approval_id, source=recommendation.source, dry_run=True, status=status)
        repo.add(ActionRow(id=response.id, recommendation_id=response.recommendation_id,
            approval_id=response.approval_id, source=response.source, dry_run=True,
            status=response.status, payload={**response.model_dump(mode="json"),
                                             "action_class": body.action_class}))
        _audit(repo, "action_dry_run_recorded", identity["actor"], source=response.source,
            record_refs=[response.id, response.recommendation_id], details={"action_class": body.action_class, "status": status})
        return response

    @router.get("/actions/history")
    def action_history(repo: Repository = Depends(_repository), identity: dict[str, str] = Depends(_require("viewer"))):
        return actions(repo, identity)

    @router.post("/actions/{action_id}/verification")
    def verify_action_execution(action_id: Annotated[str, PathParam(min_length=1, max_length=128)],
            body: ActionVerificationRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("reviewer"))):
        try:
            result = record_execution_verification(repo, action_id, executed=body.executed,
                verified=body.verified, result=body.result, actor=identity["actor"],
                audit_log=AuditLog(load_settings().audit.log_path))
            _audit(repo, "action_execution_status_recorded", identity["actor"],
                   record_refs=[action_id], details={"status": result["status"],
                       "execution_status": result["execution_status"]})
            return result
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/alerts")
    def alerts(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session:
            rows = session.scalars(select(AuditEventRow).where(AuditEventRow.event_type.like("%alert%")).order_by(AuditEventRow.occurred_at.desc())).all()
        return {"items": [_payload(r) | {"event_type": r.event_type, "source": r.source, "occurred_at": r.occurred_at} for r in rows], "count": len(rows)}

    def local_alert_manager() -> AlertManager:
        history_path = getattr(app.state, "alert_history_path", Path("data/processed/alert_history.jsonl"))
        return AlertManager(channels={}, history_path=history_path)

    @router.get("/alerts/history")
    def alert_history(limit: int = 100, _identity: dict[str, str] = Depends(_require("viewer"))):
        if limit < 1 or limit > 1000:
            raise HTTPException(422, "limit must be between 1 and 1000")
        events = local_alert_manager().history()
        return {"items": events[-limit:], "count": len(events)}

    @router.post("/alerts/{group_id}/acknowledge")
    def acknowledge_alert(group_id: Annotated[str, PathParam(min_length=1, max_length=128)],
            body: AlertAcknowledgeRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("analyst"))):
        try:
            result = local_alert_manager().acknowledge(group_id, actor=identity["actor"], reason=body.reason)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        _audit(repo, "alert_acknowledged", identity["actor"], record_refs=[group_id])
        return result

    @router.post("/alerts/{group_id}/assign")
    def assign_alert(group_id: Annotated[str, PathParam(min_length=1, max_length=128)],
            body: AlertAssignmentRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("analyst"))):
        try:
            result = local_alert_manager().assign(group_id, actor=identity["actor"], assigned_to=body.assigned_to)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        _audit(repo, "alert_assigned", identity["actor"], record_refs=[group_id])
        return result

    @router.get("/connectors/health")
    def connector_health(_identity: dict[str, str] = Depends(_require("admin"))):
        configured = load_settings().connectors
        checks = [FolderImportConnector(configured.scheduled_folder,
            chunksize=configured.folder_chunk_rows).health_check()]
        rest_url = os.getenv(configured.rest_endpoint_env)
        if rest_url:
            checks.append(RestPollingConnector(rest_url, token_env=configured.rest_token_env,
                timeout_seconds=configured.rest_timeout_seconds).health_check())
        else:
            checks.append({"name": "rest_polling", "status": "NOT_CONFIGURED",
                           "detail": "REST endpoint environment variable is missing"})
        if os.getenv(configured.database_url_env):
            checks.append(DatabaseImportConnector(url_env=configured.database_url_env,
                table_name=configured.database_table, chunksize=configured.database_chunk_rows).health_check())
        else:
            checks.append({"name": "database_import", "status": "NOT_CONFIGURED",
                           "detail": "Database URL environment variable is missing"})
        checks.extend([SMTPNotificationAdapter(enabled_env=configured.notifications_enabled_env).health_check(),
                       WebhookNotificationAdapter(enabled_env=configured.notifications_enabled_env).health_check()])
        return {"items": [check.__dict__ if hasattr(check, "__dict__") else check for check in checks],
                "extensions": UNBUILT_CONNECTOR_EXTENSIONS}

    @router.get("/incidents/{incident_id}/graph")
    def incident_graph(incident_id: Annotated[str, PathParam(min_length=1, max_length=128)], repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session:
            incident = session.get(IncidentRow, incident_id)
            if not incident: raise HTTPException(404, "Incident not found")
            evidence = session.scalars(select(EvidenceRow).where(EvidenceRow.incident_id == incident_id)).all()
            hypotheses = session.scalars(select(HypothesisRow).where(HypothesisRow.incident_id == incident_id)).all()
            recs = session.scalars(select(RecommendationRow).where(RecommendationRow.incident_id == incident_id)).all()
        nodes = [{"id": incident.id, "type": "INCIDENT", "source": incident.source}]
        edges = []
        for row, kind in [(x, "EVIDENCE") for x in evidence] + [(x, "HYPOTHESIS") for x in hypotheses] + [(x, "RECOMMENDATION") for x in recs]:
            nodes.append({"id": row.id, "type": kind, "source": row.source if hasattr(row, "source") else "stored"})
            edges.append({"from": incident.id, "to": row.id, "type": "HAS_EVIDENCE" if kind == "EVIDENCE" else "HAS_HYPOTHESIS" if kind == "HYPOTHESIS" else "HAS_RECOMMENDATION", "meaning": "Stored relationship to this incident", "source_ref": row.id, "status": "ESTABLISHED"})
        return {"nodes": nodes, "edges": edges}

    @router.get("/models", response_model=Page[ModelVersion])
    def models(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        return list_rows(ModelVersionRow, ModelVersion, lambda r: {"name": r.name, "version": r.version,
            "artifact_hash": r.artifact_hash, "trained_at": r.trained_at or datetime.now(timezone.utc),
            "training_data_version": r.training_data_version, "parameters": {}, "limitations": []}, repo)

    @router.get("/models/{model_id}/metrics")
    def model_metrics(model_id: Annotated[str, PathParam(min_length=1, max_length=128)], repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        with repo.sessions() as session: row = session.get(ModelVersionRow, model_id)
        if not row: raise HTTPException(404, "Model version not found")
        return {"model_version_id": model_id, "metrics": row.payload.get("metrics", {}), "limitations": row.payload.get("limitations", [])}

    @router.get("/models/{model_version}/evaluation-report")
    def get_model_evaluation_report(
        model_version: Annotated[str, PathParam(min_length=1, max_length=200)],
        _identity: dict[str, str] = Depends(_require("viewer")),
    ):
        report_file = Path("models/evaluations") / f"{model_version}.json"
        if report_file.exists():
            try:
                return json.loads(report_file.read_text(encoding="utf-8"))
            except Exception as exc:
                raise HTTPException(500, detail="Failed to read evaluation report") from exc
        registry_path = Path("src/ml/model_registry.json")
        if registry_path.exists():
            reg = json.loads(registry_path.read_text(encoding="utf-8"))
            for m in reg.get("models", []):
                if m.get("version") == model_version:
                    return {
                        "model_version": model_version,
                        "dataset": m.get("dataset"),
                        "data_version": m.get("data_hash", "UNKNOWN"),
                        "data_hash": m.get("data_hash", "UNKNOWN"),
                        "mapping_version": m.get("config", {}).get("mapping_version", "v1"),
                        "seed": m.get("config", {}).get("random_seed", 42),
                        "metrics": m.get("metrics", {}),
                        "evaluation_context": m.get("evaluation_context", {}),
                        "limitations": ["Evaluation describes this chronological holdout only."],
                    }
        raise HTTPException(404, detail="Reproducible evaluation report not found")

    @router.get("/outcomes", response_model=Page[Outcome])
    def outcomes(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("viewer"))):
        return list_rows(OutcomeRow, Outcome, lambda r: {"action_id": r.action_id, "source": r.source,
            "record_refs": [], "observed_at": r.observed_at, "facts": {}, "limitations": []}, repo)

    @router.get("/evaluation/alerts")
    def alert_evaluation(repo: Repository = Depends(_repository),
                         _identity: dict[str, str] = Depends(_require("viewer"))):
        return evaluate_repository_alerts(repo)

    @router.get("/evaluation/outcomes")
    def outcomes_evaluation(repo: Repository = Depends(_repository),
                            _identity: dict[str, str] = Depends(_require("viewer"))):
        return evaluate_company_outcomes(repo)

    @router.post("/outcomes", status_code=201)
    def create_observed_outcome(body: OutcomeRecordRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("analyst"))):
        has_verified_label = body.verified_alert_label is not None or body.alert_was_raised is not None
        if has_verified_label and ROLES[identity["role"]] < ROLES["reviewer"]:
            raise HTTPException(403, detail="Reviewer role required to verify alert labels")
        try:
            result = record_observed_outcome(repo, action_id=body.action_id, source=body.source,
                observed_at=body.observed_at, facts=body.facts, record_refs=body.record_refs,
                prediction_refs=body.prediction_refs, recommendation_refs=body.recommendation_refs,
                result=body.result, audit_log=AuditLog(load_settings().audit.log_path), actor=identity["actor"],
                verified_alert_label=body.verified_alert_label, alert_was_raised=body.alert_was_raised,
                label_verified_by=identity["actor"] if has_verified_label else None)
            _audit(repo, "outcome_recorded", identity["actor"], source=body.source,
                   record_refs=body.record_refs, details={"action_id": body.action_id,
                       "prediction_refs": body.prediction_refs, "recommendation_refs": body.recommendation_refs,
                       "verified_alert_label": has_verified_label})
            return result
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/models/registry/comparisons/{candidate_version}")
    def model_candidate_comparison(candidate_version: Annotated[str, PathParam(min_length=1, max_length=200)],
            _identity: dict[str, str] = Depends(_require("analyst"))):
        settings = load_settings()
        try:
            return compare_candidate(Path("src/ml/model_registry.json"), candidate_version,
                                     acceptance=settings.model_promotion.model_dump())
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/models/registry/{model_version}/set-current")
    def set_initial_model_current(model_version: Annotated[str, PathParam(min_length=1, max_length=200)],
            body: ReasonRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("reviewer"))):
        try:
            result = set_initial_current(Path("src/ml/model_registry.json"), model_version,
                                         reviewer=identity["actor"], reason=body.reason)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        _audit(repo, "model_initial_version_approved", identity["actor"], record_refs=[model_version],
               details={"reason": body.reason})
        return result

    @router.post("/models/registry/{candidate_version}/promote")
    def promote_model_version(candidate_version: Annotated[str, PathParam(min_length=1, max_length=200)],
            body: ReasonRequest, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("reviewer"))):
        settings = load_settings()
        try:
            result = promote_candidate(Path("src/ml/model_registry.json"), candidate_version,
                acceptance=settings.model_promotion.model_dump(), reviewer=_identity["actor"], reason=body.reason)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        _audit(repo, "model_promoted", _identity["actor"], record_refs=[candidate_version],
               details={"reason": body.reason, "criteria": settings.model_promotion.model_dump()})
        return result

    @router.post("/models/registry/rollback")
    def rollback_model_version(body: ModelRollbackRequest, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("reviewer"))):
        try:
            result = rollback_model(Path("src/ml/model_registry.json"), body.model_key,
                                    reviewer=_identity["actor"], reason=body.reason)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        _audit(repo, "model_rolled_back", _identity["actor"], record_refs=[body.model_key], details={"reason": body.reason})
        return result

    @router.get("/audit", response_model=Page[AuditEvent])
    def audit_events(
        category: str | None = None,
        event_type: str | None = None,
        repo: Repository = Depends(_repository),
        _identity: dict[str, str] = Depends(_require("admin")),
    ):
        with repo.sessions() as session:
            rows = list(session.scalars(select(AuditEventRow).order_by(AuditEventRow.occurred_at.desc())).all())
        category_prefixes = {
            "source": ("data_source_", "dataset_"),
            "mapping": ("mapping_",),
            "rule": ("risk_scoring_config_", "rule_config_"),
            "model": ("model_",),
            "permission": ("permission_policy_",),
            "prediction": ("prediction_",),
            "investigation": ("incident_", "hypothesis_"),
            "action": ("action_", "kill_switch_"),
        }
        if event_type:
            rows = [r for r in rows if r.event_type == event_type]
        if category and category.lower() in category_prefixes:
            prefixes = category_prefixes[category.lower()]
            rows = [r for r in rows if any(r.event_type.startswith(p) for p in prefixes)]
        items = [AuditEvent(id=r.id, event_type=r.event_type, actor=r.actor, source=r.source,
            occurred_at=r.occurred_at, record_refs=r.payload.get("record_refs", []), details=r.payload.get("details", {}),
            previous_hash=r.previous_hash, event_hash=r.event_hash) for r in rows]
        return Page[AuditEvent](items=items, count=len(items))

    @router.put("/admin/kill-switch")
    @router.post("/system/kill-switch")
    @router.put("/system/kill-switch")
    def toggle_kill_switch(body: KillSwitchBody, repo: Repository = Depends(_repository), identity: dict[str, str] = Depends(_require("admin"))):
        repo.set_kill_switch(body.enabled, body.reason)
        app.state.kill_switch = body.enabled
        _audit(repo, "kill_switch_toggled", identity["actor"], details={"enabled": body.enabled, "reason": body.reason})
        return {"enabled": body.enabled, "reason": body.reason}

    @router.put("/admin/permission-policy")
    def update_permission_policy(body: PermissionPolicyRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("admin"))):
        previous = dict(app.state.role_policy)
        app.state.role_policy = dict(body.role_levels)
        _audit(repo, "permission_policy_changed", identity["actor"],
               details={"previous_role_levels": previous, "new_role_levels": body.role_levels})
        return {"role_levels": app.state.role_policy, "updated": True}

    @router.get("/admin/kill-switch")
    @router.get("/system/kill-switch")
    def get_kill_switch(repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("admin"))):
        return {"enabled": bool(repo.get_kill_switch())}

    @router.post("/datasets/upload", status_code=201)
    async def upload_dataset(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        dataset_name: Annotated[str | None, Form()] = None,
        repo: Repository = Depends(_repository),
        identity: dict[str, Any] = Depends(_require("analyst")),
    ):
        filename = file.filename or "dataset.csv"
        settings = load_settings().uploads
        try:
            upload_root, temp_path = _tenant_paths(repo, filename)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        allowed = {".csv", ".xlsx", ".xlsm", ".json", ".jsonl", ".zip"}
        if Path(filename).suffix.lower() not in allowed:
            raise HTTPException(400, detail="Allowed file types: CSV, XLSX, JSON, ZIP")
        max_size = settings.max_size_bytes
        if dataset_service.MAX_UPLOAD_SIZE is not None:
            max_size = min(max_size, dataset_service.MAX_UPLOAD_SIZE)
        sha = hashlib.sha256()
        size = 0
        try:
            with temp_path.open("wb") as target:
                while chunk := await file.read(settings.chunk_bytes):
                    size += len(chunk)
                    if size > max_size:
                        raise HTTPException(413, detail=f"File size exceeds maximum upload limit ({max_size} bytes)")
                    target.write(chunk)
                    sha.update(chunk)
            if not size:
                raise HTTPException(400, detail="Uploaded file is empty")
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        digest = sha.hexdigest()
        safe_name = Path(filename).name
        stored_path = upload_root / f"{digest}_{safe_name}"
        if stored_path.exists():
            temp_path.unlink(missing_ok=True)
            if hashlib.sha256(stored_path.read_bytes()).hexdigest() != digest:
                stored_path = upload_root / f"{digest}_{uuid.uuid4().hex}_{safe_name}"
                temp_path.replace(stored_path)
        else:
            temp_path.replace(stored_path)
        if _file_sha256(stored_path) != digest:
            raise HTTPException(500, detail="Stored upload hash verification failed")

        workspaces = repo.list_rows(WorkspaceRow)
        workspace_id = f"workspace-{repo.company_id}"
        if not any(row.id == workspace_id for row in workspaces):
            repo.add(WorkspaceRow(id=workspace_id, name="Default workspace"))
        projects = repo.list_rows(ProjectRow)
        project_id = f"project-{repo.company_id}"
        if not any(row.id == project_id for row in projects):
            repo.add(ProjectRow(id=project_id, workspace_id=workspace_id, name="Default project"))

        # Check for multi-table ZIP archive
        if Path(filename).suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(stored_path) as archive:
                    infos = archive.infolist()
                    if (
                        len(infos) <= settings.max_zip_entries
                        and sum(info.file_size for info in infos) <= settings.max_zip_uncompressed_bytes
                        and (sum(info.file_size for info in infos) / max(stored_path.stat().st_size, 1)) <= settings.max_zip_compression_ratio
                        and all(safe_member_name(info.filename) and not stat.S_ISLNK(info.external_attr >> 16) for info in infos)
                    ):
                        members = [i for i in infos if not i.is_dir() and Path(i.filename).suffix.lower()
                                   in {".csv", ".xlsx", ".xlsm", ".json", ".jsonl"}]
                        if len(members) > 1:
                            tables_preview = []
                            for member_info in members:
                                m_basename = Path(member_info.filename).name
                                m_target_path = upload_root / f"{digest}_{m_basename}"
                                with archive.open(member_info) as m_src, m_target_path.open("wb") as m_dst:
                                    m_sha = hashlib.sha256()
                                    while m_chunk := m_src.read(settings.chunk_bytes):
                                        m_dst.write(m_chunk)
                                        m_sha.update(m_chunk)
                                m_digest = m_sha.hexdigest()
                                tbl_stem = Path(m_basename).stem.strip().lower()
                                tbl_name = re.sub(r"[^a-z0-9_-]", "_", tbl_stem)[:128] or "table"
                                tbl_source_id = str(uuid.uuid4())
                                tbl_version_id, tbl_job_id = str(uuid.uuid4()), str(uuid.uuid4())
                                repo.add(DataSourceRow(id=tbl_source_id, project_id=project_id, name=tbl_name,
                                                       source_type=Path(m_basename).suffix.lower(), location_ref=str(m_target_path)))
                                repo.add(DatasetVersionRow(id=tbl_version_id, dataset=tbl_name, source=tbl_name, source_hash=m_digest,
                                    observed_at=datetime.now(timezone.utc), license_status="UNKNOWN",
                                    payload={"filename": m_basename, "source_id": tbl_source_id, "size_bytes": member_info.file_size}))
                                repo.add(ImportJobRow(id=tbl_job_id, data_source_id=tbl_source_id, dataset_version_id=tbl_version_id,
                                    status="QUEUED", payload={"filename": m_basename, "size_bytes": member_info.file_size,
                                                               "source_sha256": m_digest, "processed_rows": 0, "total_rows": None}))
                                background_tasks.add_task(_profile_import_job, repo, tbl_job_id, tbl_source_id, tbl_version_id,
                                                          str(m_target_path), m_basename, tbl_name)
                                tables_preview.append({
                                    "dataset_name": tbl_name,
                                    "filename": m_basename,
                                    "size_bytes": member_info.file_size,
                                    "sha256": m_digest,
                                    "source_id": tbl_source_id,
                                    "dataset_version_id": tbl_version_id,
                                    "import_job_id": tbl_job_id,
                                    "status": "QUEUED",
                                })
                            _audit(repo, "multi_table_zip_uploaded", identity["actor"], source=Path(safe_name).stem,
                                   record_refs=[digest], details={"table_count": len(members), "tables": [t["dataset_name"] for t in tables_preview]})
                            return {
                                "dataset_name": Path(safe_name).stem,
                                "filename": safe_name,
                                "sha256": digest,
                                "is_multi_table": True,
                                "table_count": len(members),
                                "tables": tables_preview,
                                "status": "QUEUED",
                                "message": f"Multi-table ZIP detected: created {len(members)} data sources",
                            }
            except Exception:
                pass

        name = (dataset_name or Path(safe_name).stem).strip().lower()
        name = re.sub(r"[^a-z0-9_-]", "_", name)[:128] or "uploaded_dataset"
        source_id = str(uuid.uuid4())
        version_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        repo.add(DataSourceRow(id=source_id, project_id=project_id, name=name,
                               source_type=Path(safe_name).suffix.lower(), location_ref=str(stored_path)))
        repo.add(DatasetVersionRow(id=version_id, dataset=name, source=name, source_hash=digest,
            observed_at=datetime.now(timezone.utc), license_status="UNKNOWN",
            payload={"filename": safe_name, "source_id": source_id, "size_bytes": size}))
        repo.add(ImportJobRow(id=job_id, data_source_id=source_id, dataset_version_id=version_id,
            status="QUEUED", payload={"filename": safe_name, "size_bytes": size, "source_sha256": digest,
                                       "processed_rows": 0, "total_rows": None}))
        background_tasks.add_task(_profile_import_job, repo, job_id, source_id, version_id,
                                  str(stored_path), safe_name, name)
        _audit(repo, "dataset_upload_queued", identity["actor"], source=name,
               record_refs=[digest], details={"filename": safe_name, "size_bytes": size,
                                               "import_job_id": job_id})
        job = repo.get(ImportJobRow, job_id)
        response = {"dataset_name": name, "filename": safe_name, "sha256": digest,
                    "source_id": source_id, "dataset_version_id": version_id,
                    "import_job_id": job_id, "status": job.status if job else "QUEUED",
                    "processed_rows": job.payload.get("processed_rows", 0) if job else 0,
                    "total_rows": job.payload.get("total_rows") if job else None,
                    "total_rows_known": (job.payload.get("total_rows") is not None) if job else False,
                    "statistics": job.payload.get("statistics") if job else None,
                    "error": job.payload.get("error") if job else None}
        if job and job.payload.get("statistics"):
            response.update(job.payload["statistics"])
        return response

    @router.get("/datasets/{dataset_name}/suggestions")
    def dataset_suggestions(
        dataset_name: Annotated[str, PathParam(min_length=1, max_length=128)],
        repo: Repository = Depends(_repository),
        _identity: dict[str, Any] = Depends(_require("analyst")),
    ):
        sources = [row for row in repo.list_rows(DataSourceRow) if row.name == dataset_name]
        if not sources:
            raise HTTPException(404, detail=f"Uploaded dataset source for '{dataset_name}' not found")
        source = max(sources, key=lambda item: item.created_at)
        version = next((v for v in repo.list_rows(DatasetVersionRow)
                        if v.payload.get("source_id") == source.id), None)
        if not version or not version.payload.get("profile"):
            raise HTTPException(409, detail="Import profiling is not complete")
        from src.data.profiler import DatasetProfileReport
        return suggest_mappings(DatasetProfileReport.model_validate(version.payload["profile"]))

    @router.get("/datasets/suggestions")
    def dataset_suggestions_query(
        dataset: str,
        repo: Repository = Depends(_repository),
        _identity: dict[str, Any] = Depends(_require("analyst")),
    ):
        return dataset_suggestions(dataset, repo, _identity)

    @router.get("/datasets/{dataset_name}/drift")
    def dataset_drift(
        dataset_name: Annotated[str, PathParam(min_length=1, max_length=128)],
        repo: Repository = Depends(_repository),
        _identity: dict[str, Any] = Depends(_require("viewer")),
    ):
        sources = [row for row in repo.list_rows(DataSourceRow) if row.name == dataset_name]
        if not sources:
            raise HTTPException(404, detail=f"Dataset '{dataset_name}' not found")
        versions = [v for v in repo.list_rows(DatasetVersionRow) if v.dataset == dataset_name]
        if not versions:
            raise HTTPException(404, detail=f"No versions found for dataset '{dataset_name}'")
        drift_entry = next((v.payload.get("drift") for v in reversed(versions) if (v.payload or {}).get("drift")), None)
        if drift_entry:
            return {"dataset_name": dataset_name, **drift_entry}
        return {
            "status": "NO_PRIOR_VERSION",
            "dataset_name": dataset_name,
            "message": "No baseline dataset version available for drift comparison.",
            "schema": {"added_columns": [], "removed_columns": [], "type_changes": {}},
            "drift_is_warning_only": True,
            "triggers_automatic_retrain": False,
            "limitations": ["Drift monitoring requires at least two versions for comparison."],
        }

    @router.get("/imports/{job_id}")
    def import_job_status(job_id: Annotated[str, PathParam(min_length=1, max_length=128)],
                          repo: Repository = Depends(_repository),
                          _identity: dict[str, Any] = Depends(_require("analyst"))):
        job = repo.get(ImportJobRow, job_id)
        if not job:
            raise HTTPException(404, detail="Import job not found")
        data = {**job.payload} if job.payload else {}
        stats = data.get("statistics") or {}
        if isinstance(stats, dict):
            s_skipped = stats.get("sheets_skipped", [])
            stats["skipped_sheets"] = s_skipped
            if "sheets_summary" not in stats and (stats.get("sheets_imported") or s_skipped):
                summary = []
                for imp in stats.get("sheets_imported", []):
                    summary.append({"sheet_name": imp, "status": "IMPORTED", "reason": "Tabular data table"})
                for sk in s_skipped:
                    summary.append({"sheet_name": sk.get("sheet_name", "unknown"), "status": "SKIPPED", "reason": sk.get("reason", "not a data table")})
                stats["sheets_summary"] = summary
            data["statistics"] = stats
        return {"id": job.id, "status": job.status, **data}

    @router.get("/imports")
    def import_history(repo: Repository = Depends(_repository),
                       _identity: dict[str, Any] = Depends(_require("analyst"))):
        rows = sorted(repo.list_rows(ImportJobRow), key=lambda row: row.created_at, reverse=True)
        return {"items": [{"id": row.id, "status": row.status, **(row.payload or {})} for row in rows],
                "count": len(rows)}

    @router.post("/imports/{job_id}/preview")
    def preview_import(job_id: str, body: ImportDecision, repo: Repository = Depends(_repository),
                       _identity: dict[str, Any] = Depends(_require("analyst"))):
        job = repo.get(ImportJobRow, job_id)
        if not job or job.status != "AWAITING_IMPORT_DECISION":
            raise HTTPException(409, detail="Import job is not ready for an import decision")
        source = repo.get(DataSourceRow, job.data_source_id)
        active_source_ids = {row.id for row in repo.list_rows(DataSourceRow)
                             if source and row.name == source.name}
        current = [row for row in repo.list_rows(ImportJobRow)
                   if row.data_source_id in active_source_ids and row.id != job.id
                   and row.status == "COMPLETED"]
        active_rows = sum(int(row.payload.get("processed_rows", 0)) for row in current)
        incoming = int(job.payload.get("processed_rows", 0))
        return {"mode": body.mode, "current_rows": active_rows,
                "incoming_rows": incoming, "resulting_rows": incoming if body.mode == "replace" else active_rows + incoming,
                "source_id": source.id if source else None,
                "note": "Preview only; no monitored source or import history has been changed."}

    @router.post("/imports/{job_id}/commit")
    def commit_import(job_id: str, body: ImportDecision, background_tasks: BackgroundTasks,
                      repo: Repository = Depends(_repository),
                      identity: dict[str, Any] = Depends(_require("analyst"))):
        job = repo.get(ImportJobRow, job_id)
        source = repo.get(DataSourceRow, job.data_source_id) if job else None
        if not job or not source or job.status != "AWAITING_IMPORT_DECISION":
            raise HTTPException(409, detail="Import job is not ready for an import decision")
        if not any(row.data_source_id == source.id and row.status == "ACCEPTED"
                   for row in repo.list_rows(MappingVersionRow)):
            raise HTTPException(409, detail="Accept a mapping before committing this import")
        preview = preview_import(job_id, body, repo, identity)
        job.status = "IMPORTING"
        job.payload = {**job.payload, "mode": body.mode,
                       "preview_resulting_rows": preview["resulting_rows"],
                       "committed_at": datetime.now(timezone.utc).isoformat()}
        repo.add(job)
        background_tasks.add_task(_materialize_import, repo, job_id, body.mode, identity["actor"])
        _audit(repo, "dataset_import_committed", identity["actor"], source=source.name,
               record_refs=[job.id], details={"mode": body.mode,
                                              "processed_rows": job.payload.get("processed_rows")})
        return {"id": job.id, "status": "IMPORTING", "mode": body.mode,
                "processed_rows": job.payload.get("processed_rows"),
                "total_rows": job.payload.get("total_rows"), "preview": preview}

    @router.get("/datasets/{dataset_name}/mappings")
    def mapping_history(dataset_name: str, repo: Repository = Depends(_repository),
                        _identity: dict[str, Any] = Depends(_require("viewer"))):
        source_ids = {row.id for row in repo.list_rows(DataSourceRow) if row.name == dataset_name}
        rows = sorted([row for row in repo.list_rows(MappingVersionRow) if row.data_source_id in source_ids],
                      key=lambda row: row.version)
        return {"items": [{"id": row.id, "version": row.version, "status": row.status,
                           "mapping": row.mapping} for row in rows], "count": len(rows)}

    @router.post("/datasets/{dataset_name}/mappings")
    def create_mapping(dataset_name: str, body: MappingVersionRequest, repo: Repository = Depends(_repository),
                       identity: dict[str, Any] = Depends(_require("analyst"))):
        return _save_mapping_version(dataset_name, body, repo, identity["actor"], status="PENDING_REVIEW")

    @router.put("/datasets/{dataset_name}/mappings/{version}")
    def edit_mapping(dataset_name: str, version: str, body: MappingVersionRequest,
                     repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("analyst"))):
        sources = [row for row in repo.list_rows(DataSourceRow) if row.name == dataset_name]
        latest_source = max(sources, key=lambda item: item.created_at) if sources else None
        if not sources or not any(row.version == version and row.data_source_id == latest_source.id
                                  for row in repo.list_rows(MappingVersionRow)):
            raise HTTPException(404, detail="Mapping version not found")
        return _save_mapping_version(dataset_name, body, repo, identity["actor"], status="PENDING_REVIEW")

    @router.post("/datasets/{dataset_name}/mappings/{version}/accept")
    def accept_mapping(request: Request, dataset_name: str, version: str, body: ReasonRequest,
                       repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("analyst"))):
        _check_mapping_role(request, identity, repo)
        return _review_mapping(dataset_name, version, body.reason, "ACCEPTED", repo, identity["actor"])

    @router.post("/datasets/{dataset_name}/mappings/{version}/reject")
    def reject_mapping(request: Request, dataset_name: str, version: str, body: ReasonRequest,
                       repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("analyst"))):
        _check_mapping_role(request, identity, repo)
        return _review_mapping(dataset_name, version, body.reason, "REJECTED", repo, identity["actor"])

    @router.post("/imports/{job_id}/reprocess")
    def reprocess_import(job_id: str, background_tasks: BackgroundTasks,
                         repo: Repository = Depends(_repository),
                         identity: dict[str, Any] = Depends(_require("analyst"))):
        old_job = repo.get(ImportJobRow, job_id)
        if not old_job:
            raise HTTPException(404, detail="Import job not found")
        source = repo.get(DataSourceRow, old_job.data_source_id)
        version = repo.get(DatasetVersionRow, old_job.dataset_version_id) if old_job.dataset_version_id else None
        accepted = [row for row in repo.list_rows(MappingVersionRow)
                    if row.data_source_id == old_job.data_source_id and row.status == "ACCEPTED"]
        if not source or not version or not accepted:
            raise HTTPException(409, detail="Accept a mapping before reprocessing this source")
        new_id = str(uuid.uuid4())
        new_job = ImportJobRow(id=new_id, data_source_id=source.id, dataset_version_id=version.id,
                               status="QUEUED", payload={"filename": old_job.payload.get("filename"),
                               "source_sha256": version.source_hash, "processed_rows": 0, "total_rows": None,
                               "reprocess_of": old_job.id})
        repo.add(new_job)
        background_tasks.add_task(_profile_import_job, repo, new_id, source.id, version.id,
                                  source.location_ref, old_job.payload.get("filename", "source.csv"), source.name)
        _audit(repo, "dataset_reprocess_queued", identity["actor"], source=source.name, record_refs=[new_id])
        return {"id": new_id, "status": "QUEUED", "reprocess_of": job_id}

    @router.post("/datasets/relationships/preview")
    def relationship_preview(body: RelationshipPreviewRequest, repo: Repository = Depends(_repository),
                             _identity: dict[str, Any] = Depends(_require("analyst"))):
        results = []
        for link in body.links:
            left = repo.get(DataSourceRow, link.left_source_id)
            right = repo.get(DataSourceRow, link.right_source_id)
            if not left or not right:
                raise HTTPException(404, detail="One or more source IDs were not found in this company workspace")
            left_counts, left_nulls = _key_counts(Path(left.location_ref), Path(left.location_ref).name,
                                                   link.left_key, load_settings().uploads.chunk_rows)
            right_counts, right_nulls = _key_counts(Path(right.location_ref), Path(right.location_ref).name,
                                                     link.right_key, load_settings().uploads.chunk_rows)
            shared = set(left_counts).intersection(right_counts)
            results.append({"left_source_id": left.id, "left_key": link.left_key,
                "right_source_id": right.id, "right_key": link.right_key,
                "relationship": link.relationship,
                "matched_left_rows": sum(left_counts[key] for key in shared),
                "matched_right_rows": sum(right_counts[key] for key in shared),
                "orphan_left_rows": sum(value for key, value in left_counts.items() if key not in right_counts),
                "orphan_right_rows": sum(value for key, value in right_counts.items() if key not in left_counts),
                "invalid_left_references": left_nulls, "invalid_right_references": right_nulls})
        proposal_id = str(uuid.uuid4())
        repo.add(RelationshipProposalRow(id=proposal_id, status="PENDING_APPROVAL",
            payload={"links": results, "created_relationships": False,
                     "note": "Preview only; explicit approval is required."}))
        return {"proposal_id": proposal_id, "status": "PENDING_APPROVAL", "links": results,
                "created_relationships": False}

    @router.post("/datasets/relationships/{proposal_id}/approve")
    def approve_relationships(request: Request, proposal_id: str, body: ReasonRequest, repo: Repository = Depends(_repository),
                             identity: dict[str, Any] = Depends(_require("analyst"))):
        _check_mapping_role(request, identity, repo)
        proposal = repo.get(RelationshipProposalRow, proposal_id)
        if not proposal:
            raise HTTPException(404, detail="Relationship proposal not found")
        if proposal.status != "PENDING_APPROVAL":
            raise HTTPException(409, detail="Relationship proposal is not pending")
        proposal.status = "APPROVED"
        proposal.payload = {**proposal.payload, "created_relationships": True,
                            "approved_by": identity["actor"], "approval_reason": body.reason,
                            "approved_at": datetime.now(timezone.utc).isoformat()}
        repo.add(proposal)
        _audit(repo, "dataset_relationships_approved", identity["actor"], record_refs=[proposal_id],
               details={"reason": body.reason})
        return {"id": proposal.id, "status": proposal.status, "created_relationships": True}

    @router.put("/datasets/{dataset_name}/confirm-mapping")
    def confirm_mapping(
        request: Request,
        dataset_name: Annotated[str, PathParam(min_length=1, max_length=128)],
        body: DatasetMappingConfirm,
        repo: Repository = Depends(_repository),
        identity: dict[str, Any] = Depends(_require("analyst")),
    ):
        _check_mapping_role(request, identity, repo)
        pending = _save_mapping_version(dataset_name, MappingVersionRequest(
            mappings=body.mappings, reason=body.description or "Explicit reviewer confirmation"),
            repo, identity["actor"], status="PENDING_REVIEW")
        accepted = _review_mapping(dataset_name, pending["version"],
            body.description or "Explicit reviewer confirmation", "ACCEPTED", repo, identity["actor"])
        return {key: value for key, value in accepted["mapping"].items() if key != "review_history"}

    @router.get("/datasets")
    def get_datasets(
        repo: Repository = Depends(_repository),
        _identity: dict[str, Any] = Depends(_require("viewer")),
    ):
        items = []
        for source in repo.list_rows(DataSourceRow, include_deleted=True):
            version = next((row for row in repo.list_rows(DatasetVersionRow)
                            if row.payload.get("source_id") == source.id), None)
            latest_mapping = next((row for row in reversed(repo.list_rows(MappingVersionRow))
                                   if row.data_source_id == source.id), None)
            items.append({"dataset_name": source.name, "source_id": source.id,
                          "status": "DELETED" if source.deleted_at else
                                   latest_mapping.status if latest_mapping else "PENDING_REVIEW",
                          "source_file": version.payload.get("filename", "") if version else "",
                          "sha256": version.source_hash if version else "",
                          "mapping_version": latest_mapping.version if latest_mapping else None,
                          "monitoring": source.deleted_at is None})
        return {"items": items, "count": len(items)}

    @router.delete("/datasets/{dataset_name}")
    def remove_dataset(
        dataset_name: Annotated[str, PathParam(min_length=1, max_length=128)],
        repo: Repository = Depends(_repository),
        identity: dict[str, Any] = Depends(_require("admin")),
    ):
        sources = [source for source in repo.list_rows(DataSourceRow) if source.name == dataset_name]
        if not sources:
            raise HTTPException(404, detail=f"Dataset '{dataset_name}' not found")
        for source in sources:
            repo.soft_delete(DataSourceRow, source.id, actor=identity["actor"],
                            reason="Removed from monitoring; audit history and raw source retained")
        _audit(repo, "dataset_removed_from_monitoring", identity["actor"], source=dataset_name,
               record_refs=[source.id for source in sources])
        return {"deleted": True, "dataset_name": dataset_name,
                "audit_history_preserved": True, "raw_source_retained": True}

    @router.post("/projects/{project_id}/pipeline/run", status_code=200)
    def run_project_pipeline_endpoint(
        project_id: Annotated[str, PathParam(min_length=1, max_length=128)],
        repo: Repository = Depends(_repository),
        identity: dict[str, Any] = Depends(_require("analyst")),
    ):
        project = repo.get(ProjectRow, project_id)
        if not project:
            raise HTTPException(404, detail="Project not found")

        # Materialize any uncommitted imports for sources in this project that have accepted mappings
        sources = [s for s in repo.list_rows(DataSourceRow) if s.project_id == project_id]
        source_ids = {s.id for s in sources}
        mappings = [m for m in repo.list_rows(MappingVersionRow) if m.data_source_id in source_ids and m.status == "ACCEPTED"]
        accepted_source_ids = {m.data_source_id for m in mappings}

        for s in sources:
            if s.id in accepted_source_ids:
                jobs = [j for j in repo.list_rows(ImportJobRow) if j.data_source_id == s.id]
                for j in jobs:
                    if j.status == "AWAITING_IMPORT_DECISION":
                        _materialize_import(repo, j.id, "append", identity["actor"])

        capabilities = _project_capability_report(repo, project_id)
        if capabilities.get("approved_mapping_count", 0) == 0:
            raise HTTPException(409, detail="Approve at least one mapping before executing pipeline")

        preview = preview_pipeline(capabilities)
        run_id = preview["id"]
        run_row = PipelineRunRow(
            id=run_id,
            project_id=project_id,
            status="QUEUED",
            payload={
                **preview,
                "capabilities": capabilities,
                "dry_run": False,
                "created_by": identity["actor"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        repo.add(run_row)
        _execute_project_pipeline(repo, run_id, project_id)
        completed_run = repo.get(PipelineRunRow, run_id)
        return _sanitize_for_json({
            "id": run_id,
            "project_id": project_id,
            "status": completed_run.status if completed_run else "COMPLETED",
            "result": completed_run.payload.get("result", {}) if completed_run else {},
        })

    @router.post("/pipeline/run")
    def pipeline_run_dispatch(
        body: dict[str, Any],
        repo: Repository = Depends(_repository),
        identity: dict[str, Any] = Depends(_require("analyst")),
    ):
        if "project_id" in body and body["project_id"]:
            return run_project_pipeline_endpoint(body["project_id"], repo=repo, identity=identity)
        datasets = body.get("datasets", ["olist", "dataco", "online_retail_ii"])
        allowed = {"olist", "dataco", "online_retail_ii"}
        if not set(datasets).issubset(allowed):
            raise HTTPException(422, "Unknown dataset")
        _audit(repo, "pipeline_dry_run_requested", identity["actor"], details={"datasets": datasets, "executed": False})
        return DryRunResult(
            message="Request recorded; pipeline was not executed by this dry-run endpoint.",
            datasets=datasets,
            kill_switch=bool(getattr(app.state, "kill_switch", load_settings().kill_switch)),
        )

    @router.get("/datasets/{dataset_name}/quality-report")
    def get_dataset_quality_report(
        dataset_name: Annotated[str, PathParam(min_length=1, max_length=128)],
        repo: Repository = Depends(_repository),
        _identity: dict[str, Any] = Depends(_require("viewer")),
    ):
        return compute_dataset_quality_report(repo, dataset_name)

    @router.get("/projects/{project_id}/quality-report")
    def get_project_quality_report(
        project_id: Annotated[str, PathParam(min_length=1, max_length=128)],
        repo: Repository = Depends(_repository),
        _identity: dict[str, Any] = Depends(_require("viewer")),
    ):
        return compute_project_quality_report(repo, project_id)

    @router.post("/projects/{project_id}/leakage-overrides", status_code=200)
    def add_leakage_override(
        project_id: Annotated[str, PathParam(min_length=1, max_length=128)],
        body: dict[str, Any],
        repo: Repository = Depends(_repository),
        identity: dict[str, Any] = Depends(_require("analyst")),
    ):
        col = body.get("column", "")
        reason = body.get("reason", "")
        if not col or not reason:
            raise HTTPException(422, "Both column and reason are required")
        _audit(repo, "leakage_override_recorded", identity["actor"], details={"project_id": project_id, "column": col, "reason": reason})
        return {"project_id": project_id, "column": col, "reason": reason, "status": "RECORDED"}

    @router.get("/projects/{project_id}/capabilities")
    def project_capabilities(project_id: Annotated[str, PathParam(min_length=1, max_length=128)],
                              repo: Repository = Depends(_repository),
                              _identity: dict[str, str] = Depends(_require("viewer"))):
        return _project_capability_report(repo, project_id)

    def project_graph(repo: Repository, project_id: str, max_records: int = 10000):
        project = repo.get(ProjectRow, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        combined = nx.MultiDiGraph()
        omitted: dict[str, str] = {}
        sources = [row for row in repo.list_rows(DataSourceRow, limit=10000) if row.project_id == project_id]
        source_ids = {row.id for row in sources}
        accepted = [row for row in repo.list_rows(MappingVersionRow, limit=10000)
                    if row.data_source_id in source_ids and row.status == "ACCEPTED"]
        latest_mapping = {source_id: max((m for m in accepted if m.data_source_id == source_id),
                                        key=lambda m: m.version, default=None) for source_id in source_ids}
        jobs = [job for job in repo.list_rows(ImportJobRow, limit=10000)
                if job.data_source_id in source_ids and job.status == "COMPLETED" and job.payload.get("processed_file")]
        for source in sources:
            mapping = latest_mapping.get(source.id)
            if not mapping:
                omitted[f"source:{source.name}"] = "no confirmed mapping"
                continue
            job = max((item for item in jobs if item.data_source_id == source.id), key=lambda item: item.created_at, default=None)
            if not job:
                omitted[f"source:{source.name}"] = "no completed canonical import"
                continue
            path = Path(job.payload["processed_file"]).resolve()
            safe_root = (Path("data/processed/companies") / re.sub(r"[^A-Za-z0-9_-]", "_", repo.company_id)).resolve()
            if not path.is_relative_to(safe_root) or not path.is_file():
                omitted[f"source:{source.name}"] = "canonical file is missing or outside the company processed-data directory"
                continue
            records = []
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if len(records) >= max_records:
                        break
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            version = repo.get(DatasetVersionRow, job.dataset_version_id) if job.dataset_version_id else None
            built = build_canonical_graph(records, source=source.name, mapping_version=mapping.version,
                source_hash=version.source_hash if version else "UNKNOWN")
            combined.add_nodes_from(built["graph"].nodes(data=True))
            combined.add_edges_from((a, b, key, data) for a, b, key, data in built["graph"].edges(keys=True, data=True))
            omitted.update({f"{source.name}:{kind}": reason for kind, reason in built["omitted_node_types"].items()})
        # User-entered links are visible only after a reviewer approved the relationship.
        for proposal in repo.list_rows(RelationshipProposalRow, limit=10000):
            if proposal.status != "APPROVED":
                continue
            for relation in proposal.payload.get("graph_relationships", []):
                left, right = relation.get("left_node_id"), relation.get("right_node_id")
                if left in combined and right in combined:
                    combined.add_edge(left, right, meaning=relation["meaning"], source="user",
                        source_record_ref=relation["source_record_ref"], provenance=proposal.id,
                        validity_period={"from": relation.get("valid_from"), "to": relation.get("valid_to")},
                        flag="USER_ENTERED")
        # Incident links are evidence associations and remain INFERRED; they do not assert a cause.
        for incident in repo.list_rows(IncidentRow, limit=10000):
            version = repo.get(DatasetVersionRow, incident.dataset_version_id)
            source_id = (version.payload or {}).get("source_id") if version else None
            source = repo.get(DataSourceRow, source_id) if source_id else None
            if not source or source.project_id != project_id:
                continue
            incident_node = f"incident:{source.name}:{incident.id}"
            incident_payload = incident.payload or {}
            risk_level = incident_payload.get("risk_level") or incident_payload.get("severity")
            combined.add_node(incident_node, type="Incident", identifier=incident.id, source=incident.source,
                source_record_ref=incident.id, valid_from=incident.occurred_at.isoformat(), valid_to=None,
                title=incident.title, risk_level=risk_level)
            refs = set(incident_payload.get("record_refs", []))
            linked_nodes = set()
            for left, right, _key, attrs in combined.edges(keys=True, data=True):
                if attrs.get("source_record_ref") in refs:
                    linked_nodes.update((left, right))
            for endpoint in linked_nodes:
                if combined.nodes[endpoint].get("type") == "Supplier":
                    combined.nodes[endpoint]["incident_count"] = int(combined.nodes[endpoint].get("incident_count", 0)) + 1
                if risk_level:
                    combined.nodes[endpoint]["risk_level"] = risk_level
                combined.add_edge(incident_node, endpoint, meaning="incident references a source-record relationship",
                    source=incident.source, source_record_ref=incident.id,
                    provenance=f"incident_id={incident.id};dataset_version={incident.dataset_version_id}",
                    validity_period={"from": incident.occurred_at.isoformat(), "to": None}, flag="INFERRED")
        return combined, omitted

    @router.get("/projects/{project_id}/graph")
    def project_graph_view(project_id: Annotated[str, PathParam(min_length=1, max_length=128)],
            company_id: str | None = None, supplier_id: str | None = None, product_id: str | None = None,
            start: datetime | None = None, end: datetime | None = None, risk: str | None = None,
            limit: int = 1000, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("viewer"))):
        if company_id and company_id != repo.company_id:
            raise HTTPException(403, "Company scope mismatch")
        if limit < 1 or limit > 5000:
            raise HTTPException(422, "limit must be between 1 and 5000")
        if start and end and start > end:
            raise HTTPException(422, "start must be earlier than end")
        graph, omitted = project_graph(repo, project_id, max_records=50000)
        node_filter = None
        if supplier_id:
            seeds = {f"supplier:{source.name}:{supplier_id}" for source in repo.list_rows(DataSourceRow)
                     if source.project_id == project_id}
            node_filter = seeds
        if product_id:
            seeds = {f"product:{source.name}:{product_id}" for source in repo.list_rows(DataSourceRow)
                     if source.project_id == project_id}
            node_filter = (node_filter or set()) | seeds
        if node_filter:
            undirected = graph.to_undirected()
            node_filter = {member for seed in node_filter if seed in undirected
                           for member in nx.node_connected_component(undirected, seed)}
        nodes = []
        for node_id, attrs in graph.nodes(data=True):
            stamp = attrs.get("valid_from")
            if node_filter and node_id not in node_filter:
                continue
            if start and stamp and datetime.fromisoformat(stamp.replace("Z", "+00:00")) < start:
                continue
            if end and stamp and datetime.fromisoformat(stamp.replace("Z", "+00:00")) > end:
                continue
            if risk and str(attrs.get("risk_level", "")).upper() != risk.upper():
                continue
            nodes.append({"id": node_id, **attrs})
        allowed = {item["id"] for item in nodes}
        edges = [{"from": left, "to": right, **attrs} for left, right, attrs in graph.edges(data=True)
                 if left in allowed and right in allowed][:limit]
        nodes = nodes[:limit]
        return {"nodes": nodes, "edges": edges, "omitted_node_types": omitted,
                "count": {"nodes": len(nodes), "edges": len(edges)}, "truncated": graph.number_of_nodes() > limit,
                "filters": {"company_id": repo.company_id, "supplier_id": supplier_id, "product_id": product_id,
                            "start": start, "end": end, "risk": risk},
                "analytics": graph_analytics(graph),
                "limitations": ["Graph results describe exposure/hypotheses, not causation."]}

    @router.get("/projects/{project_id}/graph/neighborhood")
    def graph_neighborhood(project_id: str, node_id: Annotated[str, Query(min_length=1, max_length=256)],
            hops: int = 1, limit: int = 500, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("viewer"))):
        if hops < 1 or hops > 3 or limit < 1 or limit > 500:
            raise HTTPException(422, "hops must be 1..3 and limit must be 1..500")
        graph, omitted = project_graph(repo, project_id, max_records=50000)
        if node_id not in graph:
            raise HTTPException(404, "Graph node not found")
        selected = {node_id}
        frontier = {node_id}
        for _ in range(hops):
            frontier = {neighbor for node in frontier for neighbor in set(graph.predecessors(node)) | set(graph.successors(node))} - selected
            selected.update(frontier)
            if len(selected) >= limit:
                selected = set(list(selected)[:limit])
                break
        nodes = [{"id": item, **graph.nodes[item]} for item in selected]
        edges = [{"from": left, "to": right, **attrs} for left, right, attrs in graph.edges(data=True)
                 if left in selected and right in selected][:limit]
        return {"nodes": nodes, "edges": edges, "omitted_node_types": omitted,
                "label": "exposure/hypothesis", "truncated": len(selected) >= limit}

    @router.get("/projects/{project_id}/graph/trace/downstream")
    def graph_trace_downstream(project_id: str, node_id: Annotated[str, Query(min_length=1, max_length=256)],
            limit: int = 500, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("viewer"))):
        if limit < 1 or limit > 500:
            raise HTTPException(422, "limit must be between 1 and 500")
        graph, _ = project_graph(repo, project_id, max_records=50000)
        return downstream_trace(graph, node_id, max_nodes=limit)

    @router.get("/projects/{project_id}/graph/trace/upstream")
    def graph_trace_upstream(project_id: str, node_id: Annotated[str, Query(min_length=1, max_length=256)],
            limit: int = 500, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("viewer"))):
        if limit < 1 or limit > 500:
            raise HTTPException(422, "limit must be between 1 and 500")
        graph, _ = project_graph(repo, project_id, max_records=50000)
        return upstream_trace(graph, node_id, max_nodes=limit)

    @router.get("/projects/{project_id}/graph/aggregated")
    def project_graph_aggregated(
        project_id: Annotated[str, PathParam(min_length=1, max_length=128)],
        company_id: str | None = None,
        dataset_name: str | None = None,
        incident_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        max_nodes: int = 150,
        time_bucket: str = "week",
        repo: Repository = Depends(_repository),
        _identity: dict[str, str] = Depends(_require("viewer")),
    ):
        if company_id and company_id != repo.company_id:
            raise HTTPException(403, "Company scope mismatch")
        if max_nodes < 1 or max_nodes > 1000:
            raise HTTPException(422, "max_nodes must be between 1 and 1000")
        if start and end and start > end:
            raise HTTPException(422, "start must be earlier than end")

        sources = [s for s in repo.list_rows(DataSourceRow) if s.project_id == project_id or not s.project_id]
        if dataset_name:
            sources = [s for s in sources if s.name == dataset_name]

        jobs = repo.list_rows(ImportJobRow)
        records = []
        source_name = dataset_name or (sources[0].name if sources else "default")

        for s in sources:
            matching_jobs = [j for j in jobs if j.data_source_id == s.id and j.status == "COMPLETED"]
            if not matching_jobs:
                continue
            job = max(matching_jobs, key=lambda j: j.created_at, default=None)
            if not job or not job.payload or not job.payload.get("processed_file"):
                continue
            p_file = Path(job.payload["processed_file"])
            if p_file.exists():
                with p_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        if len(records) >= 20000:
                            break
                        try:
                            rec = json.loads(line)
                            records.append(rec)
                        except Exception:
                            continue

        anomalies_rows = repo.list_rows(AnomalyRow, limit=1000)
        anomalies = [{"id": a.id, "record_ref": a.record_ref, "feature": a.feature, "severity": (a.payload or {}).get("severity", 0.8)} for a in anomalies_rows]
        incidents_rows = repo.list_rows(IncidentRow, limit=100)
        incidents = [{"id": i.id, "title": i.title, "record_refs": (i.payload or {}).get("record_refs", [])} for i in incidents_rows]

        approved_rel = []
        for prop in repo.list_rows(RelationshipProposalRow):
            if prop.status == "APPROVED" and prop.payload:
                approved_rel.extend(prop.payload.get("graph_relationships", []))
                approved_rel.extend(prop.payload.get("links", []))

        return build_aggregated_supply_network(
            records,
            source=source_name,
            company_id=repo.company_id,
            anomalies=anomalies,
            incidents=incidents,
            approved_relationships=approved_rel,
            max_nodes=max_nodes,
            selected_incident_id=incident_id,
            time_bucket_unit=time_bucket,
        )

    @router.get("/projects/{project_id}/graph/aggregated/trace")
    def project_graph_aggregated_trace(
        project_id: Annotated[str, PathParam(min_length=1, max_length=128)],
        node_id: Annotated[str, Query(min_length=1, max_length=256)],
        direction: str = "downstream",
        dataset_name: str | None = None,
        incident_id: str | None = None,
        limit: int = 500,
        repo: Repository = Depends(_repository),
        _identity: dict[str, str] = Depends(_require("viewer")),
    ):
        if limit < 1 or limit > 500:
            raise HTTPException(422, "limit must be between 1 and 500")
        if direction not in ("upstream", "downstream"):
            raise HTTPException(422, "direction must be upstream or downstream")

        agg_graph = project_graph_aggregated(
            project_id=project_id,
            dataset_name=dataset_name,
            incident_id=incident_id,
            max_nodes=500,
            repo=repo,
            _identity=_identity,
        )
        return trace_aggregated_network(agg_graph, node_id, direction=direction, max_nodes=limit)

    @router.get("/incidents/{incident_id}/graph/aggregated")
    def incident_graph_aggregated(
        incident_id: Annotated[str, PathParam(min_length=1, max_length=128)],
        repo: Repository = Depends(_repository),
        _identity: dict[str, str] = Depends(_require("viewer")),
    ):
        with repo.sessions() as session:
            inc = session.get(IncidentRow, incident_id)
            if not inc:
                raise HTTPException(404, "Incident not found")
        return project_graph_aggregated(
            project_id="default",
            incident_id=incident_id,
            max_nodes=150,
            repo=repo,
            _identity=_identity,
        )

    @router.post("/projects/{project_id}/graph/relationships", status_code=201)
    def propose_graph_relationship(project_id: str, body: UserGraphRelationship,
            repo: Repository = Depends(_repository), identity: dict[str, str] = Depends(_require("analyst"))):
        graph, _ = project_graph(repo, project_id, max_records=50000)
        if body.left_node_id not in graph or body.right_node_id not in graph:
            raise HTTPException(422, "Both endpoints must be present in the confirmed-mapping graph")
        proposal_id = str(uuid.uuid4())
        payload = {"graph_relationships": [{**body.model_dump(), "approval_id": None}], "created_by": identity["actor"]}
        repo.add(RelationshipProposalRow(id=proposal_id, status="PENDING_APPROVAL", payload=payload))
        _audit(repo, "graph_relationship_proposed", identity["actor"], record_refs=[proposal_id, body.source_record_ref])
        return {"id": proposal_id, "status": "PENDING_APPROVAL", "flag": "USER_ENTERED", "created": False}

    @router.post("/graph/relationships/{proposal_id}/approve")
    def approve_graph_relationship(request: Request, proposal_id: str, body: DecisionBody,
            repo: Repository = Depends(_repository), identity: dict[str, Any] = Depends(_require("analyst"))):
        _check_mapping_role(request, identity, repo)
        proposal = repo.get(RelationshipProposalRow, proposal_id)
        if not proposal or not proposal.payload.get("graph_relationships"):
            raise HTTPException(404, "Graph relationship proposal not found")
        if proposal.status != "PENDING_APPROVAL":
            raise HTTPException(409, "Graph relationship proposal is not pending")
        proposal.status = "APPROVED"
        proposal.payload = {**proposal.payload, "approved_by": identity["actor"], "approval_reason": body.rationale,
                            "approved_at": datetime.now(timezone.utc).isoformat()}
        for relation in proposal.payload["graph_relationships"]:
            relation["approval_id"] = proposal.id
        repo.add(proposal)
        _audit(repo, "graph_relationship_approved", identity["actor"], record_refs=[proposal_id])
        return {"id": proposal_id, "status": "APPROVED", "flag": "USER_ENTERED", "created": True}

    @router.post("/incidents/assemble", status_code=201)
    def assemble_stored_incident(body: IncidentAssemblyRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("analyst"))):
        if not body.anomaly_ids and not body.prediction_ids:
            raise HTTPException(422, "Provide anomaly_ids or prediction_ids")
        anomalies_selected = [repo.get(AnomalyRow, item) for item in body.anomaly_ids]
        predictions_selected = [repo.get(PredictionRow, item) for item in body.prediction_ids]
        if any(item is None for item in anomalies_selected + predictions_selected):
            raise HTTPException(404, "One or more stored findings were not found")
        versions = {item.dataset_version_id for item in anomalies_selected + predictions_selected}
        if len(versions) != 1:
            raise HTTPException(422, "Incident assembly requires findings from one dataset version")
        version_id = next(iter(versions))
        sources = {item.source for item in anomalies_selected + predictions_selected}
        source = next(iter(sources)) if len(sources) == 1 else "combined"
        anomaly_items = [{**_payload(item), "record_ref": item.record_ref, "observed_value": item.observed_value,
                          "baseline": item.baseline, "feature": item.feature, "detector": item.detector,
                          "source": item.source} for item in anomalies_selected]
        prediction_items = [{**_payload(item), "record_refs": item.record_refs, "target": item.target,
                             "value": item.value, "model_version_id": item.model_version_id,
                             "predicted_at": item.predicted_at, "confidence": item.confidence,
                             "source": item.source} for item in predictions_selected]
        try:
            result = assemble_incident(source=source, anomalies=anomaly_items, predictions=prediction_items, title=body.title)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        incident = result["incident"]
        repo.add(IncidentRow(id=incident.id, dataset_version_id=version_id,
            prediction_id=predictions_selected[0].id if predictions_selected else None,
            source=incident.source, title=incident.title, occurred_at=incident.occurred_at,
            payload={**incident.model_dump(mode="json"), "description": incident.description,
                     "limitations": result["limitations"], "explanation": {"label": "evidence-ledger"}}))
        for evidence in result["evidence"]:
            repo.add(EvidenceRow(id=evidence.id, dataset_version_id=version_id, incident_id=incident.id,
                source=evidence.source, observed_at=evidence.observed_at, record_refs=evidence.record_refs,
                payload=evidence.model_dump(mode="json")))
        for hypothesis in result["hypotheses"]:
            repo.add(HypothesisRow(id=hypothesis.id, incident_id=incident.id, statement=hypothesis.statement,
                status=hypothesis.status.value, payload=hypothesis.model_dump(mode="json")))
        _audit(repo, "incident_assembled", identity["actor"], source=source, record_refs=[incident.id, *incident.record_refs])
        return {"incident": incident, "evidence": result["evidence"], "hypotheses": result["hypotheses"],
                "limitations": result["limitations"]}

    @router.post("/projects/{project_id}/drivers")
    def analyze_project_drivers(project_id: str, body: DriverAnalysisRequest,
            repo: Repository = Depends(_repository), _identity: dict[str, str] = Depends(_require("analyst"))):
        if body.project_id != project_id:
            raise HTTPException(422, "project_id does not match route")
        source = repo.get(DataSourceRow, body.source_id)
        if not source or source.project_id != project_id:
            raise HTTPException(404, "Source not found in project")
        graph, _ = project_graph(repo, project_id, max_records=50000)
        # Driver input is read from the accepted canonical import for this source only.
        job = max((item for item in repo.list_rows(ImportJobRow, limit=10000)
                   if item.data_source_id == source.id and item.status == "COMPLETED" and item.payload.get("processed_file")),
                  key=lambda item: item.created_at, default=None)
        if not job:
            raise HTTPException(409, "Source has no completed canonical import")
        path = Path(job.payload["processed_file"]).resolve()
        safe_root = (Path("data/processed/companies") / re.sub(r"[^A-Za-z0-9_-]", "_", repo.company_id)).resolve()
        if not path.is_relative_to(safe_root):
            raise HTTPException(409, "Canonical file is outside this company workspace")
        rows = []
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if len(rows) >= 50000:
                    break
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        driver_settings = load_settings().driver_analysis
        result = analyze_drivers(rows, body.affected_record_refs,
            min_affected=driver_settings.minimum_affected_support,
            min_baseline=driver_settings.minimum_baseline_support,
            alpha=driver_settings.adjusted_p_value_threshold,
            min_effect_size=driver_settings.minimum_effect_size,
            min_change_point_segment=driver_settings.minimum_change_point_segment,
            max_refs=driver_settings.maximum_record_references)
        for driver in result.get("drivers", []):
            driver["hypothesis_status"] = "UNVERIFIED"
            driver["status_label"] = _hypothesis_status_label("UNVERIFIED")
        return {**result, "source_id": source.id, "source": source.name,
                "interpretation": "correlation, not proof", "label": "ranked hypotheses"}

    @router.get("/risk/scoring-config")
    def get_company_risk_config(repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("viewer"))):
        rows = sorted(repo.list_rows(RiskScoringConfigRow, limit=1000), key=lambda item: item.created_at)
        active = next((row for row in reversed(rows) if row.payload.get("lifecycle") == "CURRENT"), None)
        if active:
            return active.payload
        defaults = load_settings().company_risk_scoring
        return CompanyRiskConfig(version="risk-v1", **defaults).model_dump(mode="json")

    @router.put("/risk/scoring-config")
    def set_company_risk_config(body: CompanyRiskConfigBody, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("admin"))):
        rows = repo.list_rows(RiskScoringConfigRow, limit=1000)
        # risk-v1 is the built-in default; uploaded candidates begin at v2.
        number = len(rows) + 2
        thresholds = body.thresholds
        try:
            config = CompanyRiskConfig(version=f"risk-v{number}", weights=body.weights, thresholds=thresholds)
        except Exception as exc:
            raise HTTPException(422, str(exc)) from exc
        payload = {**config.model_dump(mode="json"), "lifecycle": "CANDIDATE"}
        repo.add(RiskScoringConfigRow(id=str(uuid.uuid4()), version=config.version, payload=payload))
        _audit(repo, "risk_scoring_config_candidate_created", identity["actor"], details={"version": config.version})
        return {**payload, "acceptance_criteria": ["configuration passes CompanyRiskConfig validation",
                "reviewer provides a reason before promotion"]}

    @router.get("/risk/scoring-config/{version}/comparison")
    def compare_risk_config(version: str, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("analyst"))):
        rows = sorted(repo.list_rows(RiskScoringConfigRow, limit=1000), key=lambda item: item.created_at)
        candidate = next((row for row in rows if row.version == version), None)
        if candidate is None:
            raise HTTPException(404, "Risk configuration version not found")
        current = next((row for row in reversed(rows) if row.payload.get("lifecycle") == "CURRENT"), None)
        current_config = current.payload if current else CompanyRiskConfig(version="risk-v1",
            **load_settings().company_risk_scoring).model_dump(mode="json")
        compare_keys = ("weights", "thresholds")
        return {"candidate_version": candidate.version,
            "current_version": current.version if current else current_config["version"],
            "status": "COMPARISON_AVAILABLE", "changes": {key: {
                "current": current_config.get(key), "candidate": candidate.payload.get(key)}
                for key in compare_keys if current_config.get(key) != candidate.payload.get(key)},
            "acceptance_criteria": ["configuration passes CompanyRiskConfig validation",
                "explicit reviewer approval and reason required"],
            "performance_effect": "NOT_ESTIMATED; no verified outcome evaluation was used"}

    @router.post("/risk/scoring-config/{version}/promote")
    def promote_risk_config(version: str, body: ReasonRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("reviewer"))):
        rows = sorted(repo.list_rows(RiskScoringConfigRow, limit=1000), key=lambda item: item.created_at)
        candidate = next((row for row in rows if row.version == version), None)
        if candidate is None:
            raise HTTPException(404, "Risk configuration version not found")
        if candidate.payload.get("lifecycle") != "CANDIDATE":
            raise HTTPException(409, "Only a candidate configuration can be promoted")
        try:
            CompanyRiskConfig.model_validate({key: candidate.payload[key] for key in ("version", "weights", "thresholds")})
        except Exception as exc:
            raise HTTPException(409, "Candidate risk configuration failed validation") from exc
        current = next((row for row in reversed(rows) if row.payload.get("lifecycle") == "CURRENT"), None)
        if current:
            current.payload = {**current.payload, "lifecycle": "SUPERSEDED"}
            repo.add(current)
        candidate.payload = {**candidate.payload, "lifecycle": "CURRENT", "promoted_by": identity["actor"],
                             "promotion_reason": body.reason,
                             "promoted_at": datetime.now(timezone.utc).isoformat()}
        repo.add(candidate)
        _audit(repo, "risk_scoring_config_promoted", identity["actor"], record_refs=[candidate.id],
               details={"version": version, "previous_version": current.version if current else None,
                        "reason": body.reason})
        return candidate.payload

    @router.post("/risk/scoring-config/rollback")
    def rollback_risk_config(body: ReasonRequest, repo: Repository = Depends(_repository),
            identity: dict[str, str] = Depends(_require("reviewer"))):
        rows = sorted(repo.list_rows(RiskScoringConfigRow, limit=1000), key=lambda item: item.created_at)
        current = next((row for row in reversed(rows) if row.payload.get("lifecycle") == "CURRENT"), None)
        previous = next((row for row in reversed(rows) if row.payload.get("lifecycle") == "SUPERSEDED"), None)
        if current is None or previous is None:
            raise HTTPException(409, "No prior promoted risk configuration is available for rollback")
        current.payload = {**current.payload, "lifecycle": "ROLLED_BACK"}
        previous.payload = {**previous.payload, "lifecycle": "CURRENT", "rollback_by": identity["actor"],
                            "rollback_reason": body.reason,
                            "rolled_back_at": datetime.now(timezone.utc).isoformat()}
        repo.add(current)
        repo.add(previous)
        _audit(repo, "risk_scoring_config_rolled_back", identity["actor"], record_refs=[previous.id, current.id],
               details={"from_version": current.version, "to_version": previous.version, "reason": body.reason})
        return {"status": "ROLLED_BACK", "current_version": previous.version, "previous_version": current.version}

    @router.post("/risk/score")
    def company_risk_score(body: RiskScoreRequest, repo: Repository = Depends(_repository),
            _identity: dict[str, str] = Depends(_require("analyst"))):
        rows = sorted(repo.list_rows(RiskScoringConfigRow, limit=1000), key=lambda item: item.created_at)
        active = next((row for row in reversed(rows) if row.payload.get("lifecycle") == "CURRENT"), None)
        config_payload = {key: active.payload[key] for key in ("version", "weights", "thresholds")} if active else None
        config = (CompanyRiskConfig.model_validate(config_payload) if config_payload else
                  CompanyRiskConfig(version="risk-v1", **load_settings().company_risk_scoring))
        try:
            return score_company_risk(config=config,
                likelihood=body.likelihood, likelihood_calibrated=body.likelihood_calibrated,
                impact=body.impact, evidence_strength=body.evidence_strength, uncertainty=body.uncertainty)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/pipeline/previews", status_code=201)
    def create_pipeline_preview(body: ProjectRunRequest, repo: Repository = Depends(_repository),
                                identity: dict[str, str] = Depends(_require("analyst"))):
        capabilities = _project_capability_report(repo, body.project_id)
        preview = preview_pipeline(capabilities)
        row = PipelineRunRow(id=preview["id"], project_id=body.project_id, status="PREVIEW",
            payload={**preview, "capabilities": capabilities, "created_by": identity["actor"],
                     "created_at": datetime.now(timezone.utc).isoformat()})
        repo.add(row)
        return preview

    @router.get("/pipeline/runs/{run_id}")
    def get_project_pipeline_run(run_id: Annotated[str, PathParam(min_length=1, max_length=128)],
                                 repo: Repository = Depends(_repository),
                                 _identity: dict[str, str] = Depends(_require("viewer"))):
        row = repo.get(PipelineRunRow, run_id)
        if row is None:
            raise HTTPException(404, detail="Pipeline run not found")
        return {"id": row.id, "project_id": row.project_id, "status": row.status, **row.payload}

    @router.post("/pipeline/previews/{preview_id}/accept", status_code=202)
    def accept_pipeline_preview(preview_id: Annotated[str, PathParam(min_length=1, max_length=128)],
                                background_tasks: BackgroundTasks,
                                repo: Repository = Depends(_repository),
                                identity: dict[str, str] = Depends(_require("analyst"))):
        row = repo.get(PipelineRunRow, preview_id)
        if row is None or row.status != "PREVIEW":
            raise HTTPException(404, detail="Unaccepted pipeline preview not found")
        if row.payload.get("dry_run") is not True:
            raise HTTPException(409, detail="Pipeline preview is not a dry run")
        if not any(item.get("status") == "ACCEPTED" for item in row.payload["capabilities"].get("sources", [])):
            # Mapping approval is the source of canonical roles; capability output is the authority.
            if row.payload["capabilities"].get("approved_mapping_count", 0) == 0:
                raise HTTPException(409, detail="Approve at least one mapping before accepting a pipeline preview")
        row.status = "QUEUED"
        row.payload = {**row.payload, "dry_run": False, "accepted_by": identity["actor"],
                       "accepted_at": datetime.now(timezone.utc).isoformat(),
                       "steps": [{**step, "status": "QUEUED"} for step in row.payload.get("steps", [])]}
        repo.add(row)
        background_tasks.add_task(_execute_project_pipeline, repo, row.id, row.project_id)
        _audit(repo, "pipeline_preview_accepted", identity["actor"], record_refs=[row.id],
               details={"project_id": row.project_id, "dry_run": False})
        return {"id": row.id, "status": "QUEUED", "dry_run": False,
                "message": "Accepted preview queued for canonical pipeline execution."}

    app.include_router(router)
    return app


app = create_app()
