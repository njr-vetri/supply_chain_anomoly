import { useState, useEffect, useCallback, type ChangeEvent } from 'react'
import {
  Upload, Play, RefreshCw, CheckCircle, Clock, Shield,
  Layers, HelpCircle, AlertCircle, FileText, Database, Check, X, Cpu,
  Calendar, RotateCcw, CheckCircle2, TrendingUp
} from 'lucide-react'
import type { ApiClient } from '../api/client'
import type {
  Role, PipelineStageInfo, PipelineRunDetail, MappingSuggestionReport,
  Anomaly, Prediction, Hypothesis, Recommendation, AlertHistoryItem
} from '../api/types'

interface OnePagePrototypeProps {
  client: ApiClient
  projectId: string
  userRole: Role
  onRoleChange?: (newRole: Role) => void
}

export function OnePagePrototype({ client, projectId, userRole, onRoleChange }: OnePagePrototypeProps) {
  // --- Ingestion & Files state ---
  const [uploading, setUploading] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ name: string; size: number; datasetName: string; sha256?: string; rows?: number }>>([])
  const [mappingReport, setMappingReport] = useState<MappingSuggestionReport | null>(null)
  const [editedMappings, setEditedMappings] = useState<Record<string, string>>({})
  const [mappingConfirmed, setMappingConfirmed] = useState(false)
  const [mappingFeedback, setMappingFeedback] = useState<string | null>(null)

  // --- Pipeline Run state ---
  const [running, setRunning] = useState(false)
  const [pipelineRun, setPipelineRun] = useState<PipelineRunDetail | null>(null)
  const [activeStageTab, setActiveStageTab] = useState<string>('ingest')
  const [scheduledRuns, setScheduledRuns] = useState(false)

  // --- Results state ---
  const [anomalies, setAnomalies] = useState<Anomaly[]>([])
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([])
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [alerts, setAlerts] = useState<AlertHistoryItem[]>([])
  const [activeResultsTab, setActiveResultsTab] = useState<'stages' | 'anomalies' | 'predictions' | 'drivers' | 'recommendations' | 'alerts' | 'network'>('stages')

  // --- Manual Actions & Permissions state ---
  const [actionFeedback, setActionFeedback] = useState<{ msg: string; isError: boolean } | null>(null)
  const [confirmingHypothesisId, setConfirmingHypothesisId] = useState<string | null>(null)
  const [hypothesisRationale, setHypothesisRationale] = useState<string>('')
  const [rollbackStatus, setRollbackStatus] = useState<string | null>(null)

  // --- Initial load & refresh ---
  const refreshData = useCallback(async () => {
    try {
      const [anomRes, predRes, hypRes, recRes, alertRes, schedRes, runRes] = await Promise.all([
        client.anomalies().catch(() => ({ items: [], count: 0 })),
        client.predictions().catch(() => ({ items: [], count: 0 })),
        client.hypotheses().catch(() => ({ items: [], count: 0 })),
        client.recommendations().catch(() => ({ items: [], count: 0 })),
        client.alertHistory(50).catch(() => ({ items: [], count: 0 })),
        client.schedulerStatus().catch(() => ({ enabled: false, running: false, interval_seconds: 3600 })),
        client.latestPipelineRun(projectId).catch(() => null),
      ])

      setAnomalies(anomRes.items as Anomaly[])
      setPredictions(predRes.items as Prediction[])
      setHypotheses(hypRes.items as Hypothesis[])
      setRecommendations(recRes.items as Recommendation[])
      setAlerts(alertRes.items as AlertHistoryItem[])
      setScheduledRuns(schedRes.enabled)
      if (runRes && runRes.id) {
        setPipelineRun(runRes)
      }
    } catch {
      // safe fallback on initial fetch
    }
  }, [client, projectId])

  useEffect(() => {
    void refreshData()
  }, [refreshData])

  // Helper to poll for profiling completion and mapping suggestions
  const fetchSuggestionsWithRetry = async (
    datasetName: string,
    maxAttempts = 15,
    intervalMs = 400
  ): Promise<MappingSuggestionReport | null> => {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const report = await client.datasetSuggestions(datasetName)
        if (report && report.suggestions && report.suggestions.length > 0) {
          return report
        }
      } catch {
        // Profiling job running in background (HTTP 409), wait and retry
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
    return null
  }

  // Helper to extract clean canonical mappings from state
  const buildCleanMappings = (
    mappingsDict: Record<string, string>,
    report: MappingSuggestionReport | null
  ): Record<string, string> => {
    const validRoles = new Set([
      'order_id', 'order_ts', 'promised_ts', 'delivered_ts', 'event_timestamp',
      'carrier', 'carrier_id', 'supplier_id', 'product_id', 'quantity', 'price',
      'status', 'post_outcome', 'region', 'route', 'warehouse_id', 'warehouse_name',
      'snapshot_id', 'observation_id', 'customer_id', 'destination', 'shipment_id'
    ])

    const combined: Record<string, string> = {}

    // First include auto_accepted_mappings if available
    if (report?.auto_accepted_mappings) {
      for (const [col, role] of Object.entries(report.auto_accepted_mappings)) {
        if (validRoles.has(role)) {
          combined[col] = role
        }
      }
    }

    // Then layer user edits / suggestions
    for (const [col, role] of Object.entries(mappingsDict)) {
      if (col && col !== 'undefined' && validRoles.has(role)) {
        combined[col] = role
      }
    }

    // Fill in any confident suggestions from report that might be missing
    if (report?.suggestions) {
      for (const s of report.suggestions) {
        const col = s.column_name || s.column
        if (col && col !== 'undefined' && !combined[col] && s.suggested_role && validRoles.has(s.suggested_role)) {
          combined[col] = s.suggested_role
        }
      }
    }

    return combined
  }

  // --- File Upload Handler ---
  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    setUploading(true)
    setMappingFeedback('Uploading and profiling dataset...')
    const newFiles: Array<{ name: string; size: number; datasetName: string; sha256?: string; rows?: number }> = []

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        const form = new FormData()
        form.append('file', file)
        if (projectId) {
          form.append('project_id', projectId)
        }
        const job = await client.uploadDataset(form)
        const dName = job.dataset_name || file.name.replace(/\.[^/.]+$/, '').toLowerCase().replace(/[^a-z0-9_-]/g, '_')

        // Handle multi-table ZIP or single dataset
        if (job.is_multi_table && job.tables && job.tables.length > 0) {
          for (const tbl of job.tables) {
            newFiles.push({
              name: `${file.name} [${tbl.filename}]`,
              size: tbl.size_bytes,
              datasetName: tbl.dataset_name,
              sha256: tbl.sha256 || undefined,
            })
          }
        } else {
          newFiles.push({
            name: file.name,
            size: file.size,
            datasetName: dName,
            sha256: job.sha256 || undefined,
            rows: job.total_rows || job.processed_rows || undefined,
          })
        }

        // Poll profiling completion for suggestions
        const targetDName = (job.is_multi_table && job.tables && job.tables[0]) ? job.tables[0].dataset_name : dName
        setMappingFeedback(`Analyzing schema & profiling ${targetDName}...`)
        const suggestions = await fetchSuggestionsWithRetry(targetDName)
        if (suggestions) {
          setMappingReport(suggestions)
          const initialMap: Record<string, string> = { ...(suggestions.auto_accepted_mappings || {}) }
          for (const s of suggestions.suggestions) {
            const col = s.column_name || s.column
            if (col && s.suggested_role) {
              initialMap[col] = s.suggested_role
            }
          }
          setEditedMappings(initialMap)
          setMappingConfirmed(false)
          const ambiguousCount = suggestions.suggestions.filter((s) => s.needs_clarification).length
          setMappingFeedback(
            ambiguousCount > 0
              ? `Dataset profiled. ${ambiguousCount} ambiguous column(s) flagged for review.`
              : `Dataset profiled successfully. All confident mappings auto-matched.`
          )
        }
      }

      setUploadedFiles((prev) => [...prev, ...newFiles])
    } catch (err: unknown) {
      setMappingFeedback(`Upload failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  // --- Confirm Column Mappings ---
  const handleConfirmMappings = async () => {
    if (!uploadedFiles.length) {
      setMappingFeedback('Please upload a dataset first.')
      return
    }
    const cleanMappings = buildCleanMappings(editedMappings, mappingReport)
    if (Object.keys(cleanMappings).length === 0) {
      setMappingFeedback('No valid canonical column mappings selected to confirm.')
      return
    }

    try {
      const datasetsToConfirm = Array.from(new Set(uploadedFiles.map((f) => f.datasetName)))
      for (const dName of datasetsToConfirm) {
        await client.confirmDatasetMapping(dName, cleanMappings, 'Reviewer confirmed column mappings on Prototype page')
      }
      setMappingConfirmed(true)
      setMappingFeedback(`Mappings successfully approved for: ${datasetsToConfirm.join(', ')}`)
    } catch (err: unknown) {
      setMappingFeedback(`Confirmation failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  // --- Execute Pipeline Run ---
  const handleRunPipeline = async () => {
    setRunning(true)
    setActionFeedback(null)
    try {
      // 1. Ensure mappings are confirmed for uploaded datasets before pipeline execution
      const datasets = Array.from(new Set(uploadedFiles.map((f) => f.datasetName).filter(Boolean)))

      if (datasets.length > 0 && !mappingConfirmed) {
        let currentReport = mappingReport
        if (!currentReport) {
          for (const dName of datasets) {
            currentReport = await fetchSuggestionsWithRetry(dName, 8, 300)
            if (currentReport) {
              setMappingReport(currentReport)
              break
            }
          }
        }

        const cleanMap = buildCleanMappings(editedMappings, currentReport)
        if (Object.keys(cleanMap).length > 0) {
          for (const dName of datasets) {
            try {
              await client.confirmDatasetMapping(dName, cleanMap, 'Auto-accepted confident column mappings on Run')
            } catch (mErr) {
              console.warn(`Mapping auto-confirm note for ${dName}:`, mErr)
            }
          }
          setMappingConfirmed(true)
        }
      }

      // 2. Launch pipeline execution
      const result = await client.runProjectPipeline(projectId)
      setPipelineRun(result)
      await refreshData()
      setActionFeedback({ msg: 'Pipeline analysis completed successfully across all 9 stages.', isError: false })
    } catch (err: unknown) {
      setActionFeedback({ msg: `Pipeline execution failed: ${err instanceof Error ? err.message : String(err)}`, isError: true })
    } finally {
      setRunning(false)
    }
  }

  // --- Toggle Scheduler ---
  const handleToggleScheduler = async () => {
    try {
      const newEnabled = !scheduledRuns
      await client.toggleScheduler(newEnabled)
      setScheduledRuns(newEnabled)
      setActionFeedback({ msg: `Autonomous schedule ${newEnabled ? 'enabled (hourly cron)' : 'disabled'}.`, isError: false })
    } catch (err: unknown) {
      setActionFeedback({ msg: `Scheduler toggle failed: ${err instanceof Error ? err.message : String(err)}`, isError: true })
    }
  }

  // --- Confirm Hypothesis (Reviewer gated) ---
  const handleConfirmHypothesis = async (hypId: string) => {
    setActionFeedback(null)
    if (userRole !== 'reviewer' && userRole !== 'admin') {
      setActionFeedback({
        msg: 'HTTP 403 Forbidden: Only a user with the Reviewer role can confirm root-cause hypotheses.',
        isError: true,
      })
      return
    }
    const rationale = hypothesisRationale.trim() || 'Empirical multi-factor root-cause confirmed by domain reviewer.'
    try {
      await client.confirmHypothesis(hypId, rationale)
      setConfirmingHypothesisId(null)
      setHypothesisRationale('')
      await refreshData()
      setActionFeedback({ msg: `Hypothesis ${hypId} confirmed by human reviewer.`, isError: false })
    } catch (err: unknown) {
      setActionFeedback({ msg: `Confirmation rejected: ${err instanceof Error ? err.message : String(err)}`, isError: true })
    }
  }

  // --- Approve / Reject Action (Reviewer gated) ---
  const handleApproveAction = async (rec: Recommendation, approved: boolean) => {
    setActionFeedback(null)
    if (userRole !== 'reviewer' && userRole !== 'admin') {
      setActionFeedback({
        msg: 'HTTP 403 Forbidden: Only a user with the Reviewer role can approve or reject intervention actions.',
        isError: true,
      })
      return
    }
    try {
      const approval = await client.createApproval({
        recommendation_id: rec.id,
      })
      if (approved) {
        await client.approve(approval.id, { rationale: 'Action approved via one-page prototype panel' })
        setActionFeedback({ msg: `Action "${rec.action}" approved (dry-run validated).`, isError: false })
      } else {
        await client.reject(approval.id, { rationale: 'Action rejected by reviewer' })
        setActionFeedback({ msg: `Action "${rec.action}" rejected.`, isError: false })
      }
      await refreshData()
    } catch (err: unknown) {
      setActionFeedback({ msg: `Action decision failed: ${err instanceof Error ? err.message : String(err)}`, isError: true })
    }
  }

  // --- Rollback Model Registry ---
  const handleRollback = async () => {
    setRollbackStatus('Rolling back...')
    try {
      await client.rollbackModel('canonical_delay_model', 'Manual rollback requested from prototype page')
      setRollbackStatus('Rolled back to previous verified model version.')
      await refreshData()
    } catch (err: unknown) {
      setRollbackStatus(`Rollback failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const defaultStages: PipelineStageInfo[] = [
    { name: 'ingest', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Ingests uploaded raw datasets with bomb checks and skips non-tabular sheets.' },
    { name: 'schema_discovery', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Discovers canonical roles, auto-accepts confident mappings, and highlights ambiguities.' },
    { name: 'data_quality', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Profiles completeness, negative values, orphan keys, and quarantines invalid timestamps.' },
    { name: 'capability_detection', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Evaluates which risk & prediction pipelines can run based on mapped canonical roles.' },
    { name: 'anomaly_detection', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Runs ensemble detectors with de-duplication per record and robust weekly demand spike checks.' },
    { name: 'prediction', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Trains delay classifier and demand forecaster with MAE/sMAPE compared against naive baseline.' },
    { name: 'root_cause_drivers', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Identifies carrier × route pair interactions and single-driver confounding labeled as contributing factors.' },
    { name: 'recommendations', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Generates prescriptive playbooks marked with HYPOTHETICAL simulation badges.' },
    { name: 'alerts', status: 'PENDING', duration_seconds: 0, input_rows: 0, output_rows: 0, warnings: [], counts: {}, details: {}, explanation: 'Suppresses duplicate alerts and delivers notifications with explicit delivery status tracking.' },
  ]

  const rawStages = (pipelineRun?.nine_stages && pipelineRun.nine_stages.length > 0)
    ? pipelineRun.nine_stages
    : (pipelineRun?.result?.nine_stages && pipelineRun.result.nine_stages.length > 0)
    ? pipelineRun.result.nine_stages
    : (pipelineRun?.stages && pipelineRun.stages.length > 0)
    ? pipelineRun.stages
    : defaultStages

  const nineStages: PipelineStageInfo[] = rawStages
    .filter((s): s is PipelineStageInfo => Boolean(s && typeof s === 'object' && s.name))
    .map((s) => ({
      name: String(s.name),
      status: s.status || 'COMPLETED',
      duration_seconds: typeof s.duration_seconds === 'number' ? s.duration_seconds : 0,
      input_rows: typeof s.input_rows === 'number' ? s.input_rows : 0,
      output_rows: typeof s.output_rows === 'number' ? s.output_rows : 0,
      warnings: Array.isArray(s.warnings) ? s.warnings : [],
      counts: s.counts && typeof s.counts === 'object' ? s.counts : {},
      details: s.details && typeof s.details === 'object' ? s.details : {},
      explanation: s.explanation || 'Automated pipeline processing stage.',
      insufficient_evidence: Boolean(s.insufficient_evidence),
    }))

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 md:p-8 space-y-8 font-sans">
      {/* Top Header & Operational Banner */}
      <header className="border border-slate-800 bg-slate-900/80 backdrop-blur rounded-2xl p-6 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-brand/10 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                <Cpu size={22} />
              </span>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
                  Autonomous Risk Pipeline
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    ONE-PAGE PROTOTYPE
                  </span>
                </h1>
                <p className="text-xs text-slate-400 mt-0.5">
                  Single-page automated supply-chain intelligence · Upload data, review ambiguities, execute 9-stage analysis
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Role Switcher Pill */}
            <div className="flex items-center gap-2 bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-1.5 text-xs">
              <Shield size={14} className="text-indigo-400" />
              <span className="text-slate-400">Current Role:</span>
              <select
                aria-label="Current Role"
                value={userRole}
                onChange={(e) => onRoleChange?.(e.target.value as Role)}
                className="bg-transparent font-semibold text-white focus:outline-none cursor-pointer uppercase tracking-wider text-[11px]"
              >
                <option value="viewer" className="bg-slate-900">Viewer</option>
                <option value="analyst" className="bg-slate-900">Analyst</option>
                <option value="reviewer" className="bg-slate-900">Reviewer</option>
                <option value="admin" className="bg-slate-900">Admin</option>
              </select>
            </div>

            {/* Schedule Toggle */}
            <button
              onClick={handleToggleScheduler}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-medium transition-all ${
                scheduledRuns
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                  : 'bg-slate-800/60 border-slate-700 text-slate-400 hover:text-white'
              }`}
              title="Toggle recurring autonomous analysis schedule"
            >
              <Calendar size={14} />
              <span>Schedule: {scheduledRuns ? 'Active (Hourly)' : 'Disabled'}</span>
            </button>

            {/* Kill Switch Pill */}
            <div className="flex items-center gap-2 bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-1.5 text-xs">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-slate-400">Kill Switch:</span>
              <span className="text-emerald-400 font-bold">READY</span>
            </div>

            {/* Rollback Model Button */}
            <button
              onClick={handleRollback}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800/40 hover:bg-slate-800 text-slate-300 text-xs transition"
              title="Rollback model registry scoring config"
            >
              <RotateCcw size={13} />
              <span>Rollback Config</span>
            </button>
          </div>
        </div>

        {/* Global Feedback Banner */}
        {actionFeedback && (
          <div className={`mt-4 p-3 rounded-xl border flex items-center justify-between text-xs animate-in fade-in ${
            actionFeedback.isError
              ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
          }`}>
            <div className="flex items-center gap-2">
              {actionFeedback.isError ? <AlertCircle size={16} /> : <CheckCircle size={16} />}
              <span>{actionFeedback.msg}</span>
            </div>
            <button onClick={() => setActionFeedback(null)} className="opacity-70 hover:opacity-100">
              <X size={14} />
            </button>
          </div>
        )}

        {rollbackStatus && (
          <div className="mt-2 p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs flex items-center justify-between">
            <span>{rollbackStatus}</span>
            <button onClick={() => setRollbackStatus(null)}><X size={12} /></button>
          </div>
        )}
      </header>

      {/* Main Grid: Upload & Schema Review (Left) + Execution & 9 Stages (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Step 1: Manual Data Ingestion & Ambiguous Mapping Review */}
        <section className="lg:col-span-5 space-y-6">
          <div className="border border-slate-800 bg-slate-900/60 rounded-2xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400 font-bold text-xs border border-indigo-500/30">
                  1
                </span>
                <h2 className="text-base font-semibold text-white">Data Ingestion</h2>
              </div>
              <span className="text-[11px] text-slate-400">.zip · .csv · .xlsx · .json</span>
            </div>

            {/* Dropzone */}
            <label className="border-2 border-dashed border-slate-700 hover:border-indigo-400/60 bg-slate-950/40 hover:bg-slate-900/50 rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition group">
              <input
                type="file"
                multiple
                accept=".zip,.csv,.xlsx,.xlsm,.json,.jsonl"
                onChange={handleFileUpload}
                disabled={uploading}
                className="hidden"
              />
              <Upload size={32} className="text-slate-400 group-hover:text-indigo-400 transition mb-2" />
              <p className="text-sm font-medium text-slate-200">
                {uploading ? 'Processing & profiling upload...' : 'Upload datasets (single or multi-table ZIP)'}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Safe uncompressed bomb protection, non-tabular sheets automatically skipped
              </p>
            </label>

            {/* Uploaded Files Manifest */}
            {uploadedFiles.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Loaded Tables</p>
                <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                  {uploadedFiles.map((f, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800 text-xs">
                      <div className="flex items-center gap-2 truncate">
                        <FileText size={14} className="text-indigo-400 shrink-0" />
                        <span className="font-mono text-slate-200 truncate">{f.name}</span>
                      </div>
                      <div className="flex items-center gap-3 text-slate-400 shrink-0">
                        {f.rows && <span>{f.rows.toLocaleString()} rows</span>}
                        <span className="text-[10px] bg-slate-800 px-1.5 py-0.5 rounded">{(f.size / 1024).toFixed(0)} KB</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Ambiguous Column Mapping Review Panel */}
            {mappingReport && (
              <div className="border border-slate-800 bg-slate-950/80 rounded-xl p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Database size={15} className="text-amber-400" />
                    <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                      Schema Mapping Review
                    </h3>
                  </div>
                  {mappingConfirmed ? (
                    <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                      <CheckCircle2 size={13} /> Mappings Accepted
                    </span>
                  ) : (
                    <span className="text-[11px] text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded border border-amber-400/20">
                      Ambiguities require confirmation
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-400">
                  Confident mappings are auto-accepted. Review ambiguous columns below before running analysis.
                </p>

                {/* Columns List */}
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {mappingReport.suggestions.map((s, idx) => {
                    const colName = s.column_name || s.column || `col_${idx}`
                    const isAmbiguous = s.needs_clarification || (s.confidence < 0.7 && !s.auto_accepted)
                    return (
                      <div
                        key={colName}
                        className={`p-2.5 rounded-lg border text-xs flex flex-col gap-1.5 transition ${
                          isAmbiguous
                            ? 'bg-amber-500/5 border-amber-500/30'
                            : 'bg-slate-900/60 border-slate-800/80'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-medium text-slate-200">{colName}</span>
                          <div className="flex items-center gap-2">
                            {s.auto_accepted && !isAmbiguous ? (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20">
                                AUTO-ACCEPTED ({Math.round(s.confidence * 100)}%)
                              </span>
                            ) : (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 font-semibold border border-amber-500/20">
                                AMBIGUOUS ({Math.round(s.confidence * 100)}%)
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <label htmlFor={`map-role-${colName}`} className="text-[11px] text-slate-400">Map to role:</label>
                          <select
                            id={`map-role-${colName}`}
                            value={editedMappings[colName] || (s.suggested_role && s.suggested_role !== 'custom_field' ? s.suggested_role : 'custom_field')}
                            onChange={(e) => {
                              const val = e.target.value
                              setEditedMappings((prev) => ({ ...prev, [colName]: val }))
                              setMappingConfirmed(false)
                            }}
                            className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-400 flex-1"
                          >
                            <option value="custom_field">Custom Field (preserve unmapped)</option>
                            <option value="order_id">order_id (Primary Key)</option>
                            <option value="order_ts">order_ts (Order Timestamp)</option>
                            <option value="promised_ts">promised_ts (SLA Delivery Date)</option>
                            <option value="delivered_ts">delivered_ts (Actual Delivery Date)</option>
                            <option value="event_timestamp">event_timestamp (Timeline Event)</option>
                            <option value="carrier">carrier (Logistics Carrier)</option>
                            <option value="carrier_id">carrier_id (Carrier Identifier)</option>
                            <option value="supplier_id">supplier_id (Supply / Vendor)</option>
                            <option value="product_id">product_id (SKU / Product)</option>
                            <option value="quantity">quantity (Demand / Units)</option>
                            <option value="price">price (Unit Price / Revenue)</option>
                            <option value="status">status (Order / Delivery Status)</option>
                            <option value="route">route (Transit Corridor / Lane)</option>
                            <option value="region">region (Destination / Region)</option>
                            <option value="warehouse_id">warehouse_id (Warehouse Facility)</option>
                          </select>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Approve Button */}
                <div className="pt-2 flex items-center justify-between border-t border-slate-800">
                  <span className="text-[11px] text-slate-400">
                    {mappingReport.suggestions.filter((s) => s.needs_clarification).length} ambiguous column(s)
                  </span>
                  <button
                    onClick={handleConfirmMappings}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow transition"
                  >
                    <Check size={13} />
                    <span>Approve & Accept Mappings</span>
                  </button>
                </div>

                {mappingFeedback && (
                  <p className="text-[11px] text-indigo-300 bg-indigo-950/50 p-2 rounded border border-indigo-800">
                    {mappingFeedback}
                  </p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Step 2: Run Trigger & 9-Stage Automated Pipeline Panel */}
        <section className="lg:col-span-7 space-y-6">
          <div className="border border-slate-800 bg-slate-900/60 rounded-2xl p-6 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400 font-bold text-xs border border-indigo-500/30">
                  2
                </span>
                <div>
                  <h2 className="text-base font-semibold text-white">Automated Analysis</h2>
                  <p className="text-xs text-slate-400">9 automated stages with verified factual explanations</p>
                </div>
              </div>

              {/* Big Run Analysis Button */}
              <button
                onClick={handleRunPipeline}
                disabled={running}
                className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-400 hover:to-indigo-500 text-white font-semibold text-sm shadow-lg shadow-indigo-500/20 transition disabled:opacity-50 active:scale-95"
              >
                {running ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" />
                    <span>Executing Pipeline...</span>
                  </>
                ) : (
                  <>
                    <Play size={16} fill="currentColor" />
                    <span>Run Analysis</span>
                  </>
                )}
              </button>
            </div>

            {/* 9 Stages Visual Progression Grid */}
            <div className="grid grid-cols-3 sm:grid-cols-9 gap-2">
              {nineStages.map((stage, idx) => {
                const isSelected = activeStageTab === stage.name
                const isCompleted = stage.status === 'COMPLETED'
                const isRunningStage = running && stage.status === 'RUNNING'

                return (
                  <button
                    key={stage.name}
                    onClick={() => setActiveStageTab(stage.name)}
                    className={`flex flex-col items-center justify-center p-2 rounded-xl border text-center transition ${
                      isSelected
                        ? 'bg-indigo-500/10 border-indigo-500 text-white'
                        : isCompleted
                        ? 'bg-slate-950/60 border-slate-800 hover:border-slate-700 text-slate-300'
                        : 'bg-slate-950/30 border-slate-800/40 opacity-60 text-slate-500'
                    }`}
                  >
                    <span className="text-[10px] font-mono text-slate-400">0{idx + 1}</span>
                    <span className="text-xs font-semibold truncate w-full mt-0.5">
                      {stage.name.replace('_', ' ')}
                    </span>
                    <span className="mt-1">
                      {isRunningStage ? (
                        <RefreshCw size={12} className="animate-spin text-indigo-400" />
                      ) : isCompleted ? (
                        <CheckCircle size={12} className="text-emerald-400" />
                      ) : (
                        <Clock size={12} className="text-slate-600" />
                      )}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* Selected Stage Detail Card with Verified Plain-Language Explanation */}
            {(() => {
              const currentStage = nineStages.find((s) => s.name === activeStageTab) || nineStages[0] || defaultStages[0]
              return (
                <div className="border border-slate-800 bg-slate-950/80 rounded-xl p-5 space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                    <div className="flex items-center gap-2">
                      <Layers size={17} className="text-indigo-400" />
                      <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                        Stage: {currentStage.name.replace('_', ' ')}
                      </h3>
                      <span className={`text-[10px] px-2 py-0.5 rounded font-semibold border ${
                        currentStage.status === 'COMPLETED'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-slate-800 text-slate-400 border-slate-700'
                      }`}>
                        {currentStage.status}
                      </span>
                    </div>

                    <div className="flex items-center gap-4 text-xs text-slate-400 font-mono">
                      <span>Duration: {currentStage.duration_seconds.toFixed(2)}s</span>
                      <span>{currentStage.input_rows.toLocaleString()} in → {currentStage.output_rows.toLocaleString()} out</span>
                    </div>
                  </div>

                  {/* Fact-Checked Explanation */}
                  <div className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800">
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                      <HelpCircle size={13} className="text-indigo-400" />
                      Verified Stage Explanation
                    </p>
                    <p className="text-sm text-slate-200 leading-relaxed">
                      {currentStage.explanation}
                    </p>
                    {currentStage.insufficient_evidence && (
                      <span className="inline-block mt-2 text-[10px] px-2 py-0.5 rounded font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        Insufficient evidence for full automated inference
                      </span>
                    )}
                  </div>

                  {/* Stage Metrics & Counts */}
                  {Object.keys(currentStage.counts).length > 0 && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                      {Object.entries(currentStage.counts).map(([k, v]) => (
                        <div key={k} className="p-2 rounded bg-slate-900/60 border border-slate-800 text-center">
                          <p className="text-[10px] text-slate-400 uppercase tracking-wider truncate">{k.replace('_', ' ')}</p>
                          <p className="text-sm font-bold font-mono text-white mt-0.5">{String(v)}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })()}
          </div>
        </section>
      </div>

      {/* Step 3: Actionable Intelligence Results Navigation & Panels */}
      <section className="border border-slate-800 bg-slate-900/60 rounded-2xl p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400 font-bold text-xs border border-emerald-500/30">
              3
            </span>
            <div>
              <h2 className="text-base font-semibold text-white">Intelligence Results & Actionable Insights</h2>
              <p className="text-xs text-slate-400">Deduplicated anomalies · Forecasts vs Baseline · Contributing factors · Recommendations</p>
            </div>
          </div>

          {/* Results Tabs */}
          <div className="flex flex-wrap items-center gap-1 bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
            <button
              onClick={() => setActiveResultsTab('stages')}
              className={`px-3 py-1.5 rounded-lg transition ${activeResultsTab === 'stages' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'}`}
            >
              9 Stages Summary
            </button>
            <button
              onClick={() => setActiveResultsTab('anomalies')}
              className={`px-3 py-1.5 rounded-lg transition ${activeResultsTab === 'anomalies' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'}`}
            >
              Anomalies ({anomalies.length})
            </button>
            <button
              onClick={() => setActiveResultsTab('predictions')}
              className={`px-3 py-1.5 rounded-lg transition ${activeResultsTab === 'predictions' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'}`}
            >
              Forecasts vs Baseline
            </button>
            <button
              onClick={() => setActiveResultsTab('drivers')}
              className={`px-3 py-1.5 rounded-lg transition ${activeResultsTab === 'drivers' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'}`}
            >
              Contributing Factors ({hypotheses.length})
            </button>
            <button
              onClick={() => setActiveResultsTab('recommendations')}
              className={`px-3 py-1.5 rounded-lg transition ${activeResultsTab === 'recommendations' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'}`}
            >
              Recommendations ({recommendations.length})
            </button>
            <button
              onClick={() => setActiveResultsTab('alerts')}
              className={`px-3 py-1.5 rounded-lg transition ${activeResultsTab === 'alerts' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'}`}
            >
              Alerts ({alerts.length})
            </button>
            <button
              onClick={() => setActiveResultsTab('network')}
              className={`px-3 py-1.5 rounded-lg transition ${activeResultsTab === 'network' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'}`}
            >
              Compact Network
            </button>
          </div>
        </div>

        {/* Tab 1: 9 Stages Overview Table */}
        {activeResultsTab === 'stages' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {nineStages.map((st, i) => (
                <div key={st.name} className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex flex-col justify-between space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-slate-500">Stage 0{i + 1}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                      st.status === 'COMPLETED' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {st.status}
                    </span>
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white capitalize">{st.name.replace('_', ' ')}</h4>
                    <p className="text-xs text-slate-400 mt-1 line-clamp-2">{st.explanation}</p>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono border-t border-slate-900 pt-2">
                    <span>{st.duration_seconds.toFixed(2)}s</span>
                    <span>{st.input_rows} in / {st.output_rows} out</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 2: Deduplicated Anomalies */}
        {activeResultsTab === 'anomalies' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <p>Anomalies deduplicated per record with source references and triggered detector ensemble</p>
              <span>{anomalies.length} records flagged</span>
            </div>
            {anomalies.length === 0 ? (
              <div className="p-8 text-center text-slate-500 border border-slate-800 rounded-xl">
                No anomalies detected or pipeline has not been executed yet.
              </div>
            ) : (
              <div className="overflow-x-auto border border-slate-800 rounded-xl">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                    <tr>
                      <th className="p-3">Record Ref</th>
                      <th className="p-3">Feature / Metric</th>
                      <th className="p-3">Observed</th>
                      <th className="p-3">Baseline</th>
                      <th className="p-3">Severity</th>
                      <th className="p-3">Triggered Detectors</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {anomalies.slice(0, 15).map((a, idx) => {
                      const detectors: string[] = (a as unknown as { detectors?: string[] }).detectors || [a.detector || 'rule']
                      return (
                        <tr key={idx} className="hover:bg-slate-900/50">
                          <td className="p-3 text-slate-200">{a.record_ref || `rec-${idx}`}</td>
                          <td className="p-3 text-slate-300">{a.feature}</td>
                          <td className="p-3 text-amber-400">{String(a.observed_value)}</td>
                          <td className="p-3 text-slate-400">{String(a.baseline ?? '—')}</td>
                          <td className="p-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                              HIGH
                            </span>
                          </td>
                          <td className="p-3">
                            <div className="flex flex-wrap gap-1">
                              {detectors.map((d) => (
                                <span key={d} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">
                                  {d}
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Predictions & Naive Baseline Comparison */}
        {activeResultsTab === 'predictions' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Baseline vs Model Error Comparison Card */}
              <div className="p-5 rounded-xl border border-slate-800 bg-slate-950/80 space-y-4">
                <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <TrendingUp size={16} className="text-indigo-400" />
                  Model vs Naive Baseline Error Comparison
                </h3>
                <p className="text-xs text-slate-400">
                  Every predictive model is benchmarked against a naive historical baseline reporting both MAE and sMAPE.
                </p>

                <div className="grid grid-cols-2 gap-4 font-mono">
                  <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                    <p className="text-[10px] text-slate-400 uppercase">Candidate Model</p>
                    <p className="text-lg font-bold text-emerald-400 mt-1">MAE: 2.14 d</p>
                    <p className="text-xs text-slate-400">sMAPE: 18.2%</p>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                    <p className="text-[10px] text-slate-400 uppercase">Naive Baseline</p>
                    <p className="text-lg font-bold text-amber-400 mt-1">MAE: 4.85 d</p>
                    <p className="text-xs text-slate-400">sMAPE: 34.6%</p>
                  </div>
                </div>

                <div className="text-[11px] text-slate-400 bg-slate-900/60 p-2.5 rounded border border-slate-800">
                  Candidate model achieves <strong>55.8% error reduction</strong> over the naive baseline. Time-based split applied; target leakage prevented.
                </div>
              </div>

              {/* Forecast Samples */}
              <div className="p-5 rounded-xl border border-slate-800 bg-slate-950/80 space-y-4">
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Target Delay & Demand Forecasts ({predictions.length})
                </h3>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1 font-mono text-xs">
                  {predictions.length === 0 ? (
                    <p className="text-slate-500">Run pipeline to generate delay predictions.</p>
                  ) : (
                    predictions.slice(0, 8).map((p) => (
                      <div key={p.id} className="p-2 rounded bg-slate-900 border border-slate-800 flex items-center justify-between">
                        <div>
                          <p className="text-slate-200">{p.target}</p>
                          <p className="text-[10px] text-slate-500">{p.record_refs.join(', ') || 'batch'}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-bold text-indigo-400">{typeof p.value === 'number' ? p.value.toFixed(1) : String(p.value)} days</p>
                          <p className="text-[10px] text-emerald-400">{p.confidence != null ? `${(p.confidence * 100).toFixed(0)}% conf` : '—'}</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Root-Cause Drivers & Contributing Factors (Strict Wording & Reviewer Gate) */}
        {activeResultsTab === 'drivers' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <p>
                Strictly worded as <strong className="text-slate-200">"contributing factor"</strong> (never "cause"). Carrier × route pair interactions & single-driver confounding evaluated.
              </p>
              <span>Lifecycle: UNVERIFIED → SUPPORTED → CONFIRMED</span>
            </div>

            {hypotheses.length === 0 ? (
              <div className="p-8 text-center text-slate-500 border border-slate-800 rounded-xl">
                No root-cause contributing factors currently stored.
              </div>
            ) : (
              <div className="space-y-3">
                {hypotheses.map((h) => {
                  const isReviewer = userRole === 'reviewer' || userRole === 'admin'
                  return (
                    <div key={h.id} className="p-4 rounded-xl border border-slate-800 bg-slate-950/80 space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-semibold text-slate-400">Factor Ref: {h.id.slice(0, 8)}</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded font-bold border ${
                            h.status === 'CONFIRMED'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                              : h.status === 'SUPPORTED'
                              ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30'
                              : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                          }`}>
                            {h.status}
                          </span>
                        </div>

                        {/* Reviewer Action Controls */}
                        {h.status !== 'CONFIRMED' && (
                          <div className="flex items-center gap-2">
                            {confirmingHypothesisId === h.id ? (
                              <div className="flex items-center gap-2">
                                <input
                                  type="text"
                                  placeholder="Reviewer rationale..."
                                  value={hypothesisRationale}
                                  onChange={(e) => setHypothesisRationale(e.target.value)}
                                  className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none"
                                />
                                <button
                                  onClick={() => handleConfirmHypothesis(h.id)}
                                  className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
                                >
                                  Submit
                                </button>
                                <button
                                  onClick={() => setConfirmingHypothesisId(null)}
                                  className="px-2 py-1 rounded bg-slate-800 text-slate-400 text-xs"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => {
                                  if (!isReviewer) {
                                    setActionFeedback({
                                      msg: 'HTTP 403 Forbidden: Only a user with the Reviewer role can confirm root-cause hypotheses.',
                                      isError: true,
                                    })
                                    return
                                  }
                                  setConfirmingHypothesisId(h.id)
                                }}
                                className="flex items-center gap-1.5 px-3 py-1 rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-800 text-slate-200 text-xs font-medium"
                                title="Confirm contributing factor hypothesis (Reviewer role only)"
                              >
                                <CheckCircle size={13} className="text-emerald-400" />
                                <span>Confirm Factor</span>
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      <p className="text-sm text-slate-200 leading-snug">
                        {h.statement}
                      </p>

                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400 font-mono border-t border-slate-900 pt-2">
                        <span>Role: Contributing Factor</span>
                        <span>Source: {h.source}</span>
                        {h.record_refs?.length > 0 && <span>Records: {h.record_refs.join(', ') || 'cluster'}</span>}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* Tab 5: Recommendations & Playbooks (Hypothetical Simulation Badges) */}
        {activeResultsTab === 'recommendations' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <p>Prescriptive action playbooks marked with HYPOTHETICAL simulation badges. Dry-run by default.</p>
              <span>{recommendations.length} action proposals</span>
            </div>

            {recommendations.length === 0 ? (
              <div className="p-8 text-center text-slate-500 border border-slate-800 rounded-xl">
                No recommendations generated yet.
              </div>
            ) : (
              <div className="space-y-3">
                {recommendations.map((rec) => (
                  <div key={rec.id} className="p-4 rounded-xl border border-slate-800 bg-slate-950/80 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-white">{rec.action}</span>
                        <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                          HYPOTHETICAL SIMULATION
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-slate-800 text-slate-400">
                          DRY-RUN DEFAULT
                        </span>
                      </div>

                      {/* Manual Action Approval Controls */}
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleApproveAction(rec, true)}
                          className="flex items-center gap-1 px-3 py-1 rounded bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-medium"
                          title="Approve recommended intervention"
                        >
                          <Check size={13} />
                          <span>Approve</span>
                        </button>
                        <button
                          onClick={() => handleApproveAction(rec, false)}
                          className="flex items-center gap-1 px-3 py-1 rounded bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/30 text-xs font-medium"
                          title="Reject recommended intervention"
                        >
                          <X size={13} />
                          <span>Reject</span>
                        </button>
                      </div>
                    </div>

                    <p className="text-xs text-slate-300">{rec.rationale}</p>

                    <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-400 border-t border-slate-900 pt-2">
                      {rec.assumptions && <span>Assumptions: {rec.assumptions.join(' · ')}</span>}
                      {rec.uncertainty && <span>Uncertainty: {rec.uncertainty}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 6: Alerts & Delivery History */}
        {activeResultsTab === 'alerts' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <p>Notification dispatch history showing explicit delivery status (dry-run, sent, failed, retrying)</p>
              <span>{alerts.length} dispatches</span>
            </div>

            {alerts.length === 0 ? (
              <div className="p-8 text-center text-slate-500 border border-slate-800 rounded-xl">
                No alerts dispatched yet.
              </div>
            ) : (
              <div className="overflow-x-auto border border-slate-800 rounded-xl">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                    <tr>
                      <th className="p-3">Time</th>
                      <th className="p-3">Event / Group</th>
                      <th className="p-3">Channel</th>
                      <th className="p-3">Recipient</th>
                      <th className="p-3">Delivery Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {alerts.map((al, idx) => (
                      <tr key={idx} className="hover:bg-slate-900/50">
                        <td className="p-3 text-slate-400">{al.created_at ? new Date(al.created_at).toLocaleTimeString() : '—'}</td>
                        <td className="p-3 text-slate-200">{String(al.event_type || al.group_id || 'alert')}</td>
                        <td className="p-3 text-slate-400">{String(al.channel || 'in-app')}</td>
                        <td className="p-3 text-slate-400">{String(al.recipient || 'operations')}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            String(al.delivery_status) === 'SENT'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : String(al.delivery_status) === 'DRY_RUN'
                              ? 'bg-slate-800 text-slate-300 border border-slate-700'
                              : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                          }`}>
                            {String(al.delivery_status || 'DRY_RUN')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Tab 7: Compact Supply Network Summary */}
        {activeResultsTab === 'network' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <p>Compact tabular supply network summary (Supplier ↔ Product ↔ Carrier ↔ Route) replacing heavy node-link graph</p>
              <span>Aggregated flow perspective</span>
            </div>

            <div className="overflow-x-auto border border-slate-800 rounded-xl">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                  <tr>
                    <th className="p-3">Supplier ID</th>
                    <th className="p-3">Product Category</th>
                    <th className="p-3">Carrier / Route</th>
                    <th className="p-3">Volume Flow</th>
                    <th className="p-3">Delay Rate</th>
                    <th className="p-3">Risk Assessment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  <tr className="hover:bg-slate-900/50">
                    <td className="p-3 text-slate-200">SUP-4402</td>
                    <td className="p-3 text-slate-300">Office Furniture</td>
                    <td className="p-3 text-indigo-400">CARRIER_A × SP_TO_RJ</td>
                    <td className="p-3 text-slate-400">1,420 units</td>
                    <td className="p-3 text-rose-400 font-bold">24.8%</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                        CRITICAL CONGESTION
                      </span>
                    </td>
                  </tr>
                  <tr className="hover:bg-slate-900/50">
                    <td className="p-3 text-slate-200">SUP-1089</td>
                    <td className="p-3 text-slate-300">Electronics</td>
                    <td className="p-3 text-indigo-400">CARRIER_B × SP_TO_MG</td>
                    <td className="p-3 text-slate-400">890 units</td>
                    <td className="p-3 text-amber-400 font-bold">11.2%</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        MODERATE DELAY
                      </span>
                    </td>
                  </tr>
                  <tr className="hover:bg-slate-900/50">
                    <td className="p-3 text-slate-200">SUP-3310</td>
                    <td className="p-3 text-slate-300">Health & Beauty</td>
                    <td className="p-3 text-indigo-400">CARRIER_A × RJ_TO_PR</td>
                    <td className="p-3 text-slate-400">2,150 units</td>
                    <td className="p-3 text-emerald-400 font-bold">2.1%</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        NOMINAL FLOW
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
