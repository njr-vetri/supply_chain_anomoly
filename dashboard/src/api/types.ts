// API types – all fields reflect what the backend actually returns.
// UNKNOWN is used wherever the backend does not supply a value.

export type FindingKind =
  | 'FACT'
  | 'PREDICTION'
  | 'HYPOTHESIS'
  | 'RECOMMENDATION'
  | 'SYNTHETIC'
  | 'SIMULATED'
  | 'DRY_RUN'

export type Role = 'viewer' | 'analyst' | 'reviewer' | 'admin'
export type HypothesisStatus = 'UNVERIFIED' | 'SUPPORTED' | 'CONFIRMED' | 'REJECTED' | 'CLOSED'
export type ImportStatus = 'QUEUED' | 'RUNNING' | 'PARTIAL' | 'FAILED' | 'COMPLETED'
export type MappingStatus = 'PENDING_REVIEW' | 'ACCEPTED' | 'REJECTED'
export type CapabilityStatus = 'AVAILABLE' | 'AVAILABLE_WITH_LIMITATIONS' | 'AWAITING_CONFIGURATION' | 'UNSUPPORTED' | 'NOT_IMPLEMENTED'
export type EdgeKind = 'ESTABLISHED' | 'INFERRED' | 'USER_ENTERED'
export type HealthStatus = 'HEALTHY' | 'WATCH' | 'PROBLEM' | 'AT_RISK' | 'INCIDENT' | 'UNKNOWN'

// ── Core shared ────────────────────────────────────────────────────────────────

export interface Page<T> { items: T[]; count: number }
export interface Health { status: string; api_version: string }

// ── Quality / drift ────────────────────────────────────────────────────────────

export interface QualityItem {
  source: string; observed_at: string; row_count: number
  null_rates: Record<string, number>; drift: Record<string, unknown>; fresh: boolean
}

export interface DriftResult {
  dataset_name: string
  drift_is_warning_only: true
  triggers_automatic_retrain: false
  warning: string
  schema_changes: {
    added: string[]; removed: string[]; retyped: Record<string, { from: string; to: string }>
  }
  feature_drift: Record<string, {
    mean_shift?: number | null; std_shift?: number | null
    null_rate_change?: number | null; severity: string
  }>
  baseline_observed_at?: string | null
  current_observed_at?: string | null
}

// ── Datasets / uploads ─────────────────────────────────────────────────────────

export interface DatasetSource {
  source_id: string; dataset_name: string; status: string
  mapping_status?: MappingStatus | null; sha256?: string | null
  uploaded_at?: string | null; monitoring?: boolean
}

export interface ImportJob {
  import_job_id: string; status: ImportStatus
  processed_rows?: number | null; total_rows?: number | null
  sha256?: string | null; dataset_name?: string | null
  error?: string | null; created_at?: string | null
}

export interface MappingVersion {
  version: string; status: MappingStatus
  mappings: Record<string, string>; custom_fields?: Record<string, string>
  units?: Record<string, string>; time_zone?: string | null; date_format?: string | null
  reason?: string | null; reviewed_at?: string | null; reviewer_id?: string | null
}

export interface MappingSuggestion {
  column: string; suggested_role: string | null; confidence: number
  reason: string; needs_clarification?: boolean
}

export interface CapabilityResult {
  name: string; status: CapabilityStatus
  missing_roles?: string[]; limitations?: string[]
}

export interface RelationshipPreview {
  proposal_id?: string | null
  links: Array<{
    left_source_id: string; left_key: string
    right_source_id: string; right_key: string
    matched: number; orphan_left: number; orphan_right: number; null_keys: number
  }>
  status?: string | null
}

// ── Incidents ──────────────────────────────────────────────────────────────────

export interface Incident {
  id: string; title: string; description: string; source: string; record_refs: string[]
  occurred_at: string; evidence_refs: string[]; hypothesis_refs: string[]
}

export interface Evidence {
  id: string; evidence_type: string; source: string; record_refs: string[]
  observed_at: string; facts: Record<string, unknown>; content_hash?: string | null
}

export interface ReviewEntry {
  reviewed_at: string; reviewer_id: string
  previous_status: HypothesisStatus; new_status: HypothesisStatus; rationale: string
}

export interface Hypothesis {
  id: string; statement: string; status: HypothesisStatus; evidence_refs: string[]
  source: string; record_refs: string[]; review_history: ReviewEntry[]; created_at?: string
}

export interface IncidentDetail extends Incident {
  evidence: Evidence[]; hypotheses: Hypothesis[]
  explanation: Record<string, unknown>; limitations: string[]
}

// ── Predictions / anomalies ────────────────────────────────────────────────────

export interface Prediction {
  id: string; target: string; value: string | number | boolean
  model_version_id: string; source: string; record_refs: string[]
  predicted_at: string; confidence?: number | null; limitations: string[]
}

export interface Anomaly {
  id: string; source: string; detector: string; record_ref: string
  feature: string; observed_value: unknown; baseline: unknown
  severity?: string | null; created_at?: string
}

// ── Recommendations / approvals / actions ──────────────────────────────────────

export interface Recommendation {
  id: string; action: string; rationale: string
  evidence_refs: string[]; prediction_refs: string[]; hypothesis_refs: string[]
  source: string; record_refs: string[]; human_approval_required: boolean
  incident_id?: string; priority_breakdown?: Record<string, unknown>
  assumptions?: string[]; uncertainty?: string; constraints?: string[]; created_at?: string
}

export interface Approval {
  id: string; recommendation_id: string; reviewer_id?: string | null
  status: string; approved?: boolean | null; reviewed_at: string; rationale: string
}

export interface Action {
  id: string; recommendation_id: string; approval_id?: string | null
  source: string; record_refs: string[]; dry_run: boolean
  executed_at?: string | null; status: string; created_at?: string
}

export interface Outcome {
  id: string; action_id: string; source: string; record_refs: string[]
  observed_at: string; facts: Record<string, unknown>; limitations: string[]
}

// ── Alerts ────────────────────────────────────────────────────────────────────

export interface AlertHistoryItem {
  group_id?: string; event_type?: string; type?: string
  source?: string; occurred_at?: string; created_at?: string
  acknowledged?: boolean; assigned_to?: string | null
  [key: string]: unknown
}

// ── Supply-chain graph ─────────────────────────────────────────────────────────

export interface SupplyGraphNode {
  id: string; type: string; source?: string
  health?: HealthStatus | null; exposure_count?: number | null
  incident_count?: number | null; evidence_refs?: string[]
  payload?: Record<string, unknown>
}

export interface SupplyGraphEdge {
  from: string; to: string; type: string; meaning?: string
  source_ref?: string; status: EdgeKind
  valid_from?: string | null; valid_to?: string | null
}

export interface SupplyGraphResponse {
  nodes: SupplyGraphNode[]; edges: SupplyGraphEdge[]
  count?: number; capped?: boolean
}

// ── Models / evaluation ───────────────────────────────────────────────────────

export interface ModelVersion {
  id?: string; name?: string; version?: string
  artifact_hash?: string; trained_at?: string | null
  training_data_version?: string; limitations?: string[]
  payload?: Record<string, unknown>
}

export interface ModelMetrics {
  model_version_id: string; metrics: Record<string, unknown>; limitations: string[]
}

export interface EvalOutcomeResult {
  status?: string; message?: string
  forecast_mae?: number | null; forecast_mape?: number | null; forecast_bias?: number | null
  prediction_accuracy?: number | null; precision?: number | null; recall?: number | null
  brier_score?: number | null; confusion_matrix?: unknown
  alert_precision?: number | null; missed_events?: number | null
  [key: string]: unknown
}

// ── Incident graph (existing, incident-level) ─────────────────────────────────

export interface GraphResponse {
  nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>>
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export interface AuditEvent {
  id: string; event_type: string; actor: string; source?: string | null
  record_refs: string[]; occurred_at: string
  details: Record<string, unknown>; previous_hash: string; event_hash: string
}

// ── Request / response helpers ────────────────────────────────────────────────

export interface ApiErrorBody { error: { code: string; message: string; details?: unknown } }
export interface PipelineDryRunResult {
  status: string; executed: boolean; message: string; datasets: string[]; kill_switch: boolean
}
export interface HypothesisCreateRequest { incident_id: string; statement: string; source: string; record_refs?: string[] }
export interface HypothesisReviewRequest { status: HypothesisStatus; rationale: string }
export interface ApprovalCreateRequest { recommendation_id: string }
export interface DecisionRequest { rationale: string }
export interface ActionCreateRequest {
  recommendation_id: string; action_class: 'READ_ONLY' | 'LOW_IMPACT_REVERSIBLE' | 'HIGH_IMPACT'
  approval_id?: string | null
}
export interface KillSwitchRequest { enabled: boolean; reason: string }
export interface WhatIfScenario { name: string; assumed_relative_probability_reduction: number; assumptions: string[] }
export interface WhatIfRequest {
  affected_order_count: number; calibrated_delay_probability: number
  probability_calibrated: boolean; scenarios: WhatIfScenario[]
}

// ── Aggregated Supply-Chain Network (Functionality 5 Redesign) ─────────────

export interface PeerMetricBaseline {
  node_value: number
  peer_mean: number
  peer_std: number
  z_score: number
}

export interface NodeHealthSnapshot {
  bucket: string
  exposure: number
  anomalies: number
  health: HealthStatus
}

export interface AggregatedGraphNode {
  id: string
  label: string
  type: string
  exposure: number
  health: HealthStatus
  health_reason?: string
  metrics_vs_peer_baseline?: Record<string, PeerMetricBaseline>
  anomaly_count: number
  evidence_refs: string[]
  time_series: NodeHealthSnapshot[]
  clustered_count?: number
  clustered_node_ids?: string[]
  candidate_source_rank?: number | null
  culprit?: boolean
  affected?: boolean
}

export interface AggregatedGraphEdge {
  source: string
  target: string
  type: string
  weight: number
  flag: EdgeKind
  source_refs: string[]
}

export interface CandidateSource {
  node_id: string
  label: string
  type: string
  score: number
  anomaly_count: number
  exposure: number
  rank: number
  health: HealthStatus
  disclaimer: string
}

export interface AggregatedGraphCapping {
  capped: boolean
  max_nodes: number
  original_count: number
  returned_count: number
  clustered_into_other: number
}

export interface MissingRoleInfo {
  role: string
  omitted_reason: string
}

export interface AggregatedGraphResponse {
  nodes: AggregatedGraphNode[]
  edges: AggregatedGraphEdge[]
  time_buckets: string[]
  capping: AggregatedGraphCapping
  missing_roles: MissingRoleInfo[]
  candidate_sources: CandidateSource[]
}

export interface AggregatedTraceResponse {
  direction: 'downstream' | 'upstream'
  start_node_id: string
  reached_nodes: AggregatedGraphNode[]
  path_edges: AggregatedGraphEdge[]
  node_count: number
  disclaimer: string
}

