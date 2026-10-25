"""Typed access to project settings."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ThresholdSettings(BaseModel):
    min_data_quality: float = Field(ge=0, le=1)
    minimum_hypothesis_evidence: int = Field(ge=0)


class WeightSettings(BaseModel):
    recency: float = Field(ge=0)
    severity: float = Field(ge=0)
    confidence: float = Field(ge=0)


class OperationSettings(BaseModel):
    dry_run: bool = True
    kill_switch: bool = False
    rate_limit_actions: int = Field(gt=0)
    rate_limit_window_seconds: int = Field(gt=0)


class DataSettings(BaseModel):
    freshness_max_age_hours: int = Field(gt=0)
    max_null_fraction: float = Field(ge=0, le=1)
    csv_chunk_rows: int = Field(gt=0)


class UploadSettings(BaseModel):
    max_size_bytes: int = Field(gt=0)
    chunk_bytes: int = Field(gt=0)
    chunk_rows: int = Field(gt=0)
    max_zip_entries: int = Field(gt=0)
    max_zip_uncompressed_bytes: int = Field(gt=0)
    max_zip_compression_ratio: float = Field(gt=0)


class AuditSettings(BaseModel):
    log_path: str


class AnomalySettings(BaseModel):
    robust_z_threshold: float = Field(gt=0)
    iqr_multiplier: float = Field(gt=0)
    isolation_forest_contamination: float = Field(gt=0, lt=0.5)
    isolation_forest_estimators: int = Field(gt=0)
    random_seed: int
    rule_thresholds: dict[str, float]
    canonical_metrics: dict[str, dict[str, Any]]
    rolling_window_records: int = Field(gt=0)
    minimum_baseline_records: int = Field(ge=2)
    seasonality_minimum_records: int = Field(ge=2)


class DelayPredictionSettings(BaseModel):
    prediction_time_role: str
    label_role: str
    feature_allowlist: list[str]
    feature_availability: dict[str, str]
    blocked_feature_roles: list[str]
    train_fraction: float = Field(gt=0, lt=1)
    validation_fraction: float = Field(gt=0, lt=1)
    minimum_training_rows: int = Field(gt=0)
    probability_threshold: float = Field(ge=0, le=1)
    random_seed: int


class ForecastSettings(BaseModel):
    allowed_granularities: list[str]
    daily_max_span_days: int = Field(gt=0)
    weekly_min_span_days: int = Field(gt=0)
    monthly_min_span_days: int = Field(gt=0)
    minimum_history_periods: int = Field(gt=0)
    moving_average_periods: int = Field(gt=0)
    seasonal_periods: dict[str, int]
    prediction_interval_level: float = Field(gt=0, lt=1)
    backtest_folds: int = Field(gt=0)
    horizon_periods: int = Field(gt=0)


class RiskSettings(BaseModel):
    weights: dict[str, float]
    freshness_max_age_hours: int = Field(gt=0)
    count_saturation: int = Field(gt=0)
    supplier_exposure_saturation: int = Field(gt=0)
    recurrence_saturation: int = Field(gt=0)
    minimum_supporting_evidence: int = Field(gt=0)
    minimum_evidence_strength: float = Field(ge=0, le=1)


class DriverAnalysisSettings(BaseModel):
    minimum_affected_support: int = Field(gt=0)
    minimum_baseline_support: int = Field(gt=0)
    adjusted_p_value_threshold: float = Field(gt=0, lt=1)
    minimum_effect_size: float = Field(ge=0, le=1)
    minimum_change_point_segment: int = Field(gt=0)
    maximum_record_references: int = Field(gt=0)


class WorkflowSettings(BaseModel):
    timer_interval_seconds: int = Field(gt=0)
    max_attempts: int = Field(gt=0)
    retry_backoff_seconds: float = Field(ge=0)


class ConnectorSettings(BaseModel):
    scheduled_folder: str
    folder_chunk_rows: int = Field(gt=0)
    rest_endpoint_env: str
    rest_token_env: str
    rest_timeout_seconds: int = Field(gt=0)
    database_url_env: str
    database_table: str
    database_chunk_rows: int = Field(gt=0)
    notifications_enabled_env: str


class StorageSettings(BaseModel):
    url: str


class PipelineSettings(BaseModel):
    max_predictions_per_dataset: int = Field(ge=0)
    max_investigations_per_dataset: int = Field(ge=0)
    max_persisted_anomalies_per_dataset: int = Field(ge=0)
    enable_isolation_forest: bool = True
    retry_attempts: int = Field(gt=0)
    retry_backoff_seconds: float = Field(ge=0)
    severity_thresholds: dict[str, int]
    feature_thresholds: dict[str, float]


class DriftSettings(BaseModel):
    max_row_count_change_fraction: float = Field(ge=0)
    max_null_rate_change: float = Field(ge=0, le=1)
    max_numeric_mean_shift: float = Field(default=1.0, ge=0)
    max_category_concentration_change: float = Field(default=0.2, ge=0, le=1)


class ModelPromotionSettings(BaseModel):
    primary_metric: str = "macro_f1"
    minimum_improvement: float = 0.0
    maximum_brier_increase: float | None = Field(default=None, ge=0)
    require_brier: bool = False


class ValidationSettings(BaseModel):
    missing_required: bool = True
    duplicates: bool = True
    invalid_dates: bool = True
    negative_quantity: bool = True
    broken_relationships: bool = True
    unit_currency_consistency: bool = True
    schema_change: bool = True
    outliers: bool = True
    outlier_iqr_multiplier: float = Field(default=1.5, gt=0)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    thresholds: ThresholdSettings
    weights: WeightSettings
    operations: OperationSettings
    data: DataSettings
    uploads: UploadSettings
    audit: AuditSettings
    anomaly: AnomalySettings
    delay_prediction: DelayPredictionSettings
    forecasting: ForecastSettings
    evaluation: dict[str, Any]
    risk: RiskSettings
    company_risk_scoring: dict[str, Any]
    driver_analysis: DriverAnalysisSettings
    workflow: WorkflowSettings
    connectors: ConnectorSettings
    recommendations: dict[str, Any]
    alerts: dict[str, Any]
    actions: dict[str, Any]
    storage: StorageSettings
    pipeline: PipelineSettings
    drift: DriftSettings
    model_promotion: ModelPromotionSettings
    validation: ValidationSettings

    @property
    def dry_run(self) -> bool:
        return self.operations.dry_run

    @property
    def kill_switch(self) -> bool:
        return self.operations.kill_switch


def load_settings(path: Path | str | None = None) -> Settings:
    """Load config from YAML; resolve default relative to repository root."""
    config_path = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
    data: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Settings YAML must contain a mapping")
    return Settings.model_validate(data)
