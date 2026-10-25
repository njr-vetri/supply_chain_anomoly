import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, LoaderCircle, RefreshCw, X } from 'lucide-react'
import type { ApiClient } from '../api/client'
import type { Action, Approval, Outcome, Recommendation, Role, WhatIfRequest } from '../api/types'
import { TypeBadge } from './TypeBadge'

const roleRank: Record<Role, number> = { viewer: 1, analyst: 2, reviewer: 3, admin: 4 }
const can = (role: Role, min: Role) => roleRank[role] >= roleRank[min]

function Spinner() { return <LoaderCircle size={16} className="animate-spin text-muted" /> }
function ErrBox({ msg }: { msg: string }) {
  return <div className="ds-err" role="alert"><AlertTriangle size={15} /><span>{msg}</span></div>
}
function PermDenied({ reason }: { reason: string }) {
  return <div className="ds-perm-denied">🔒 Permission denied: {reason}</div>
}

// ── Approval workflow per recommendation ──────────────────────────────────────

function ApprovalWidget({
  rec, approvals, actions, outcomes, role, client, onRefresh,
}: {
  rec: Recommendation
  approvals: Approval[]
  actions: Action[]
  outcomes: Outcome[]
  role: Role
  client: ApiClient
  onRefresh: () => void
}) {
  const recApprovals = approvals.filter((a) => a.recommendation_id === rec.id)
  const recActions = actions.filter((a) => a.recommendation_id === rec.id)
  const actionIds = new Set(recActions.map((a) => a.id))
  const recOutcomes = outcomes.filter((o) => actionIds.has(o.action_id))

  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  async function createApproval() {
    if (!can(role, 'analyst')) return
    setBusy('create'); setMsg(null)
    try {
      await client.createApproval({ recommendation_id: rec.id })
      setMsg('Approval request created.')
      onRefresh()
    } catch (e) { setMsg(e instanceof Error ? e.message : 'Failed') }
    finally { setBusy(null) }
  }

  async function decide(approvalId: string, decision: 'approve' | 'reject') {
    if (!reason.trim() || !can(role, 'reviewer')) return
    setBusy(approvalId + decision); setMsg(null)
    try {
      if (decision === 'approve') await client.approve(approvalId, { rationale: reason })
      else await client.reject(approvalId, { rationale: reason })
      setMsg(`Approval ${decision}d.`)
      setReason('')
      onRefresh()
    } catch (e) { setMsg(e instanceof Error ? e.message : 'Failed') }
    finally { setBusy(null) }
  }

  return (
    <div className="approval-widget space-y-3">
      {/* Actions */}
      {recActions.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-muted mb-1">Actions</p>
          {recActions.map((act) => (
            <div key={act.id} className="history-row">
              {act.dry_run ? <TypeBadge kind="DRY_RUN" /> : <TypeBadge kind="FACT" />}
              <span className="text-xs">{act.status}{act.dry_run ? ' · No external action executed.' : ''}</span>
            </div>
          ))}
        </div>
      )}

      {/* Outcomes */}
      {recOutcomes.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-muted mb-1">Linked outcomes</p>
          {recOutcomes.map((o) => (
            <div key={o.id} className="history-row">
              <TypeBadge kind="FACT" />
              <span className="text-xs">Observed: {o.observed_at} · Source: {o.source}</span>
            </div>
          ))}
        </div>
      )}

      {/* Approvals */}
      {recApprovals.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-muted mb-1">Approvals</p>
          {recApprovals.map((a) => (
            <div key={a.id} className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`status-chip ${a.status === 'approved' ? 'chip-ok' : a.status === 'rejected' ? 'chip-err' : 'chip-queued'}`}>{a.status}</span>
                <TypeBadge kind="FACT" />
                <span className="text-xs text-muted">{a.reviewer_id ?? 'reviewer UNKNOWN'} · {a.reviewed_at}</span>
              </div>
              {a.status === 'pending' && can(role, 'reviewer') && (
                <div className="flex flex-wrap gap-2">
                  <input className="text-input flex-1 min-w-40 text-xs"
                    aria-label={`Approval reason ${a.id}`}
                    value={reason} onChange={(e) => setReason(e.target.value)}
                    placeholder="Reviewer rationale required" />
                  <button className="primary-button text-xs" disabled={!reason.trim() || !!busy}
                    onClick={() => void decide(a.id, 'approve')}>
                    {busy === a.id + 'approve' ? <Spinner /> : <CheckCircle2 size={13} />} Approve
                  </button>
                  <button className="btn-secondary text-xs" disabled={!reason.trim() || !!busy}
                    onClick={() => void decide(a.id, 'reject')}>
                    {busy === a.id + 'reject' ? <Spinner /> : <X size={13} />} Reject
                  </button>
                </div>
              )}
              {a.status === 'pending' && !can(role, 'reviewer') && (
                <PermDenied reason="Reviewer role required to approve or reject." />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create approval */}
      {can(role, 'analyst') ? (
        <button className="btn-secondary text-xs" disabled={!!busy} onClick={() => void createApproval()}>
          {busy === 'create' ? <Spinner /> : '+ Create approval request'}
        </button>
      ) : (
        <PermDenied reason="Analyst role required to create an approval request." />
      )}

      {msg && <p className="text-xs" role="status">{msg}</p>}
      <p className="text-[10px] italic text-muted">No external action is executed by this view. All actions are DRY_RUN until verified by a reviewer.</p>
    </div>
  )
}

// ── What-if panel ──────────────────────────────────────────────────────────────

function WhatIfPanel({ client, role }: { client: ApiClient; role: Role }) {
  const [orderCount, setOrderCount] = useState(10)
  const [prob, setProb] = useState(0.4)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    if (!can(role, 'analyst')) return
    setBusy(true); setError(null); setResult(null)
    const body: WhatIfRequest = {
      affected_order_count: orderCount,
      calibrated_delay_probability: prob,
      probability_calibrated: true,
      scenarios: [{ name: 'monitoring', assumed_relative_probability_reduction: 0.1, assumptions: ['Monitoring reduces exposure by 10%'] }],
    }
    try { setResult(await client.whatIf(body)) }
    catch (e) { setError(e instanceof Error ? e.message : 'What-if request failed') }
    finally { setBusy(false) }
  }

  if (!can(role, 'analyst')) return <PermDenied reason="Analyst role required for what-if scenarios." />

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>What-if scenarios</h3><TypeBadge kind="HYPOTHESIS" /></div>
          <p>Hypothetical arithmetic only. Every scenario output is HYPOTHETICAL.</p>
        </div>
      </div>
      <div className="p-5 grid gap-4 sm:grid-cols-2">
        <label className="form-label text-xs">Affected order count
          <input className="text-input mt-1" type="number" min={1} value={orderCount}
            onChange={(e) => setOrderCount(Number(e.target.value))} />
        </label>
        <label className="form-label text-xs">Calibrated delay probability (0–1)
          <input className="text-input mt-1" type="number" step={0.01} min={0} max={1} value={prob}
            onChange={(e) => setProb(Number(e.target.value))} />
        </label>
        <div className="sm:col-span-2">
          <button className="primary-button" disabled={busy} onClick={() => void run()}>
            {busy ? <><Spinner />Running…</> : 'Run what-if'}
          </button>
        </div>
      </div>
      {error && <div className="px-5 pb-5"><ErrBox msg={error} /></div>}
      {result && (
        <div className="px-5 pb-5 space-y-2">
          <div className="flex items-center gap-2"><TypeBadge kind="HYPOTHESIS" /><span className="text-xs font-semibold text-amber-800">HYPOTHETICAL — all scenario outputs are projections, not predictions</span></div>
          <pre className="json-block">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </section>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────────

export function RecommendationsScreen({ client, role }: { client: ApiClient; role: Role }) {
  const [recs, setRecs] = useState<Recommendation[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [actions, setActions] = useState<Action[]>([])
  const [outcomes, setOutcomes] = useState<Outcome[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [r, a, ac, o] = await Promise.all([
        client.recommendations(), client.approvals(), client.actions(), client.outcomes(),
      ])
      setRecs(r.items); setApprovals(a.items); setActions(ac.items); setOutcomes(o.items)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  return (
    <div className="space-y-7">
      <section className="page-intro">
        <div>
          <p className="eyebrow">WORKFLOW / RECOMMENDATIONS & ACTIONS</p>
          <h2>Recommendations and actions</h2>
          <p>All actions are DRY_RUN. No external action is executed by this console.</p>
        </div>
        <TypeBadge kind="RECOMMENDATION" />
      </section>

      {loading && <div className="loading-state py-16"><Spinner />Loading recommendations…</div>}
      {error && <ErrBox msg={error} />}

      {!loading && !error && recs.length === 0 && (
        <div className="empty-state">No recommendations stored for this scope.</div>
      )}

      {recs.map((rec) => (
        <div key={rec.id} className="panel p-5 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <TypeBadge kind="RECOMMENDATION" />
                {rec.human_approval_required && <span className="status-chip chip-warn">Approval required</span>}
              </div>
              <p className="font-semibold text-ink dark:text-white">{rec.action}</p>
              <p className="mt-1 text-sm text-muted">{rec.rationale}</p>
            </div>
            <button className="icon-button" aria-label="Refresh" onClick={() => void load()}><RefreshCw size={13} /></button>
          </div>

          {rec.assumptions?.length ? (
            <div className="text-xs text-muted space-y-1">
              {rec.assumptions.map((a) => <p key={a}>Assumption · {a}</p>)}
            </div>
          ) : null}
          {rec.uncertainty && <p className="text-xs text-muted">Uncertainty · {rec.uncertainty}</p>}
          {rec.constraints?.length ? (
            <div className="text-xs text-muted">{rec.constraints.map((c) => <p key={c}>Constraint · {c}</p>)}</div>
          ) : null}

          <div className="text-xs text-muted">
            Evidence refs: {rec.evidence_refs.join(', ') || 'UNKNOWN'} ·
            Source: {rec.source} ·
            Created: {rec.created_at ?? 'UNKNOWN'}
          </div>

          <ApprovalWidget
            rec={rec}
            approvals={approvals}
            actions={actions}
            outcomes={outcomes}
            role={role}
            client={client}
            onRefresh={() => void load()}
          />
        </div>
      ))}

      <WhatIfPanel client={client} role={role} />
    </div>
  )
}
