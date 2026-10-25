import { useCallback, useEffect, useState } from 'react'
import { Check, CircleHelp, FilePlus2, LoaderCircle, RefreshCw } from 'lucide-react'
import type { ApiClient } from '../api/client'
import type { Action, Approval, Hypothesis, HypothesisStatus, Incident, Page, Recommendation, Role } from '../api/types'
import { HypothesisActions } from './HypothesisActions'
import { TypeBadge } from './TypeBadge'

function useRemote<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(async () => {
    setLoading(true); setError(null)
    try { setData(await load()) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Request failed') }
    finally { setLoading(false) }
  }, [load])
  useEffect(() => { void reload() }, [reload])
  return { data, setData, loading, error, reload }
}

const roleRank: Record<Role, number> = { viewer: 1, analyst: 2, reviewer: 3, admin: 4 }
function can(role: Role, minimum: Role) { return roleRank[role] >= roleRank[minimum] }
function provenance(source?: string, refs?: string[], timestamp?: string) {
  return <div className="mt-2 text-[10px] text-muted dark:text-slate-400">Source: {source || 'UNKNOWN'} · Records: {refs?.join(', ') || 'UNKNOWN'} · Time: {timestamp || 'UNKNOWN'} · Limitations: see linked record</div>
}
function PageError({ message, retry }: { message: string; retry: () => void }) { return <div className="m-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><p>{message}</p><button className="mt-2 font-semibold underline" onClick={retry}>Retry</button></div> }
function Busy() { return <div className="loading-state py-16"><LoaderCircle size={17} className="animate-spin" />Loading local records…</div> }
function NoRecords({ title, note }: { title: string; note: string }) { return <div className="empty-state"><CircleHelp size={19} /><h3>{title}</h3><p>{note}</p></div> }

const reviewStatuses: HypothesisStatus[] = ['SUPPORTED', 'REJECTED', 'CLOSED']
export function HypothesisLedgerScreen({ client, role, incidents }: { client: ApiClient; role: Role; incidents: Incident[] }) {
  const load = useCallback(() => client.hypotheses(), [client])
  const state = useRemote<Page<Hypothesis>>(load)
  const [incidentId, setIncidentId] = useState('')
  const [statement, setStatement] = useState('')
  const [source, setSource] = useState('')
  const [recordRefs, setRecordRefs] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [reason, setReason] = useState<Record<string, string>>({})
  const [reviewStatus, setReviewStatus] = useState<Record<string, HypothesisStatus>>({})
  const [message, setMessage] = useState<string | null>(null)
  const items = state.data?.items || []

  async function createHypothesis() {
    if (!incidentId || !statement.trim() || !source.trim() || !can(role, 'analyst')) return
    setBusy('create'); setMessage(null)
    try {
      await client.createHypothesis({ incident_id: incidentId, statement: statement.trim(), source: source.trim(), record_refs: recordRefs.split(',').map((ref) => ref.trim()).filter(Boolean) })
      setStatement(''); setSource(''); setRecordRefs(''); await state.reload(); setMessage('Hypothesis created as UNVERIFIED.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Hypothesis creation failed') }
    finally { setBusy(null) }
  }
  async function review(item: Hypothesis) {
    const rationale = reason[item.id]?.trim(); const next = reviewStatus[item.id]
    if (!rationale || !next || next === 'CONFIRMED') return
    setBusy(item.id); setMessage(null)
    try { await client.reviewHypothesis(item.id, { status: next, rationale }); await state.reload(); setMessage(`Review recorded: ${next}.`) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Review failed') }
    finally { setBusy(null) }
  }
  async function confirm(item: Hypothesis) {
    const rationale = reason[item.id]?.trim()
    if (!rationale || role !== 'reviewer') return
    setBusy(item.id); setMessage(null)
    try { await client.confirmHypothesis(item.id, rationale); await state.reload(); setMessage('Reviewer confirmation recorded.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Confirmation failed') }
    finally { setBusy(null) }
  }

  return <div className="space-y-5"><section className="page-intro"><div><p className="eyebrow">INVESTIGATION / HYPOTHESES</p><h2>Hypothesis ledger</h2><p>Lifecycle transitions keep evidence and human review visible.</p></div><TypeBadge kind="HYPOTHESIS" /></section>
    <section className="panel"><div className="panel-heading"><div><h3>Create a hypothesis</h3><p>New records enter as UNVERIFIED; creation does not establish a cause.</p></div><FilePlus2 size={18} className="text-muted" /></div><div className="grid gap-3 p-5 md:grid-cols-2">
      <label className="form-label">Incident<select className="text-input mt-2" value={incidentId} onChange={(event) => setIncidentId(event.target.value)}><option value="">Select incident</option>{incidents.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.id}</option>)}</select></label>
      <label className="form-label">Source<input className="text-input mt-2" value={source} onChange={(event) => setSource(event.target.value)} placeholder="Source identifier" /></label>
      <label className="form-label md:col-span-2">Hypothesis statement<textarea className="text-input mt-2 min-h-20" value={statement} onChange={(event) => setStatement(event.target.value)} placeholder="State a testable proposition, not an established cause." /></label>
      <label className="form-label md:col-span-2">Source record references<input className="text-input mt-2" value={recordRefs} onChange={(event) => setRecordRefs(event.target.value)} placeholder="Comma-separated record IDs (optional)" /></label>
      {!can(role, 'analyst') && <p className="text-xs text-amber-800 md:col-span-2">Analyst role is required to create a hypothesis.</p>}
      <div className="flex items-center gap-3 md:col-span-2"><button className="primary-button" disabled={!can(role, 'analyst') || !incidentId || !statement.trim() || !source.trim() || busy === 'create'} onClick={() => void createHypothesis()}>{busy === 'create' ? 'Saving…' : 'Create UNVERIFIED hypothesis'}</button>{message && <span role="status" className="text-xs text-muted">{message}</span>}</div>
    </div></section>
    <section className="panel"><div className="panel-heading"><div><h3>Evidence ledger</h3><p>Statuses and review history returned by the API</p></div><button className="icon-button" aria-label="Refresh hypotheses" onClick={() => void state.reload()}><RefreshCw size={15} /></button></div>
      {state.loading ? <Busy /> : state.error ? <PageError message={state.error} retry={() => void state.reload()} /> : !items.length ? <NoRecords title="No hypotheses stored" note="Create a hypothesis from an incident above when evidence warrants review." /> : items.map((item) => <article className="hypothesis-card" key={item.id}>
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start"><div className="min-w-0"><div className="flex items-center gap-2"><TypeBadge kind="HYPOTHESIS" /><span className="text-[10px] font-semibold text-muted">{item.id}</span></div><p className="mt-2 text-sm font-semibold text-ink dark:text-white">{item.statement}</p>{provenance(item.source, item.record_refs, item.created_at)}</div><span className="status-chip">{item.status}</span></div>
        {item.review_history?.length ? <div className="mt-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-900"><p className="text-[10px] font-bold uppercase tracking-widest text-muted">Review history</p>{item.review_history.map((entry) => <p className="mt-2 text-xs text-slate-600 dark:text-slate-300" key={`${entry.reviewer_id}-${entry.reviewed_at}`}>{entry.previous_status} → {entry.new_status} · {entry.reviewer_id} · {entry.reviewed_at} · {entry.rationale}</p>)}</div> : <p className="mt-3 text-xs text-muted">No review entries returned.</p>}
        {item.status !== 'CONFIRMED' && <div className="mt-4 grid gap-2 md:grid-cols-[1fr_auto_auto]"><input className="text-input" aria-label={`Reason for ${item.id}`} value={reason[item.id] || ''} onChange={(event) => setReason({ ...reason, [item.id]: event.target.value })} placeholder="Required review / confirmation reason" /><select className="text-input" aria-label={`Review status ${item.id}`} value={reviewStatus[item.id] || ''} onChange={(event) => setReviewStatus({ ...reviewStatus, [item.id]: event.target.value as HypothesisStatus })}><option value="">Choose review outcome</option>{reviewStatuses.map((s) => <option key={s} value={s}>{s}</option>)}</select><button className="secondary-button" disabled={!can(role, 'analyst') || !reason[item.id]?.trim() || !reviewStatus[item.id] || busy === item.id} onClick={() => void review(item)}>{busy === item.id ? 'Saving…' : 'Record review'}</button>
          <div className="md:col-span-3 flex items-center gap-3"><HypothesisActions status={item.status} role={role} disabled={!reason[item.id]?.trim() || busy === item.id} onConfirm={() => void confirm(item)} /><span className="text-[10px] text-muted">Only the backend-verified reviewer key can confirm.</span></div>
        </div>}
      </article>)}
    </section>
  </div>
}

export function ApprovalQueueScreen({ client, role }: { client: ApiClient; role: Role }) {
  const loadApprovals = useCallback(() => client.approvals(), [client])
  const loadRecommendations = useCallback(() => client.recommendations(), [client])
  const loadActions = useCallback(() => client.actions(), [client])
  const approvals = useRemote<Page<Approval>>(loadApprovals)
  const recommendations = useRemote<Page<Recommendation>>(loadRecommendations)
  const actions = useRemote<Page<Action>>(loadActions)
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const items = recommendations.data?.items || []
  const queue = approvals.data?.items || []
  const recordedActions = actions.data?.items || []
  const pendingRecommendationIds = new Set(queue.filter((approval) => approval.status === 'pending').map((approval) => approval.recommendation_id))
  async function createApproval(id: string) {
    setBusy(id); setMessage(null)
    try { await client.createApproval({ recommendation_id: id }); await approvals.reload(); setMessage('Pending approval request recorded.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Approval request failed') }
    finally { setBusy(null) }
  }
  async function decide(item: Approval, decision: 'approve' | 'reject') {
    const rationale = reasons[item.id]?.trim()
    if (!rationale || (role !== 'reviewer' && role !== 'admin')) return
    setBusy(item.id); setMessage(null)
    try {
      if (decision === 'approve') await client.approve(item.id, { rationale })
      else await client.reject(item.id, { rationale })
      await approvals.reload(); setMessage(`Approval ${decision} recorded.`)
    } catch (error) { setMessage(error instanceof Error ? error.message : `Could not ${decision}`) }
    finally { setBusy(null) }
  }
  async function recordDryRun(id: string) {
    setBusy(id); setMessage(null)
    try { await client.createAction({ recommendation_id: id, action_class: 'READ_ONLY' }); await actions.reload(); setMessage('Action recorded as DRY_RUN; it was not executed.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Dry-run record failed') }
    finally { setBusy(null) }
  }

  return <div className="space-y-5"><section className="page-intro"><div><p className="eyebrow">RESPONSE / APPROVALS</p><h2>Recommendations & approvals</h2><p>Every request remains reviewable; action records are always displayed as dry-run.</p></div><TypeBadge kind="RECOMMENDATION" /></section>
    {message && <p className="rounded-lg bg-sky-50 p-3 text-xs text-sky-900 dark:bg-sky-950 dark:text-sky-100" role="status">{message}</p>}
    <section className="panel"><div className="panel-heading"><div><h3>Pending approvals queue</h3><p>Reviewer decision and rationale are required</p></div><span className="status-chip">{queue.filter((item) => item.status === 'pending').length} pending</span></div>
      {approvals.loading ? <Busy /> : approvals.error ? <PageError message={approvals.error} retry={() => void approvals.reload()} /> : !queue.length ? <NoRecords title="No approval records" note="Pending approvals will appear when an analyst requests review." /> : queue.map((item) => { const linked = items.find((recommendation) => recommendation.id === item.recommendation_id); return <article className="hypothesis-card" key={item.id}><div className="flex flex-wrap items-center justify-between gap-2"><div><div className="flex items-center gap-2"><TypeBadge kind="FACT" /><strong className="text-xs text-ink dark:text-white">Approval · {item.id}</strong></div><p className="mt-1 text-xs text-muted">Recommendation ref: {item.recommendation_id} · {linked?.action || 'Recommendation text unavailable'} · Status: {item.status} · Time: {item.reviewed_at}</p></div><span className="status-chip">{item.status}</span></div>
        {item.status === 'pending' && <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto_auto]"><input className="text-input" aria-label={`Approval reason ${item.id}`} value={reasons[item.id] || ''} onChange={(event) => setReasons({ ...reasons, [item.id]: event.target.value })} placeholder="Required reviewer reason" /><button className="secondary-button" disabled={!can(role, 'reviewer') || !reasons[item.id]?.trim() || busy === item.id} onClick={() => void decide(item, 'approve')}>{busy === item.id ? 'Saving…' : 'Approve'}</button><button className="danger-button" disabled={!can(role, 'reviewer') || !reasons[item.id]?.trim() || busy === item.id} onClick={() => void decide(item, 'reject')}>Reject</button></div>}
        {item.rationale && <p className="mt-2 text-xs text-muted">Reason: {item.rationale} · Reviewer: {item.reviewer_id || 'UNKNOWN'}</p>}
        {!can(role, 'reviewer') && item.status === 'pending' && <p className="mt-2 text-xs text-amber-800">Reviewer role is required to approve or reject.</p>}
      </article> })}
    </section>
    <section className="panel"><div className="panel-heading"><div><h3>Recommendations</h3><p>Rationale and provenance from stored records</p></div></div>
      {recommendations.loading ? <Busy /> : recommendations.error ? <PageError message={recommendations.error} retry={() => void recommendations.reload()} /> : !items.length ? <NoRecords title="No recommendations stored" note="Recommendations appear after a local pipeline run persists them." /> : items.map((item) => <article className="recommendation-card" key={item.id}><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2"><TypeBadge kind="RECOMMENDATION" /><strong className="text-sm text-ink dark:text-white">{item.action}</strong></div><p className="mt-2 text-xs leading-5 text-muted dark:text-slate-300">{item.rationale}</p>{provenance(item.source, item.record_refs, item.created_at)}</div><span className="status-chip">Human approval required</span></div>
        <div className="mt-3 space-y-1 text-[11px] text-muted">Evidence refs: {item.evidence_refs?.join(', ') || 'UNKNOWN'}{item.assumptions?.map((assumption) => <p key={assumption}>Assumption: {assumption}</p>)}{item.uncertainty && <p>Uncertainty: {item.uncertainty}</p>}{item.constraints?.map((constraint) => <p key={constraint}>Constraint: {constraint}</p>)}</div>
        <div className="mt-3 flex flex-wrap gap-2"><button className="secondary-button" disabled={!can(role, 'analyst') || busy === item.id || pendingRecommendationIds.has(item.id)} onClick={() => void createApproval(item.id)}>{pendingRecommendationIds.has(item.id) ? 'Approval pending' : busy === item.id ? 'Saving…' : 'Request approval'}</button><button className="secondary-button" disabled={!can(role, 'analyst') || busy === item.id} onClick={() => void recordDryRun(item.id)}><Check size={14} />Record action DRY_RUN</button><TypeBadge kind="FACT" /></div>
        {recordedActions.filter((action) => action.recommendation_id === item.id).map((action) => <p className="mt-2 rounded-lg bg-amber-50 p-2 text-xs font-semibold text-amber-900 dark:bg-amber-950 dark:text-amber-100" key={action.id}>{action.dry_run ? 'DRY_RUN · execution not performed' : 'Execution state UNKNOWN'} · status {action.status}</p>)}
      </article>)}
    </section>
    <p className="text-xs text-muted">All actions displayed here are recorded as DRY_RUN. The API contract does not provide an executed-action flow for this interface.</p>
  </div>
}
