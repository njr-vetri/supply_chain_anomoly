import type {
  Action, ActionCreateRequest, AlertHistoryItem, Anomaly, Approval, ApprovalCreateRequest,
  AuditEvent, CapabilityResult, DatasetSource, DecisionRequest, DriftResult, EvalOutcomeResult,
  GraphResponse, Health, Hypothesis, HypothesisCreateRequest, HypothesisReviewRequest,
  ImportJob, KillSwitchRequest, MappingSuggestion, MappingVersion, ModelMetrics, Outcome, Page,
  PipelineDryRunResult, Prediction, QualityItem, Recommendation, RelationshipPreview,
  SupplyGraphResponse, WhatIfRequest, AggregatedGraphResponse, AggregatedTraceResponse,
  Role,
} from './types'

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code = 'request_failed') {
    super(message)
    this.name = 'ApiError'
  }
}

const API_ROOT = '/api/v1'

export class ApiClient {
  constructor(
    readonly baseUrl: string,
    private readonly tokenOrKey: string,
    private readonly companyId?: string,
  ) {}

  private get authHeaders(): Record<string, string> {
    const headers: Record<string, string> = {}
    if (this.tokenOrKey) {
      if (this.tokenOrKey.includes('.')) {
        headers['Authorization'] = `Bearer ${this.tokenOrKey}`
      } else {
        headers['X-API-Key'] = this.tokenOrKey
      }
    }
    if (this.companyId) {
      headers['X-Company-Id'] = this.companyId
    }
    return headers
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response
    try {
      response = await fetch(`${this.baseUrl.replace(/\/$/, '')}${API_ROOT}${path}`, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          ...this.authHeaders,
          ...init.headers,
        },
      })
    } catch (error) {
      throw new ApiError(
        error instanceof Error ? error.message : 'Could not reach the local API',
        0,
        'connection_error',
      )
    }
    const body = await response.json().catch(() => null) as { error?: { code?: string; message?: string } } | null
    if (!response.ok)
      throw new ApiError(
        body?.error?.message ?? `Request failed (${response.status})`,
        response.status,
        body?.error?.code,
      )
    return body as T
  }

  /** Multipart upload – does not set Content-Type (browser sets it with boundary). */
  private async requestMultipart<T>(path: string, form: FormData): Promise<T> {
    let response: Response
    try {
      response = await fetch(`${this.baseUrl.replace(/\/$/, '')}${API_ROOT}${path}`, {
        method: 'POST', body: form, headers: this.authHeaders,
      })
    } catch (error) {
      throw new ApiError(
        error instanceof Error ? error.message : 'Upload failed',
        0,
        'connection_error',
      )
    }
    const body = await response.json().catch(() => null) as { error?: { code?: string; message?: string } } | null
    if (!response.ok)
      throw new ApiError(body?.error?.message ?? `Upload failed (${response.status})`, response.status, body?.error?.code)
    return body as T
  }

  // ── Health ──────────────────────────────────────────────────────────────────
  health() { return this.request<Health>('/health') }

  // ── Quality / drift ─────────────────────────────────────────────────────────
  quality() { return this.request<Page<QualityItem>>('/quality') }
  datasetDrift(datasetName: string) {
    return this.request<DriftResult>(`/datasets/${encodeURIComponent(datasetName)}/drift`)
  }

  // ── Datasets / uploads ──────────────────────────────────────────────────────
  datasets() { return this.request<Page<DatasetSource>>('/datasets') }
  uploadDataset(form: FormData) { return this.requestMultipart<ImportJob>('/datasets/upload', form) }
  importHistory() { return this.request<Page<ImportJob>>('/imports') }
  importJob(jobId: string) { return this.request<ImportJob>(`/imports/${encodeURIComponent(jobId)}`) }
  previewImport(jobId: string, mode: 'append' | 'replace') {
    return this.request<Record<string, unknown>>(`/imports/${encodeURIComponent(jobId)}/preview`, {
      method: 'POST', body: JSON.stringify({ mode }),
    })
  }
  commitImport(jobId: string) {
    return this.request<Record<string, unknown>>(`/imports/${encodeURIComponent(jobId)}/commit`, { method: 'POST', body: JSON.stringify({}) })
  }

  // ── Mapping ─────────────────────────────────────────────────────────────────
  datasetSuggestions(datasetName: string) {
    return this.request<{ suggestions: MappingSuggestion[]; capabilities?: CapabilityResult[] }>(
      `/datasets/${encodeURIComponent(datasetName)}/suggestions`,
    )
  }
  mappingVersions(datasetName: string) {
    return this.request<Page<MappingVersion>>(`/datasets/${encodeURIComponent(datasetName)}/mappings`)
  }
  createMapping(datasetName: string, body: Record<string, unknown>) {
    return this.request<MappingVersion>(`/datasets/${encodeURIComponent(datasetName)}/mappings`, {
      method: 'POST', body: JSON.stringify(body),
    })
  }
  acceptMapping(datasetName: string, version: string, reason: string) {
    return this.request<MappingVersion>(
      `/datasets/${encodeURIComponent(datasetName)}/mappings/${encodeURIComponent(version)}/accept`,
      { method: 'POST', body: JSON.stringify({ reason }) },
    )
  }
  rejectMapping(datasetName: string, version: string, reason: string) {
    return this.request<MappingVersion>(
      `/datasets/${encodeURIComponent(datasetName)}/mappings/${encodeURIComponent(version)}/reject`,
      { method: 'POST', body: JSON.stringify({ reason }) },
    )
  }

  // ── Relationships ───────────────────────────────────────────────────────────
  relationshipPreview(body: Record<string, unknown>) {
    return this.request<RelationshipPreview>('/datasets/relationships/preview', {
      method: 'POST', body: JSON.stringify(body),
    })
  }
  approveRelationship(proposalId: string, reason: string) {
    return this.request<Record<string, unknown>>(
      `/datasets/relationships/${encodeURIComponent(proposalId)}/approve`,
      { method: 'POST', body: JSON.stringify({ reason }) },
    )
  }

  // ── Incidents ───────────────────────────────────────────────────────────────
  incidents() { return this.request<Page<{ id: string; title: string; description: string; source: string; record_refs: string[]; occurred_at: string; evidence_refs: string[]; hypothesis_refs: string[] }>>('/incidents') }
  incident(id: string) { return this.request<import('./types').IncidentDetail>(`/incidents/${encodeURIComponent(id)}`) }

  // ── Predictions / anomalies ─────────────────────────────────────────────────
  predictions() { return this.request<Page<Prediction>>('/predictions') }
  anomalies() { return this.request<Page<Anomaly>>('/anomalies') }

  // ── Evaluation ──────────────────────────────────────────────────────────────
  evaluationOutcomes() { return this.request<EvalOutcomeResult>('/evaluation/outcomes') }
  evaluationAlerts() { return this.request<EvalOutcomeResult>('/evaluation/alerts') }

  // ── Hypotheses ──────────────────────────────────────────────────────────────
  hypotheses() { return this.request<Page<Hypothesis>>('/hypotheses') }
  createHypothesis(body: HypothesisCreateRequest) {
    return this.request<Hypothesis>('/hypotheses', { method: 'POST', body: JSON.stringify(body) })
  }
  reviewHypothesis(id: string, body: HypothesisReviewRequest) {
    return this.request<Hypothesis>(`/hypotheses/${encodeURIComponent(id)}/review`, {
      method: 'POST', body: JSON.stringify(body),
    })
  }
  confirmHypothesis(id: string, rationale: string) {
    return this.request<Hypothesis>(`/hypotheses/${encodeURIComponent(id)}/confirm`, {
      method: 'POST', body: JSON.stringify({ rationale }),
    })
  }

  // ── Recommendations ─────────────────────────────────────────────────────────
  recommendations() { return this.request<Page<Recommendation>>('/recommendations') }
  whatIf(body: WhatIfRequest) {
    return this.request<Record<string, unknown>>('/recommendations/what-if', {
      method: 'POST', body: JSON.stringify(body),
    })
  }

  // ── Approvals ───────────────────────────────────────────────────────────────
  approvals() { return this.request<Page<Approval>>('/approvals') }
  createApproval(body: ApprovalCreateRequest) {
    return this.request<Approval>('/approvals', { method: 'POST', body: JSON.stringify(body) })
  }
  approve(id: string, body: DecisionRequest) {
    return this.request<Approval>(`/approvals/${encodeURIComponent(id)}/approve`, {
      method: 'POST', body: JSON.stringify(body),
    })
  }
  reject(id: string, body: DecisionRequest) {
    return this.request<Approval>(`/approvals/${encodeURIComponent(id)}/reject`, {
      method: 'POST', body: JSON.stringify(body),
    })
  }

  // ── Actions ─────────────────────────────────────────────────────────────────
  actions() { return this.request<Page<Action>>('/actions') }
  actionHistory() { return this.request<Page<Action>>('/actions/history') }
  createAction(body: ActionCreateRequest) {
    return this.request<Action>('/actions', { method: 'POST', body: JSON.stringify(body) })
  }

  // ── Alerts ──────────────────────────────────────────────────────────────────
  alerts() { return this.request<Page<AlertHistoryItem>>('/alerts') }
  alertHistory(limit = 100) {
    return this.request<Page<AlertHistoryItem>>(`/alerts/history?limit=${limit}`)
  }
  acknowledgeAlert(groupId: string, reason: string) {
    return this.request<Record<string, unknown>>(`/alerts/${encodeURIComponent(groupId)}/acknowledge`, {
      method: 'POST', body: JSON.stringify({ reason }),
    })
  }
  assignAlert(groupId: string, assignedTo: string) {
    return this.request<Record<string, unknown>>(`/alerts/${encodeURIComponent(groupId)}/assign`, {
      method: 'POST', body: JSON.stringify({ assigned_to: assignedTo }),
    })
  }

  // ── Incident graph (incident-level, @xyflow) ─────────────────────────────────
  graph(id: string) { return this.request<GraphResponse>(`/incidents/${encodeURIComponent(id)}/graph`) }

  // ── Supply-chain graph (project-level, cytoscape) ────────────────────────────
  supplyGraph(projectId: string, params?: Record<string, string>) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return this.request<SupplyGraphResponse>(
      `/projects/${encodeURIComponent(projectId)}/graph${qs}`,
    )
  }
  supplyGraphNeighborhood(projectId: string, nodeId: string, hops = 1) {
    return this.request<SupplyGraphResponse>(
      `/projects/${encodeURIComponent(projectId)}/graph/neighborhood?node_id=${encodeURIComponent(nodeId)}&hops=${hops}&limit=500`,
    )
  }
  supplyGraphTrace(projectId: string, nodeId: string, direction: 'upstream' | 'downstream') {
    return this.request<SupplyGraphResponse>(
      `/projects/${encodeURIComponent(projectId)}/graph/trace/${direction}?node_id=${encodeURIComponent(nodeId)}&limit=500`,
    )
  }

  // ── Aggregated Supply Network (Functionality 5 Redesign) ───────────────────
  aggregatedSupplyGraph(
    projectId: string,
    params?: { incident_id?: string; max_nodes?: number; min_flow_weight?: number },
  ) {
    const query = new URLSearchParams()
    if (params?.incident_id) query.set('incident_id', params.incident_id)
    if (params?.max_nodes != null) query.set('max_nodes', String(params.max_nodes))
    if (params?.min_flow_weight != null) query.set('min_flow_weight', String(params.min_flow_weight))
    const qs = query.toString() ? '?' + query.toString() : ''
    return this.request<AggregatedGraphResponse>(
      `/projects/${encodeURIComponent(projectId)}/graph/aggregated${qs}`,
    )
  }

  aggregatedSupplyGraphTrace(
    projectId: string,
    nodeId: string,
    direction: 'upstream' | 'downstream',
    maxDepth = 6,
  ) {
    const query = new URLSearchParams({
      node_id: nodeId,
      direction,
      max_depth: String(maxDepth),
    })
    return this.request<AggregatedTraceResponse>(
      `/projects/${encodeURIComponent(projectId)}/graph/aggregated/trace?${query.toString()}`,
    )
  }

  incidentAggregatedSupplyGraph(
    incidentId: string,
    params?: { max_nodes?: number; min_flow_weight?: number },
  ) {
    const query = new URLSearchParams()
    if (params?.max_nodes != null) query.set('max_nodes', String(params.max_nodes))
    if (params?.min_flow_weight != null) query.set('min_flow_weight', String(params.min_flow_weight))
    const qs = query.toString() ? '?' + query.toString() : ''
    return this.request<AggregatedGraphResponse>(
      `/incidents/${encodeURIComponent(incidentId)}/graph/aggregated${qs}`,
    )
  }

  // ── Models ──────────────────────────────────────────────────────────────────
  models() { return this.request<Page<Record<string, unknown>>>('/models') }
  modelMetrics(id: string) { return this.request<ModelMetrics>(`/models/${encodeURIComponent(id)}/metrics`) }
  modelEvalReport(id: string) { return this.request<Record<string, unknown>>(`/models/${encodeURIComponent(id)}/evaluation-report`) }
  modelRegistryComparison(candidateVersion: string) {
    return this.request<Record<string, unknown>>(`/models/registry/comparisons/${encodeURIComponent(candidateVersion)}`)
  }
  promoteModel(candidateVersion: string, reason: string) {
    return this.request<Record<string, unknown>>(`/models/registry/${encodeURIComponent(candidateVersion)}/promote`, {
      method: 'POST', body: JSON.stringify({ reason }),
    })
  }
  rollbackModel(modelKey: string, reason: string) {
    return this.request<Record<string, unknown>>('/models/registry/rollback', {
      method: 'POST', body: JSON.stringify({ model_key: modelKey, reason }),
    })
  }

  // ── Outcomes ─────────────────────────────────────────────────────────────────
  outcomes() { return this.request<Page<Outcome>>('/outcomes') }

  // ── Audit ────────────────────────────────────────────────────────────────────
  audit(params?: { category?: string; event_type?: string }) {
    const qs = params ? '?' + new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null) as [string, string][])).toString() : ''
    return this.request<Page<AuditEvent>>(`/audit${qs}`)
  }

  // ── Kill switch ──────────────────────────────────────────────────────────────
  killSwitch() { return this.request<{ enabled: boolean }>('/admin/kill-switch') }
  toggleKillSwitch(body: KillSwitchRequest) {
    return this.request<{ enabled: boolean; reason: string }>('/admin/kill-switch', {
      method: 'PUT', body: JSON.stringify(body),
    })
  }

  // ── Pipeline ─────────────────────────────────────────────────────────────────
  runPipelineDryRun(datasets: Array<'olist' | 'dataco' | 'online_retail_ii'>) {
    return this.request<PipelineDryRunResult>('/pipeline/run', {
      method: 'POST', body: JSON.stringify({ datasets }),
    })
  }

  // ── Auth & Accounts ─────────────────────────────────────────────────────────
  setupStatus() { return this.request<{ setup_required: boolean }>('/auth/setup-status') }
  setup(body: { company_id: string; company_name: string; admin_username: string; admin_email: string; admin_password: string }) {
    return this.request<{ token: string; user: { id: string; username: string; email: string; role: Role; company_id: string; must_change_password: boolean }; message: string }>('/auth/setup', { method: 'POST', body: JSON.stringify(body) })
  }
  login(body: { username_or_email: string; password: string; company_id?: string }) {
    return this.request<{ token: string; user: { id: string; username: string; email: string; role: Role; company_id: string; must_change_password: boolean } }>('/auth/login', { method: 'POST', body: JSON.stringify(body) })
  }
  logout() { return this.request<{ message: string }>('/auth/logout', { method: 'POST', body: JSON.stringify({}) }) }
  changePassword(oldPassword: string, newPassword: string) {
    return this.request<{ message: string }>('/auth/change-password', {
      method: 'POST', body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    })
  }
  permissions() {
    return this.request<{ roles: string[]; role_levels: Record<string, number>; permissions: Record<string, string[]> }>('/auth/permissions')
  }
  listUsers() { return this.request<{ items: Array<{ id: string; username: string; email: string; role: Role; is_active: boolean; must_change_password: boolean; locked_until: string | null; created_at: string | null }>; count: number }>('/auth/users') }
  createUser(body: { username: string; email: string; role: string; temp_password?: string }) {
    return this.request<{ user: { id: string; username: string; email: string; role: Role; company_id: string; must_change_password: boolean }; temporary_password?: string; message: string }>('/auth/users', { method: 'POST', body: JSON.stringify(body) })
  }
  adminResetPassword(userId: string) {
    return this.request<{ temporary_password: string; message: string }>(`/auth/users/${encodeURIComponent(userId)}/reset-password`, { method: 'POST', body: JSON.stringify({}) })
  }
  deleteUser(userId: string) {
    return this.request<{ message: string; id: string }>(`/auth/users/${encodeURIComponent(userId)}`, { method: 'DELETE' })
  }
  listApiKeys() { return this.request<{ items: Array<{ id: string; name: string; prefix: string; role: 'viewer' | 'analyst'; scopes: string[]; created_at: string | null; last_used_at: string | null }>; count: number }>('/auth/api-keys') }
  createApiKey(body: { name: string; role: 'viewer' | 'analyst'; scopes?: string[] }) {
    return this.request<{ id: string; name: string; prefix: string; role: string; api_key: string; message: string }>('/auth/api-keys', {
      method: 'POST', body: JSON.stringify(body),
    })
  }
  revokeApiKey(keyId: string) {
    return this.request<{ message: string; id: string }>(`/auth/api-keys/${encodeURIComponent(keyId)}`, { method: 'DELETE' })
  }

  // ── Workspaces & Projects ────────────────────────────────────────────────────
  listWorkspaces() { return this.request<{ items: Array<{ id: string; name: string }>; count: number }>('/workspaces') }
  createWorkspace(name: string) {
    return this.request<{ id: string; name: string }>('/workspaces', { method: 'POST', body: JSON.stringify({ name }) })
  }
  listProjects(workspaceId?: string) {
    const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ''
    return this.request<{ items: Array<{ id: string; workspace_id: string; name: string }>; count: number }>(`/projects${qs}`)
  }
  createProject(name: string, workspaceId?: string) {
    return this.request<{ id: string; workspace_id: string; name: string }>('/projects', {
      method: 'POST', body: JSON.stringify({ name, workspace_id: workspaceId }),
    })
  }
  getProject(projectId: string) {
    return this.request<{ id: string; workspace_id: string; name: string }>(`/projects/${encodeURIComponent(projectId)}`)
  }
  listProjectDatasets(projectId: string) {
    return this.request<{ items: Array<{ id: string; name: string; source_type: string }>; count: number }>(`/projects/${encodeURIComponent(projectId)}/datasets`)
  }
  currentUser() {
    return this.request<{ id: string; username: string; email: string; role: string; company_id: string; must_change_password: boolean; last_project_id: string | null }>('/users/me')
  }
  updateUserPreferences(lastProjectId: string) {
    return this.request<{ last_project_id: string }>('/users/me/preferences', {
      method: 'PUT', body: JSON.stringify({ last_project_id: lastProjectId }),
    })
  }

  // ── Admin Settings & Scheduler ───────────────────────────────────────────────
  adminSettings() { return this.request<{ require_reviewer_mapping_approval: boolean }>('/admin/settings') }
  updateAdminSettings(body: { require_reviewer_mapping_approval: boolean }) {
    return this.request<{ require_reviewer_mapping_approval: boolean }>('/admin/settings', {
      method: 'PUT', body: JSON.stringify(body),
    })
  }
  schedulerStatus() {
    return this.request<{ enabled: boolean; running: boolean; interval_seconds: number; last_run: string | null }>('/admin/scheduler')
  }
  toggleScheduler(enabled: boolean) {
    return this.request<{ enabled: boolean; running: boolean; interval_seconds: number; last_run: string | null }>('/admin/scheduler', {
      method: 'PUT', body: JSON.stringify({ enabled }),
    })
  }

  // ── Datasets Deletion ────────────────────────────────────────────────────────
  deleteDataset(datasetName: string) {
    return this.request<{ deleted: boolean; dataset_name: string }>(`/datasets/${encodeURIComponent(datasetName)}`, {
      method: 'DELETE',
    })
  }
}

export const defaultApiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
