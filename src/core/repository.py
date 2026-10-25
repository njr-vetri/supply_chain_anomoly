"""SQLAlchemy persistence models and repository for local-first storage.

Only Repository exposes writes to application code. The URL is read from YAML so
the SQLAlchemy dialect can be swapped without changing pipeline code.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    __abstract__ = True
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CompanyRow(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantBase(Base):
    __abstract__ = True
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True, default="local")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class UserRow(TenantBase):
    """Company-scoped user account with hashed credentials and role."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="viewer")
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_project_id: Mapped[str | None] = mapped_column(String, nullable=True)


class ApiKeyRow(TenantBase):
    """Company-scoped machine access key (hashed, revocable, maximum analyst role)."""
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    key_hash: Mapped[str] = mapped_column(String, index=True)
    prefix: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="viewer")
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanySettingRow(TenantBase):
    """Company-scoped persistent settings (e.g. kill switch, mapping policy)."""
    __tablename__ = "company_settings"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String, index=True)
    setting_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WorkspaceRow(TenantBase):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)


class ProjectRow(TenantBase):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String)


class DataSourceRow(TenantBase):
    __tablename__ = "data_sources"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)
    location_ref: Mapped[str] = mapped_column(String)


class MappingVersionRow(TenantBase):
    __tablename__ = "mapping_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    version: Mapped[str] = mapped_column(String)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="PENDING_REVIEW")


class ImportJobRow(TenantBase):
    __tablename__ = "import_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    dataset_version_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RelationshipProposalRow(TenantBase):
    """A reviewed multi-source key relationship; pending proposals are not active links."""
    __tablename__ = "relationship_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="PENDING_APPROVAL")


class RiskScoringConfigRow(TenantBase):
    """Immutable per-company risk-scoring configuration versions."""
    __tablename__ = "risk_scoring_configs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PipelineRunRow(TenantBase):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DatasetVersionRow(TenantBase):
    __tablename__ = "dataset_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String)
    source_hash: Mapped[str] = mapped_column(String, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    license_status: Mapped[str] = mapped_column(String, default="UNKNOWN")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ModelVersionRow(TenantBase):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    artifact_hash: Mapped[str] = mapped_column(String)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    training_data_version: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PredictionRow(TenantBase):
    __tablename__ = "predictions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    source: Mapped[str] = mapped_column(String)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target: Mapped[str] = mapped_column(String)
    value: Mapped[Any] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    record_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AnomalyRow(TenantBase):
    __tablename__ = "anomalies"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    source: Mapped[str] = mapped_column(String)
    detector: Mapped[str] = mapped_column(String)
    record_ref: Mapped[str] = mapped_column(String)
    feature: Mapped[str] = mapped_column(String)
    observed_value: Mapped[Any] = mapped_column(JSON)
    baseline: Mapped[Any] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IncidentRow(TenantBase):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    prediction_id: Mapped[str | None] = mapped_column(ForeignKey("predictions.id"), nullable=True)
    source: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class EvidenceRow(TenantBase):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    source: Mapped[str] = mapped_column(String)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    record_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class HypothesisRow(TenantBase):
    __tablename__ = "hypotheses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RecommendationRow(TenantBase):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("hypotheses.id"), nullable=True)
    source: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ApprovalRow(TenantBase):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"))
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ActionRow(TenantBase):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"))
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    source: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    dry_run: Mapped[bool] = mapped_column(default=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class OutcomeRow(TenantBase):
    __tablename__ = "outcomes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"))
    prediction_id: Mapped[str | None] = mapped_column(ForeignKey("predictions.id"), nullable=True)
    source: Mapped[str] = mapped_column(String)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditEventRow(TenantBase):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_hash: Mapped[str] = mapped_column(String)
    event_hash: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class QualitySnapshotRow(TenantBase):
    __tablename__ = "quality_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    source: Mapped[str] = mapped_column(String, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(Integer)
    null_rates: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    drift: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Repository:
    """Small transaction boundary; backend chosen solely by SQLAlchemy URL."""
    def __init__(self, url: str, *, company_id: str, engine: Engine | None = None):
        if not company_id or not company_id.strip():
            raise ValueError("company_id is required")
        self.company_id = company_id.strip()
        if engine is None and url.startswith("sqlite:") and ":memory:" not in url:
            database = url.removeprefix("sqlite:///")
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = engine or create_engine(url, future=True)
        if self.engine.dialect.name == "sqlite":
            from sqlalchemy import event

            @event.listens_for(self.engine, "connect")
            def enable_foreign_keys(connection, _record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        self.sessions = sessionmaker(self.engine, expire_on_commit=False, class_=Session)
        from sqlalchemy import event
        scope_company_id = self.company_id

        @event.listens_for(self.sessions, "do_orm_execute")
        def apply_company_scope(execute_state):
            if execute_state.is_select:
                from sqlalchemy.orm import with_loader_criteria
                execute_state.statement = execute_state.statement.options(
                    with_loader_criteria(TenantBase, lambda row: row.company_id == scope_company_id,
                                         include_aliases=True))
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            if session.get(CompanyRow, self.company_id) is None:
                session.add(CompanyRow(id=self.company_id, company_id=self.company_id, name="Local workspace"))

    def add(self, row: Base) -> None:
        self._scope_write(row)
        with self.sessions.begin() as session:
            session.add(row)

    def add_many(self, rows: list[Base]) -> None:
        if rows:
            for row in rows:
                self._scope_write(row)
            with self.sessions.begin() as session:
                session.add_all(rows)

    def _scope_write(self, row: Base) -> None:
        if not isinstance(row, TenantBase):
            raise TypeError("Repository writes require a company-scoped row")
        if row.company_id not in {None, "local", self.company_id}:
            raise PermissionError("Cannot write a row owned by another company")
        row.company_id = self.company_id

    def get(self, model: type[TenantBase], row_id: str, *, include_deleted: bool = False):
        """Read a row only inside this repository's required company scope."""
        with self.sessions() as session:
            query = select(model).where(model.id == row_id, model.company_id == self.company_id)
            if not include_deleted:
                query = query.where(model.deleted_at.is_(None))
            return session.scalar(query)

    def list_rows(self, model: type[TenantBase], *, include_deleted: bool = False, limit: int = 1000):
        with self.sessions() as session:
            query = select(model).where(model.company_id == self.company_id)
            if not include_deleted:
                query = query.where(model.deleted_at.is_(None))
            return list(session.scalars(query.limit(limit)).all())

    def soft_delete(self, model: type[TenantBase], row_id: str, *, actor: str, reason: str) -> bool:
        row = self.get(model, row_id)
        if row is None:
            return False
        row.deleted_at = now_utc()
        self.add(row)
        from src.core.audit import GENESIS_HASH
        from src.core.privacy import sanitize_for_log
        with self.sessions() as session:
            last_event = session.scalar(select(AuditEventRow).where(
                AuditEventRow.company_id == self.company_id).order_by(AuditEventRow.occurred_at.desc()).limit(1))
        previous = last_event.event_hash if last_event else GENESIS_HASH
        occurred = now_utc()
        refs = [row_id]
        details = sanitize_for_log({"record_type": model.__tablename__, "reason": reason[:500]})
        event_payload = {"event_type": "record_soft_deleted", "actor": actor, "source": "repository",
                         "record_refs": refs, "details": details}
        canonical = json.dumps({"previous_hash": previous, **event_payload}, sort_keys=True,
                               separators=(",", ":"), default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.add(AuditEventRow(id=f"soft-delete:{row_id}:{occurred.isoformat()}",
            event_type=event_payload["event_type"], actor=actor, source="repository", occurred_at=occurred,
            previous_hash=previous, event_hash=digest,
            payload={"record_type": model.__tablename__, "record_refs": refs, "details": details}))
        return True

    def dataset_version(self, dataset: str, source: str, source_hash: str,
                        payload: dict[str, Any]) -> DatasetVersionRow:
        with self.sessions() as session:
            found = session.scalar(select(DatasetVersionRow).where(
                DatasetVersionRow.dataset == dataset, DatasetVersionRow.source_hash == source_hash,
                DatasetVersionRow.company_id == self.company_id))
            if found:
                return found
            row = DatasetVersionRow(id=payload["id"], dataset=dataset, source=source,
                                    source_hash=source_hash, observed_at=payload["observed_at"],
                                    license_status="UNKNOWN", payload={**payload,
                                        "observed_at": payload["observed_at"].isoformat()})
            row.company_id = self.company_id
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def prior_quality(self, source: str) -> QualitySnapshotRow | None:
        with self.sessions() as session:
            return session.scalar(select(QualitySnapshotRow).where(QualitySnapshotRow.source == source,
                                  QualitySnapshotRow.company_id == self.company_id,
                                  QualitySnapshotRow.deleted_at.is_(None))
                                  .order_by(QualitySnapshotRow.observed_at.desc()).limit(1))

    def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = "viewer",
        email: str | None = None,
        user_id: str | None = None,
    ) -> UserRow:
        row = UserRow(
            id=user_id or str(uuid.uuid4()),
            username=username.strip(),
            email=(email or f"{username}@{self.company_id}.local").strip(),
            password_hash=password_hash,
            role=role,
            is_active=True,
        )
        row.company_id = self.company_id
        self.add(row)
        return row

    def get_user_by_username(self, username: str) -> UserRow | None:
        with self.sessions() as session:
            query = select(UserRow).where(
                UserRow.username == username.strip(),
                UserRow.company_id == self.company_id,
                UserRow.deleted_at.is_(None),
            )
            return session.scalar(query)

    def get_user_by_email_or_username(self, identifier: str) -> UserRow | None:
        val = identifier.strip().lower()
        with self.sessions() as session:
            query = select(UserRow).where(
                (func.lower(UserRow.email) == val) | (func.lower(UserRow.username) == val),
                UserRow.company_id == self.company_id,
                UserRow.deleted_at.is_(None),
            )
            return session.scalar(query)

    def list_users(self) -> list[UserRow]:
        return self.list_rows(UserRow)

    def get_user_by_id(self, user_id: str) -> UserRow | None:
        return self.get(UserRow, user_id)

    def create_company(self, company_id: str, name: str) -> CompanyRow:
        with self.sessions.begin() as session:
            existing = session.get(CompanyRow, company_id.strip())
            if existing:
                existing.name = name.strip()
                return existing
            row = CompanyRow(id=company_id.strip(), company_id=company_id.strip(), name=name.strip())
            session.add(row)
            return row

    def get_company(self, company_id: str) -> CompanyRow | None:
        with self.sessions() as session:
            return session.get(CompanyRow, company_id)

    def get_setting(self, key: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.scalar(select(CompanySettingRow).where(
                CompanySettingRow.company_id == self.company_id,
                CompanySettingRow.setting_key == key,
                CompanySettingRow.deleted_at.is_(None),
            ))
            return row.setting_value if row else None

    def set_setting(self, key: str, value: dict[str, Any]) -> None:
        row_id = f"setting:{self.company_id}:{key}"
        with self.sessions.begin() as session:
            existing = session.get(CompanySettingRow, row_id)
            if existing:
                existing.setting_value = value
                existing.deleted_at = None
            else:
                row = CompanySettingRow(id=row_id, setting_key=key, setting_value=value)
                row.company_id = self.company_id
                session.add(row)

    def get_kill_switch(self) -> bool:
        from src.core.config import load_settings
        setting = self.get_setting("kill_switch")
        if setting is not None and "enabled" in setting:
            return bool(setting["enabled"])
        return load_settings().kill_switch

    def set_kill_switch(self, enabled: bool, reason: str = "") -> None:
        self.set_setting("kill_switch", {"enabled": bool(enabled), "reason": reason})

    def create_api_key(
        self,
        name: str,
        key_hash: str,
        prefix: str,
        role: str = "viewer",
        scopes: list[str] | None = None,
    ) -> ApiKeyRow:
        row = ApiKeyRow(
            id=str(uuid.uuid4()),
            name=name.strip(),
            key_hash=key_hash,
            prefix=prefix,
            role=role if role in ("viewer", "analyst") else "analyst",
            scopes=scopes or ["read", "write"],
        )
        row.company_id = self.company_id
        self.add(row)
        return row

    def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRow | None:
        with self.sessions() as session:
            query = select(ApiKeyRow).where(
                ApiKeyRow.key_hash == key_hash,
                ApiKeyRow.company_id == self.company_id,
                ApiKeyRow.deleted_at.is_(None),
                ApiKeyRow.revoked_at.is_(None),
            )
            return session.scalar(query)

    def list_api_keys(self) -> list[ApiKeyRow]:
        return [k for k in self.list_rows(ApiKeyRow) if k.revoked_at is None]

    def revoke_api_key(self, key_id: str) -> bool:
        key = self.get(ApiKeyRow, key_id)
        if not key or key.revoked_at is not None:
            return False
        key.revoked_at = now_utc()
        self.add(key)
        return True

    def counts(self) -> dict[str, int]:
        tables = {"users": UserRow, "workspaces": WorkspaceRow, "projects": ProjectRow, "data_sources": DataSourceRow,
                  "mapping_versions": MappingVersionRow, "import_jobs": ImportJobRow,
                  "pipeline_runs": PipelineRunRow,
                  "dataset_versions": DatasetVersionRow, "model_versions": ModelVersionRow,
                  "predictions": PredictionRow, "anomalies": AnomalyRow, "incidents": IncidentRow,
                  "evidence": EvidenceRow, "hypotheses": HypothesisRow,
                  "recommendations": RecommendationRow, "approvals": ApprovalRow,
                  "actions": ActionRow, "outcomes": OutcomeRow, "audit_events": AuditEventRow}
        with self.sessions() as session:
            return {name: int(session.scalar(select(func.count()).select_from(model).where(
                        model.company_id == self.company_id, model.deleted_at.is_(None))) or 0)
                    for name, model in tables.items()}

    def daily_summary(self, day_start: datetime, day_end: datetime) -> dict[str, Any]:
        with self.sessions() as session:
            # Domain rows keep their creation timestamp in the JSON payload; audit rows have a typed timestamp.
            events = session.scalars(select(AuditEventRow).where(
                AuditEventRow.occurred_at >= day_start, AuditEventRow.occurred_at < day_end)).all()
            dataset_counts = session.execute(select(DatasetVersionRow.dataset, func.count())
                .where(DatasetVersionRow.created_at >= day_start, DatasetVersionRow.created_at < day_end,
                       DatasetVersionRow.company_id == self.company_id, DatasetVersionRow.deleted_at.is_(None))
                .group_by(DatasetVersionRow.dataset)).all()
            tables = {"users": UserRow, "dataset_versions": DatasetVersionRow, "model_versions": ModelVersionRow,
                      "predictions": PredictionRow, "anomalies": AnomalyRow, "incidents": IncidentRow,
                      "evidence": EvidenceRow, "hypotheses": HypothesisRow,
                      "recommendations": RecommendationRow, "approvals": ApprovalRow,
                      "actions": ActionRow, "outcomes": OutcomeRow, "audit_events": AuditEventRow,
                      "quality_snapshots": QualitySnapshotRow}
            created_today = {name: int(session.scalar(select(func.count()).select_from(model).where(
                model.created_at >= day_start, model.created_at < day_end,
                model.company_id == self.company_id, model.deleted_at.is_(None))) or 0)
                for name, model in tables.items()}
            by_source: dict[str, dict[str, int]] = {}
            for name, model in {"predictions": PredictionRow, "anomalies": AnomalyRow,
                                "incidents": IncidentRow, "evidence": EvidenceRow,
                                "recommendations": RecommendationRow}.items():
                pairs = session.execute(select(model.source, func.count()).where(
                    model.created_at >= day_start, model.created_at < day_end,
                    model.company_id == self.company_id, model.deleted_at.is_(None)).group_by(model.source)).all()
                for source, total in pairs:
                    by_source.setdefault(str(source), {})[name] = int(total)
            return {"period_start": day_start.isoformat(), "period_end": day_end.isoformat(),
                    "dataset_versions_by_dataset": {str(dataset): int(total) for dataset, total in dataset_counts},
                    "audit_events": len(events), "event_types": _count_values(event.event_type for event in events),
                    "rows_created_today": created_today, "entity_counts_by_source": by_source,
                    "total_rows_stored": self.counts()}


def _count_values(values) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result
