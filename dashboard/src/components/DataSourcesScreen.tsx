import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileUp, Info, LoaderCircle, RefreshCw, Trash2, X } from 'lucide-react'
import type { ApiClient } from '../api/client'
import { ApiError } from '../api/client'
import type {
  CapabilityResult, DatasetSource, ImportJob, MappingSuggestion, MappingVersion,
  RelationshipPreview, Role,
} from '../api/types'
import { TypeBadge } from './TypeBadge'

type Tab = 'sources' | 'upload' | 'mapping' | 'relationships' | 'capabilities' | 'history'

const ALLOWED_EXT = ['.csv', '.xlsx', '.json', '.jsonl', '.zip']
const roleRank: Record<Role, number> = { viewer: 1, analyst: 2, reviewer: 3, admin: 4 }
const can = (role: Role, min: Role) => roleRank[role] >= roleRank[min]

function Spinner() { return <LoaderCircle size={16} className="animate-spin text-muted" /> }
function ErrBox({ msg }: { msg: string }) {
  return <div className="ds-err" role="alert"><AlertTriangle size={15} /><span>{msg}</span></div>
}
function InfoBox({ msg }: { msg: string }) {
  return <div className="ds-info"><Info size={14} /><span>{msg}</span></div>
}
function PermDenied({ reason }: { reason: string }) {
  return <div className="ds-perm-denied"><LockIcon /><span>Permission denied: {reason}</span></div>
}
function LockIcon() { return <span style={{ fontSize: 15 }}>🔒</span> }

const STATUS_COLORS: Record<string, string> = {
  COMPLETED: 'chip-ok', RUNNING: 'chip-running', QUEUED: 'chip-queued',
  PARTIAL: 'chip-warn', FAILED: 'chip-err',
}

// ── Sources tab ────────────────────────────────────────────────────────────────

function SourcesTab({ client, role }: { client: ApiClient; role: Role }) {
  const [sources, setSources] = useState<DatasetSource[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setSources((await client.datasets()).items) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load sources') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  const handleDelete = async (datasetName: string) => {
    if (!confirm(`Remove dataset "${datasetName}" from active monitoring? (Raw source and audit history will be preserved).`)) return
    try {
      await client.deleteDataset(datasetName)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete dataset')
    }
  }

  if (loading) return <div className="ds-loading"><Spinner />Loading data sources…</div>
  if (error) return <ErrBox msg={error} />
  if (!sources?.length) return <div className="ds-empty">No data sources registered for this company scope.</div>

  return (
    <div className="ds-table-wrap">
      <table className="metric-table">
        <thead><tr><th>Name</th><th>Status</th><th>Mapping</th><th>Hash (first 12)</th><th>Uploaded</th><th className="text-right">Action</th></tr></thead>
        <tbody>
          {sources.map((src) => (
            <tr key={src.source_id}>
              <td className="font-semibold">{src.dataset_name || src.source_id}</td>
              <td><span className={`status-chip ${src.monitoring ? 'chip-ok' : 'chip-queued'}`}>{src.monitoring ? 'Monitoring' : 'Inactive'}</span></td>
              <td><span className={`status-chip ${src.mapping_status === 'ACCEPTED' ? 'chip-ok' : src.mapping_status === 'REJECTED' ? 'chip-err' : 'chip-queued'}`}>{src.mapping_status ?? 'UNKNOWN'}</span></td>
              <td className="hash-cell">{src.sha256?.slice(0, 12) ?? 'UNKNOWN'}</td>
              <td className="text-xs text-muted">{src.uploaded_at ?? 'UNKNOWN'}</td>
              <td className="text-right">
                <button
                  disabled={!can(role, 'admin')}
                  title={can(role, 'admin') ? 'Delete dataset' : 'Requires admin role to delete sources'}
                  onClick={() => handleDelete(src.dataset_name)}
                  className="rounded-lg p-1.5 text-rose-500 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-rose-950/40"
                >
                  <Trash2 size={14} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="ds-actions">
        <button className="icon-button" aria-label="Refresh sources" onClick={() => void load()}><RefreshCw size={14} /></button>
        {!can(role, 'admin') && <span className="text-xs text-muted">Admin role required to delete sources.</span>}
      </div>
    </div>
  )
}

// ── Upload tab ─────────────────────────────────────────────────────────────────

function UploadTab({ client, role }: { client: ApiClient; role: Role }) {
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [datasetName, setDatasetName] = useState('')
  const [job, setJob] = useState<ImportJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollTimer, setPollTimer] = useState<ReturnType<typeof setInterval> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const TERMINAL = new Set(['COMPLETED', 'FAILED', 'PARTIAL'])

  function pickFile(f: File) {
    const ext = '.' + (f.name.split('.').pop()?.toLowerCase() ?? '')
    if (!ALLOWED_EXT.includes(ext)) { setError(`Unsupported file type (${ext}). Allowed: ${ALLOWED_EXT.join(', ')}`); return }
    setFile(f); setError(null)
  }

  function clearPoll() { if (pollTimer) { clearInterval(pollTimer); setPollTimer(null) } }

  async function startPoll(jobId: string) {
    clearPoll()
    const t = setInterval(async () => {
      try {
        const j = await client.importJob(jobId)
        setJob(j)
        if (TERMINAL.has(j.status)) clearPoll()
      } catch { clearPoll() }
    }, 3000)
    setPollTimer(t)
  }

  async function upload() {
    if (!file || !can(role, 'analyst')) return
    setBusy(true); setError(null); setJob(null)
    const form = new FormData()
    form.append('file', file)
    if (datasetName.trim()) form.append('dataset_name', datasetName.trim())
    try {
      const j = await client.uploadDataset(form)
      setJob(j)
      if (!TERMINAL.has(j.status)) await startPoll(j.import_job_id)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Upload failed')
    } finally { setBusy(false) }
  }

  if (!can(role, 'analyst')) return <PermDenied reason="Analyst role required to upload files." />

  return (
    <div className="upload-tab">
      <InfoBox msg="Files are stored immutably. SHA-256 is verified after upload. Multi-table ZIP archives will import each table as a separate data source." />
      <div
        className={`upload-zone ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) pickFile(f) }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload file drop zone"
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click() }}
      >
        <FileUp size={32} className="upload-zone-icon" />
        <p className="upload-zone-label">{file ? file.name : 'Drop a file here or click to browse'}</p>
        <p className="upload-zone-hint">CSV, XLSX (multi-sheet supported), JSON, JSONL, ZIP · max 50 MB</p>
        <input ref={inputRef} type="file" className="sr-only" accept={ALLOWED_EXT.join(',')}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f) }} />
      </div>

      <label className="form-label mt-4 max-w-sm">
        Dataset name (optional)
        <input className="text-input mt-2" value={datasetName} onChange={(e) => setDatasetName(e.target.value)} placeholder="e.g. supplier_orders_2026" />
      </label>

      {error && <ErrBox msg={error} />}

      <button className="primary-button mt-4" disabled={!file || busy} onClick={() => void upload()}>
        {busy ? <><Spinner />Uploading…</> : <><FileUp size={15} />Upload file</>}
      </button>

      {job && (
        <div className="job-card mt-5">
          <div className="flex items-center gap-3">
            <span className={`status-chip ${STATUS_COLORS[job.status] ?? 'chip-queued'}`}>{job.status}</span>
            <TypeBadge kind="FACT" />
            <span className="text-xs text-muted">Job: {job.import_job_id}</span>
          </div>
          {job.sha256 && <p className="mt-2 text-xs text-muted">SHA-256: {job.sha256.slice(0, 32)}…</p>}
          {(job.processed_rows != null || job.total_rows != null) && (
            <p className="mt-1 text-xs text-muted">
              Rows: {job.processed_rows ?? '?'} / {job.total_rows ?? 'UNKNOWN'}
            </p>
          )}
          {job.error && <ErrBox msg={job.error} />}
          {!TERMINAL.has(job.status) && <p className="mt-2 text-xs text-muted animate-pulse">Polling for status…</p>}
        </div>
      )}
    </div>
  )
}

// ── Mapping wizard tab ─────────────────────────────────────────────────────────

function MappingTab({ client, role }: { client: ApiClient; role: Role }) {
  const [sources, setSources] = useState<DatasetSource[]>([])
  const [selected, setSelected] = useState('')
  const [suggestions, setSuggestions] = useState<MappingSuggestion[] | null>(null)
  const [versions, setVersions] = useState<MappingVersion[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    client.datasets().then((p) => setSources(p.items)).catch(() => { /* ignore */ })
  }, [client])

  async function loadSuggestions(name: string) {
    if (!name) return
    setLoading(true); setError(null); setSuggestions(null); setVersions(null)
    try {
      const [suggRes, verRes] = await Promise.all([
        client.datasetSuggestions(name),
        client.mappingVersions(name),
      ])
      setSuggestions(suggRes.suggestions)
      setVersions(verRes.items)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load mapping data') }
    finally { setLoading(false) }
  }

  async function accept(version: string) {
    if (!reason.trim() || !can(role, 'analyst')) return
    setBusy(version); setMsg(null)
    try {
      await client.acceptMapping(selected, version, reason)
      setMsg(`Version ${version} accepted.`)
      await loadSuggestions(selected)
    } catch (e) { setMsg(e instanceof Error ? e.message : 'Accept failed') }
    finally { setBusy(null) }
  }

  async function reject(version: string) {
    if (!reason.trim() || !can(role, 'analyst')) return
    setBusy(`rej-${version}`); setMsg(null)
    try {
      await client.rejectMapping(selected, version, reason)
      setMsg(`Version ${version} rejected.`)
      await loadSuggestions(selected)
    } catch (e) { setMsg(e instanceof Error ? e.message : 'Reject failed') }
    finally { setBusy(null) }
  }

  if (!can(role, 'analyst')) return <PermDenied reason="Analyst role required to view or accept mapping suggestions." />

  return (
    <div className="mapping-tab space-y-5">
      <div className="ds-notice-bar">
        <Info size={14} />
        <strong>Suggestions are never auto-confirmed.</strong>
        {' '}Explicit acceptance is required before a mapping version becomes active.
      </div>

      <label className="form-label max-w-sm">
        Select dataset
        <select className="text-input mt-2" value={selected}
          onChange={(e) => { setSelected(e.target.value); void loadSuggestions(e.target.value) }}>
          <option value="">— choose —</option>
          {sources.map((s) => <option key={s.source_id} value={s.dataset_name}>{s.dataset_name}</option>)}
        </select>
      </label>

      {loading && <div className="ds-loading"><Spinner />Loading suggestions…</div>}
      {error && <ErrBox msg={error} />}

      {suggestions && (
        <section className="panel">
          <div className="panel-heading"><div><h3>Column mapping suggestions</h3><p>Confidence scores from the local suggester. All suggestions remain PENDING until a reviewer accepts.</p></div></div>
          <div className="table-scroll">
            <table className="metric-table">
              <thead><tr><th>Column</th><th>Suggested role</th><th>Confidence</th><th>Reason</th><th>Clarification needed</th></tr></thead>
              <tbody>
                {suggestions.map((s) => (
                  <tr key={s.column}>
                    <td className="font-mono text-xs">{s.column}</td>
                    <td>{s.suggested_role ?? <span className="text-muted">None</span>}</td>
                    <td>
                      <span className={`suggestion-confidence ${s.confidence >= 0.7 ? 'conf-high' : s.confidence >= 0.4 ? 'conf-mid' : 'conf-low'}`}>
                        {(s.confidence * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="text-xs text-muted max-w-xs">{s.reason}</td>
                    <td>{s.needs_clarification ? <span className="text-amber-700 font-semibold text-xs">Yes</span> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {versions && (
        <section className="panel">
          <div className="panel-heading"><div><h3>Mapping versions</h3><p>Reviewer can accept or reject pending versions.</p></div></div>
          {versions.length === 0
            ? <div className="ds-empty">No mapping versions yet for this dataset.</div>
            : (
              <div className="divide-y divide-line dark:divide-slate-800">
                {versions.map((v) => (
                  <div key={v.version} className="mapping-wizard-row">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`status-chip ${v.status === 'ACCEPTED' ? 'chip-ok' : v.status === 'REJECTED' ? 'chip-err' : 'chip-queued'}`}>{v.status}</span>
                      <span className="text-xs font-mono text-muted">v{v.version}</span>
                      {v.reason && <span className="text-xs text-muted">· {v.reason}</span>}
                    </div>
                    <div className="text-xs text-muted mt-1">
                      Mappings: {Object.entries(v.mappings).map(([col, role]) => `${col}→${role}`).join(', ') || 'none'}
                    </div>
                    {v.status === 'PENDING_REVIEW' && can(role, 'analyst') && (
                      <div className="flex flex-wrap gap-2 mt-3">
                        <label className="sr-only" htmlFor={`reason-${v.version}`}>Reason for decision</label>
                        <input id={`reason-${v.version}`} className="text-input flex-1 min-w-48" value={reason}
                          onChange={(e) => setReason(e.target.value)} placeholder="Required reason" />
                        <button className="primary-button" disabled={!reason.trim() || !!busy} onClick={() => void accept(v.version)}>
                          {busy === v.version ? <Spinner /> : <CheckCircle2 size={14} />}{' '}Accept
                        </button>
                        <button className="btn-secondary" disabled={!reason.trim() || !!busy} onClick={() => void reject(v.version)}>
                          {busy === `rej-${v.version}` ? <Spinner /> : <X size={14} />}{' '}Reject
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          {msg && <p className="m-4 text-xs" role="status">{msg}</p>}
        </section>
      )}
    </div>
  )
}

// ── Relationships tab ──────────────────────────────────────────────────────────

function RelationshipsTab({ client, role }: { client: ApiClient; role: Role }) {
  const [sources, setSources] = useState<DatasetSource[]>([])
  const [leftSrc, setLeftSrc] = useState(''); const [leftKey, setLeftKey] = useState('')
  const [rightSrc, setRightSrc] = useState(''); const [rightKey, setRightKey] = useState('')
  const [relType, setRelType] = useState('order_shipment')
  const [preview, setPreview] = useState<RelationshipPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [approving, setApproving] = useState(false)
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { client.datasets().then((p) => setSources(p.items)).catch(() => { /* ignore */ }) }, [client])

  async function runPreview() {
    if (!leftSrc || !leftKey || !rightSrc || !rightKey) return
    setBusy(true); setError(null); setPreview(null); setMsg(null)
    try {
      const res = await client.relationshipPreview({
        links: [{ left_source_id: leftSrc, left_key: leftKey, right_source_id: rightSrc, right_key: rightKey, relationship: relType }],
      })
      setPreview(res)
    } catch (e) { setError(e instanceof Error ? e.message : 'Preview failed') }
    finally { setBusy(false) }
  }

  async function approve() {
    if (!preview?.proposal_id || !reason.trim() || !can(role, 'analyst')) return
    setApproving(true); setMsg(null)
    try { await client.approveRelationship(preview.proposal_id, reason); setMsg('Relationship approved and persisted.') }
    catch (e) { setMsg(e instanceof Error ? e.message : 'Approve failed') }
    finally { setApproving(false) }
  }

  if (!can(role, 'analyst')) return <PermDenied reason="Analyst role required to preview or approve relationships." />

  return (
    <div className="space-y-5">
      <InfoBox msg="Preview shows matched, orphan and null-key counts. A pending proposal is created; it is activated upon approval." />
      <div className="grid gap-4 md:grid-cols-2">
        {[['Left', leftSrc, setLeftSrc, leftKey, setLeftKey], ['Right', rightSrc, setRightSrc, rightKey, setRightKey]].map(([side, src, setSrc, key, setKey]) => (
          <div key={String(side)} className="panel p-4 space-y-3">
            <p className="text-sm font-semibold">{String(side)} source</p>
            <label className="form-label text-xs">Source
              <select className="text-input mt-1" value={String(src)}
                onChange={(e) => (setSrc as (v: string) => void)(e.target.value)}>
                <option value="">— choose —</option>
                {sources.map((s) => <option key={s.source_id} value={s.source_id}>{s.dataset_name}</option>)}
              </select>
            </label>
            <label className="form-label text-xs">Join key column
              <input className="text-input mt-1" value={String(key)}
                onChange={(e) => (setKey as (v: string) => void)(e.target.value)} placeholder="e.g. order_id" />
            </label>
          </div>
        ))}
      </div>
      <label className="form-label max-w-xs">Relationship type
        <input className="text-input mt-1" value={relType} onChange={(e) => setRelType(e.target.value)} />
      </label>
      <button className="primary-button" disabled={busy || !leftSrc || !leftKey || !rightSrc || !rightKey}
        onClick={() => void runPreview()}>
        {busy ? <><Spinner />Running preview…</> : 'Preview relationship'}
      </button>
      {error && <ErrBox msg={error} />}
      {preview && (
        <div className="panel p-5 space-y-4">
          {preview.links.map((link, i) => (
            <div key={i} className="grid grid-cols-3 gap-3 text-center">
              <div className="stat-cell"><p className="stat-val text-emerald-700">{link.matched.toLocaleString()}</p><p className="stat-label">Matched</p></div>
              <div className="stat-cell"><p className="stat-val text-amber-700">{(link.orphan_left + link.orphan_right).toLocaleString()}</p><p className="stat-label">Orphans (both sides)</p></div>
              <div className="stat-cell"><p className="stat-val text-rose-700">{link.null_keys.toLocaleString()}</p><p className="stat-label">Null keys</p></div>
            </div>
          ))}
          {preview.proposal_id && can(role, 'analyst') && (
            <div className="space-y-2 border-t border-line pt-4 dark:border-slate-800">
              <p className="text-xs font-semibold text-muted">Proposal ID: {preview.proposal_id} — approve to persist</p>
              <label className="form-label text-xs">Reason (required)
                <input className="text-input mt-1" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reviewer reason for approval" />
              </label>
              <button className="primary-button" disabled={!reason.trim() || approving} onClick={() => void approve()}>
                {approving ? <><Spinner />Approving…</> : <><CheckCircle2 size={14} />Approve relationship</>}
              </button>
              {msg && <p className="text-xs" role="status">{msg}</p>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Capabilities tab ───────────────────────────────────────────────────────────

function CapabilitiesTab({ client, role }: { client: ApiClient; role: Role }) {
  const [sources, setSources] = useState<DatasetSource[]>([])
  const [selected, setSelected] = useState('')
  const [caps, setCaps] = useState<CapabilityResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { client.datasets().then((p) => setSources(p.items)).catch(() => { /* ignore */ }) }, [client])

  async function load(name: string) {
    if (!name) return
    setLoading(true); setError(null); setCaps(null)
    try {
      const res = await client.datasetSuggestions(name)
      setCaps(res.capabilities ?? [])
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load capabilities') }
    finally { setLoading(false) }
  }

  if (!can(role, 'viewer')) return <PermDenied reason="Viewer role required to view capability assessment." />

  return (
    <div className="space-y-5">
      <InfoBox msg="Capabilities are derived from accepted mapping roles. AVAILABLE = all required roles present. BLOCKED = missing roles listed." />
      <label className="form-label max-w-sm">Select dataset
        <select className="text-input mt-2" value={selected}
          onChange={(e) => { setSelected(e.target.value); void load(e.target.value) }}>
          <option value="">— choose —</option>
          {sources.map((s) => <option key={s.source_id} value={s.dataset_name}>{s.dataset_name}</option>)}
        </select>
      </label>
      {loading && <div className="ds-loading"><Spinner />Assessing capabilities…</div>}
      {error && <ErrBox msg={error} />}
      {caps && (caps.length === 0
        ? <div className="ds-empty">No capability results returned. The API may not expose capability assessment for this dataset.</div>
        : (
          <div className="panel divide-y divide-line dark:divide-slate-800">
            {caps.map((cap) => (
              <div key={cap.name} className={`cap-row cap-${cap.status.toLowerCase().replace(/_/g, '-')}`}>
                <span className="cap-icon">
                  {cap.status === 'AVAILABLE' ? '✅' : cap.status === 'UNSUPPORTED' || cap.status === 'NOT_IMPLEMENTED' ? '⬛' : '⚠️'}
                </span>
                <div>
                  <p className="text-sm font-semibold">{cap.name.replace(/_/g, ' ')}</p>
                  <p className="text-xs text-muted">{cap.status}</p>
                  {cap.missing_roles?.length ? <p className="text-xs text-rose-700 mt-1">Missing roles: {cap.missing_roles.join(', ')}</p> : null}
                  {cap.limitations?.map((l) => <p key={l} className="text-xs text-muted">{l}</p>)}
                </div>
              </div>
            ))}
          </div>
        ))}
    </div>
  )
}

// ── Import history tab ─────────────────────────────────────────────────────────

function HistoryTab({ client, role }: { client: ApiClient; role: Role }) {
  const [jobs, setJobs] = useState<ImportJob[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setJobs((await client.importHistory()).items) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load history') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  if (!can(role, 'viewer')) return <PermDenied reason="Viewer role required to view import history." />
  if (loading) return <div className="ds-loading"><Spinner />Loading import history…</div>
  if (error) return <ErrBox msg={error} />
  if (!jobs?.length) return <div className="ds-empty">No import jobs found for this company scope.</div>

  return (
    <div className="space-y-3">
      <div className="flex justify-end"><button className="icon-button" aria-label="Refresh history" onClick={() => void load()}><RefreshCw size={14} /></button></div>
      <div className="table-scroll">
        <table className="metric-table">
          <thead><tr><th>Job ID</th><th>Dataset</th><th>Status</th><th>Processed / Total rows</th><th>Created</th></tr></thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.import_job_id}>
                <td className="hash-cell text-xs">{j.import_job_id.slice(0, 20)}…</td>
                <td>{j.dataset_name ?? 'UNKNOWN'}</td>
                <td><span className={`status-chip ${STATUS_COLORS[j.status] ?? 'chip-queued'}`}>{j.status}</span></td>
                <td>{j.processed_rows ?? '?'} / {j.total_rows ?? 'UNKNOWN'}</td>
                <td className="text-xs text-muted">{j.created_at ?? 'UNKNOWN'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <InfoBox msg="PARTIAL status means processing stopped after consuming some rows; the final row count is uncertain. Re-upload or reprocess to get a complete import." />
    </div>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: 'sources', label: 'Sources' },
  { id: 'upload', label: 'Upload' },
  { id: 'mapping', label: 'Mapping wizard' },
  { id: 'relationships', label: 'Relationships' },
  { id: 'capabilities', label: 'Capabilities' },
  { id: 'history', label: 'Import history' },
]

export function DataSourcesScreen({ client, role }: { client: ApiClient; role: Role }) {
  const [tab, setTab] = useState<Tab>('sources')

  return (
    <div className="space-y-5">
      <section className="page-intro">
        <div>
          <p className="eyebrow">DATA MANAGEMENT / SOURCES</p>
          <h2>Data sources</h2>
          <p>Upload, profile, map and monitor company-scoped data sources.</p>
        </div>
        <TypeBadge kind="FACT" />
      </section>

      <div className="panel overflow-hidden">
        <div className="tab-bar">
          {TABS.map((t) => (
            <button key={t.id} className={`tab-button ${tab === t.id ? 'tab-active' : ''}`}
              onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="p-5">
          {tab === 'sources' && <SourcesTab client={client} role={role} />}
          {tab === 'upload' && <UploadTab client={client} role={role} />}
          {tab === 'mapping' && <MappingTab client={client} role={role} />}
          {tab === 'relationships' && <RelationshipsTab client={client} role={role} />}
          {tab === 'capabilities' && <CapabilitiesTab client={client} role={role} />}
          {tab === 'history' && <HistoryTab client={client} role={role} />}
        </div>
      </div>
    </div>
  )
}
