import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, ChevronRight, Cpu, FileSearch, LoaderCircle, RefreshCw } from 'lucide-react'
import type { ApiClient } from '../api/client'
import type { Role } from '../api/types'
import { TypeBadge } from './TypeBadge'

const roleRank: Record<Role, number> = { viewer: 1, analyst: 2, reviewer: 3, admin: 4 }
const can = (role: Role, min: Role) => roleRank[role] >= roleRank[min]

function Spinner() { return <LoaderCircle size={16} className="animate-spin text-muted" /> }
function ErrBox({ msg }: { msg: string }) {
  return <div className="ds-err" role="alert"><AlertTriangle size={15} /><span>{msg}</span></div>
}
function text(v: unknown) { return v == null ? 'UNKNOWN' : typeof v === 'string' ? v : JSON.stringify(v) }

// ── Model versions ─────────────────────────────────────────────────────────────

function ModelVersionsSection({
  client, role, onAudit,
}: { client: ApiClient; role: Role; onAudit: () => void }) {
  const [models, setModels] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [evalReport, setEvalReport] = useState<Record<string, unknown> | null>(null)
  const [evalLoading, setEvalLoading] = useState(false)
  const [evalError, setEvalError] = useState<string | null>(null)
  const [promoteBusy, setPromoteBusy] = useState<string | null>(null)
  const [rollbackBusy, setRollbackBusy] = useState(false)
  const [govMsg, setGovMsg] = useState<string | null>(null)
  const [promoteReason, setPromoteReason] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setModels((await client.models()).items) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load models') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  async function loadEval(id: string) {
    setExpanded(id); setEvalReport(null); setEvalError(null); setEvalLoading(true)
    try { setEvalReport(await client.modelEvalReport(id)) }
    catch (e) { setEvalError(e instanceof Error ? e.message : 'Failed to load eval report') }
    finally { setEvalLoading(false) }
  }

  async function promote(version: string) {
    if (!promoteReason.trim() || !can(role, 'reviewer')) return
    setPromoteBusy(version); setGovMsg(null)
    try {
      await client.promoteModel(version, promoteReason)
      setGovMsg(`Model ${version} promoted.`)
      setPromoteReason('')
      await load()
    } catch (e) { setGovMsg(e instanceof Error ? e.message : 'Promote failed') }
    finally { setPromoteBusy(null) }
  }

  async function rollback(modelKey: string) {
    if (!promoteReason.trim() || !can(role, 'reviewer')) return
    setRollbackBusy(true); setGovMsg(null)
    try {
      await client.rollbackModel(modelKey, promoteReason)
      setGovMsg(`Rollback of ${modelKey} recorded.`)
      setPromoteReason('')
      await load()
    } catch (e) { setGovMsg(e instanceof Error ? e.message : 'Rollback failed') }
    finally { setRollbackBusy(false) }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>Model versions</h3><TypeBadge kind="FACT" /></div>
          <p>Stored versions with artifact hash and training data reference. Promote/rollback requires reviewer.</p>
        </div>
        <button className="icon-button" aria-label="Refresh models" onClick={() => void load()}><RefreshCw size={14} /></button>
      </div>

      {loading && <div className="loading-state py-8"><Spinner />Loading models…</div>}
      {error && <div className="p-5"><ErrBox msg={error} /></div>}
      {!loading && !error && models.length === 0 && (
        <div className="empty-state"><Cpu size={20} /><p>No model versions stored for this scope.</p></div>
      )}

      {models.map((m, i) => {
        const id = text(m.id || m.name)
        const version = text(m.version)
        const modelKey = `${text(m.name)}:${version}`
        return (
          <div key={String(m.id ?? i)} className="model-card">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <TypeBadge kind="FACT" />
                <strong className="text-sm">{text(m.name)} · {version}</strong>
              </div>
              <button className="text-xs text-brand flex items-center gap-1"
                onClick={() => { if (expanded === id) setExpanded(null); else void loadEval(String(m.id ?? id)) }}>
                <ChevronRight size={13} className={expanded === id ? 'rotate-90 transition-transform' : 'transition-transform'} />
                Evaluation report
              </button>
            </div>
            <div className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
              <div><span className="text-muted">Trained</span><p>{text(m.trained_at)}</p></div>
              <div><span className="text-muted">Data version</span><p>{text(m.training_data_version)}</p></div>
              <div className="sm:col-span-2"><span className="text-muted">Artifact SHA-256</span><p className="hash-cell">{text(m.artifact_hash)}</p></div>
            </div>

            {/* Eval report */}
            {expanded === id && (
              <div className="mt-3 border-t border-line pt-3 dark:border-slate-800">
                {evalLoading && <div className="ds-loading"><Spinner />Loading report…</div>}
                {evalError && <ErrBox msg={evalError} />}
                {evalReport && (
                  <pre className="json-block">{JSON.stringify(evalReport, null, 2)}</pre>
                )}
              </div>
            )}

            {/* Governance actions */}
            {can(role, 'reviewer') && (
              <div className="mt-3 border-t border-line pt-3 dark:border-slate-800">
                <div className="flex flex-wrap gap-2 items-center">
                  <input
                    className="text-input flex-1 min-w-40 text-xs"
                    value={promoteReason}
                    onChange={(e) => setPromoteReason(e.target.value)}
                    placeholder="Reviewer reason (required)"
                  />
                  <button
                    className="primary-button text-xs"
                    disabled={!promoteReason.trim() || !!promoteBusy}
                    onClick={() => void promote(version)}
                  >
                    {promoteBusy === version ? <Spinner /> : 'Promote'}
                  </button>
                  <button
                    className="btn-secondary text-xs"
                    disabled={!promoteReason.trim() || rollbackBusy}
                    onClick={() => void rollback(modelKey)}
                  >
                    {rollbackBusy ? <Spinner /> : 'Rollback'}
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span className="text-muted">Quick reasons:</span>
                  {['Validated on holdout test set', 'Performance drift observed', 'Quarterly model refresh', 'Emergency rollback'].map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      className="rounded bg-slate-100 px-2 py-0.5 text-muted hover:bg-brand/10 hover:text-brand dark:bg-slate-800 dark:hover:bg-slate-700 transition-colors"
                      onClick={() => setPromoteReason(preset)}
                    >
                      + {preset}
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-[10px] text-muted">
                  Transparency Rule: Model promotions and rollbacks write an immutable audit log. Entering a reviewer rationale ensures audit traceability.
                </p>
              </div>
            )}
          </div>
        )
      })}

      {govMsg && <p className="m-4 text-xs" role="status">{govMsg}</p>}

      {/* Audit shortcut */}
      <div className="p-4 border-t border-line dark:border-slate-800 flex items-center gap-2">
        <FileSearch size={14} className="text-muted" />
        <button className="text-xs text-brand font-semibold underline" onClick={onAudit}>
          View full hash-chained audit log →
        </button>
      </div>
    </section>
  )
}

// ── Failed pipeline jobs notice ───────────────────────────────────────────────

function PipelineJobsNotice() {
  return (
    <section className="panel p-5">
      <div className="flex items-center gap-2 mb-2">
        <h3 className="text-sm font-semibold">Failed pipeline jobs</h3>
        <TypeBadge kind="FACT" />
      </div>
      <div className="ds-info">
        <AlertTriangle size={14} />
        <span>
          Not available — no pipeline run history endpoint exists in the current API contract.
          <br />
          <span className="text-xs text-muted">Backend gap: <code>GET /api/v1/pipeline/runs</code> is not implemented.</span>
        </span>
      </div>
    </section>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────────

export function SystemHealthScreen({
  client, role, onAudit,
}: { client: ApiClient; role: Role; onAudit: () => void }) {
  return (
    <div className="space-y-7">
      <section className="page-intro">
        <div>
          <p className="eyebrow">GOVERNANCE / SYSTEM HEALTH</p>
          <h2>Models and system health</h2>
          <p>Model versions, evaluation reports, governance actions and drift. Audit trail below.</p>
        </div>
        <TypeBadge kind="FACT" />
      </section>

      <ModelVersionsSection client={client} role={role} onAudit={onAudit} />
      <PipelineJobsNotice />

      <div className="panel p-5 text-xs text-muted space-y-2">
        <p className="font-semibold text-ink dark:text-white">Drift summary</p>
        <p>Per-source drift is visible in the Monitoring screen (reviewer role required). Drift is advisory — never an automatic retrain trigger.</p>
      </div>
    </div>
  )
}
