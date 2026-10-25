import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, LoaderCircle, LockKeyhole, Moon, RefreshCw, ShieldAlert, Sun } from 'lucide-react'
import type { ApiClient } from '../api/client'
import type { Action, Outcome, Role } from '../api/types'
import { delayEvaluation, evaluationLimitations, evaluationSource, reviewEvaluation } from '../data/evaluation'
import { TypeBadge } from './TypeBadge'

type JsonPage<T> = { items: T[]; count: number }
function useRemote<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(async () => { setLoading(true); setError(null); try { setData(await load()) } catch (err) { setError(err instanceof Error ? err.message : 'Request failed') } finally { setLoading(false) } }, [load])
  useEffect(() => { void reload() }, [reload])
  return { data, loading, error, reload }
}
function PageError({ message, retry }: { message: string; retry: () => void }) { return <div className="m-5 rounded-xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">{message}<button className="ml-3 font-semibold underline" onClick={retry}>Retry</button></div> }
function Busy() { return <div className="loading-state py-14"><LoaderCircle size={17} className="animate-spin" />Loading local records…</div> }
function Empty({ title, note }: { title: string; note: string }) { return <div className="empty-state"><p className="font-semibold">{title}</p><p>{note}</p></div> }
function text(value: unknown) { return value === undefined || value === null ? 'UNKNOWN' : typeof value === 'string' ? value : JSON.stringify(value) }

export function ActivityScreen({ client }: { client: ApiClient }) {
  const alertLoad = useCallback(() => client.alerts() as Promise<JsonPage<Record<string, unknown>>>, [client])
  const actionLoad = useCallback(() => client.actionHistory(), [client])
  const outcomeLoad = useCallback(() => client.outcomes(), [client])
  const predictionLoad = useCallback(() => client.predictions(), [client])
  const alerts = useRemote(alertLoad); const actions = useRemote(actionLoad); const outcomes = useRemote(outcomeLoad); const predictions = useRemote(predictionLoad)
  return <div className="space-y-5"><section className="page-intro"><div><p className="eyebrow">MONITORING / ACTIVITY</p><h2>Alerts & action history</h2><p>Persisted alert, action, prediction, and outcome records.</p></div><TypeBadge kind="FACT" /></section>
    <section className="panel"><div className="panel-heading"><div><h3>Alert history</h3><p>Alert-related audit history from the API</p></div><button className="icon-button" aria-label="Refresh alerts" onClick={() => void alerts.reload()}><RefreshCw size={15} /></button></div>
      {alerts.loading ? <Busy /> : alerts.error ? <PageError message={alerts.error} retry={() => void alerts.reload()} /> : !alerts.data?.items.length ? <Empty title="No alert history" note="No alert events are currently returned by the backend." /> : alerts.data.items.map((item, index) => <article className="history-card" key={String(item.id || index)}><div className="flex items-center gap-2"><TypeBadge kind="FACT" /><strong>{text(item.event_type || item.type)}</strong></div><p className="mt-1 text-xs text-muted">Source: {text(item.source)} · Time: {text(item.occurred_at || item.created_at)}</p><p className="mt-1 text-[10px] text-muted">Alert payload details are omitted in this view to minimize sensitive information.</p></article>)}
    </section>
    <section className="panel"><div className="panel-heading"><div><h3>Action history</h3><p>Dry-run records are labelled; execution is never inferred.</p></div><ShieldAlert size={18} className="text-muted" /></div>
      {actions.loading ? <Busy /> : actions.error ? <PageError message={actions.error} retry={() => void actions.reload()} /> : !actions.data?.items.length ? <Empty title="No action records" note="Action history is empty." /> : actions.data.items.map((item: Action) => <article className="history-card" key={item.id}><div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><TypeBadge kind="FACT" /><strong className="text-sm">{item.dry_run ? 'DRY_RUN' : 'Execution state UNKNOWN'} · {item.status}</strong></div><span className="status-chip">{item.dry_run ? 'Execution not performed' : 'Execution UNKNOWN'}</span></div><p className="mt-2 text-xs text-muted">Action {item.id} · recommendation {item.recommendation_id} · source {item.source}</p><p className="mt-1 text-[10px] text-muted">References: {item.record_refs?.join(', ') || 'UNKNOWN'} · Recorded: {item.created_at || 'UNKNOWN'}</p></article>)}
    </section>
    <section className="panel"><div className="panel-heading"><div><div className="flex items-center gap-2"><h3>Prediction records</h3><TypeBadge kind="PREDICTION" /></div><p>Displayed independently because outcomes do not identify a prediction reference.</p></div></div>
      {predictions.loading ? <Busy /> : predictions.error ? <PageError message={predictions.error} retry={() => void predictions.reload()} /> : !predictions.data?.items.length ? <Empty title="No prediction records" note="The API did not return stored predictions." /> : predictions.data.items.map((item) => <article className="history-card" key={item.id}><div className="flex flex-wrap items-center gap-2"><strong>{item.target}: {String(item.value)}</strong><span className="status-chip">Model {item.model_version_id}</span></div><p className="mt-2 text-xs text-muted">Source: {item.source} · Records: {item.record_refs.join(', ') || 'UNKNOWN'} · Predicted: {item.predicted_at}</p><p className="mt-1 text-[10px] text-muted">Limitations: {item.limitations.join('; ') || 'UNKNOWN'} · Confidence: {item.confidence ?? 'UNKNOWN'}</p></article>)}
    </section>
    <section className="panel"><div className="panel-heading"><div><h3>Observed outcomes</h3><p>Outcome facts are displayed separately from predictions</p></div><CheckCircle2 size={18} className="text-muted" /></div>
      {outcomes.loading || predictions.loading ? <Busy /> : outcomes.error ? <PageError message={outcomes.error} retry={() => void outcomes.reload()} /> : !outcomes.data?.items.length ? <Empty title="No observed outcomes" note="The backend has not returned any outcome records." /> : outcomes.data.items.map((outcome: Outcome) => <article className="history-card" key={outcome.id}><div className="flex items-center gap-2"><TypeBadge kind="FACT" /><strong>Observed outcome</strong></div><p className="mt-2 text-xs text-muted">Action: {outcome.action_id} · source: {outcome.source} · observed: {outcome.observed_at}</p><pre className="json-block mt-2">{JSON.stringify(outcome.facts, null, 2)}</pre><p className="mt-2 text-[10px] text-muted">Limitations: {outcome.limitations?.join('; ') || 'UNKNOWN'}</p></article>)}
      <div className="m-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">Predictions available: {predictions.data?.count ?? 'UNKNOWN'}. The API Outcome schema has no prediction reference or comparison field, so this console cannot pair a predicted value with an observed value without guessing.</div>
    </section>
  </div>
}

export function ModelsScreen({ client }: { client: ApiClient }) {
  const load = useCallback(() => client.models(), [client])
  const models = useRemote<JsonPage<Record<string, unknown>>>(load)
  const [tab, setTab] = useState<'delay' | 'reviews'>('delay')
  const rows = delayEvaluation.filter((row) => tab === 'delay' || row.dataset === 'olist')
  return <div className="space-y-5"><section className="page-intro"><div><p className="eyebrow">GOVERNANCE / MODELS</p><h2>Models & evaluation</h2><p>Stored versions from the local API and computed report snapshots.</p></div><TypeBadge kind="FACT" /></section>
    <div className="proxy-notice"><AlertTriangle size={17} /><div><strong>Proxy labels notice</strong><p>Olist review classes are score bands (1–2 complaint, 3 neutral, 4–5 positive), not human-verified sentiment or complaint annotations. They do not establish delay causes.</p></div></div>
    <section className="panel"><div className="panel-heading"><div><div className="flex items-center gap-2"><h3>Stored model versions</h3><TypeBadge kind="FACT" /></div><p>Data version is shown from each model's training_data_version reference.</p></div></div>
      {models.loading ? <Busy /> : models.error ? <PageError message={models.error} retry={() => void models.reload()} /> : !models.data?.items.length ? <Empty title="No model versions returned" note="Model versions are not persisted in the API repository currently." /> : models.data.items.map((item, index) => <article className="history-card" key={String(item.id || index)}><div className="flex flex-wrap items-center gap-2"><TypeBadge kind="FACT" /><strong>{text(item.name)} · {text(item.version)}</strong></div><p className="mt-2 text-xs text-muted">Model ref: {text(item.id)} · Trained: {text(item.trained_at)} · Data version: {text(item.training_data_version)}</p><p className="mt-1 break-all text-[10px] text-muted">Artifact SHA-256: {text(item.artifact_hash)}</p>{Array.isArray(item.limitations) && <p className="mt-2 text-xs text-muted">Limitations: {item.limitations.join('; ') || 'None returned'}</p>}</article>)}
    </section>
    <section className="panel"><div className="panel-heading"><div><h3>Evaluation report metrics</h3><p>Exact values copied from {evaluationSource}; snapshot is not recomputed in the browser.</p></div><span className="status-chip">Seed 42</span></div>
      <div className="flex gap-2 border-b border-line px-5 pt-4 dark:border-slate-800"><button className={`tab-button ${tab === 'delay' ? 'tab-active' : ''}`} onClick={() => setTab('delay')}>Delay classification</button><button className={`tab-button ${tab === 'reviews' ? 'tab-active' : ''}`} onClick={() => setTab('reviews')}>Review text</button></div>
      {tab === 'delay' ? <div className="table-scroll"><table className="metric-table"><thead><tr><th>Dataset</th><th>Model</th><th>Precision</th><th>Recall</th><th>F1</th><th>PR-AUC</th><th>ROC-AUC</th><th>Brier</th></tr></thead><tbody>{rows.map((item) => <tr key={`${item.dataset}-${item.model}`}><td>{item.dataset}</td><td>{item.model}</td><td>{String(item.precision)}</td><td>{String(item.recall)}</td><td>{String(item.f1)}</td><td>{String(item.pr_auc)}</td><td>{String(item.roc_auc)}</td><td>{String(item.brier)}</td></tr>)}</tbody></table></div> : <div className="table-scroll"><table className="metric-table"><thead><tr><th>Model</th><th>Macro precision</th><th>Macro recall</th><th>Macro F1</th><th>Accuracy</th></tr></thead><tbody>{reviewEvaluation.map((item) => <tr key={item.model}><td>{item.model}</td><td>{String(item.macro_precision)}</td><td>{String(item.macro_recall)}</td><td>{String(item.macro_f1)}</td><td>{String(item.accuracy)}</td></tr>)}</tbody></table></div>}
      <div className="grid gap-4 border-t border-line p-5 md:grid-cols-2 dark:border-slate-800"><div><p className="text-xs font-bold uppercase tracking-wider text-muted">Review split</p><p className="mt-2 text-xs leading-5 text-muted">BERT and TF-IDF used the shared chronological holdout documented in the report; test rows: 8,538. No significance test was computed.</p></div><div><p className="text-xs font-bold uppercase tracking-wider text-muted">Limitations</p>{evaluationLimitations.map((item) => <p className="mt-2 text-xs leading-5 text-muted" key={item}>• {item}</p>)}</div></div>
    </section>
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">Dataset versions have no list endpoint in the API contract. Model training-data references above are the only version links available here. Online Retail II forecasting remains uncomputed per the report.</div>
  </div>
}

export function AuditScreen({ client, role }: { client: ApiClient; role: Role }) {
  const load = useCallback(() => client.audit(), [client])
  const state = useRemote(load)
  return <div className="space-y-5"><section className="page-intro"><div><p className="eyebrow">GOVERNANCE / AUDIT</p><h2>Audit log</h2><p>Read-only view of the hash-chained audit events.</p></div><LockKeyhole size={19} className="text-muted" /></section>
    <div className="audit-notice">Audit details and record-reference payloads are intentionally omitted from this view to reduce PII exposure. The API requires an admin key; the backend remains authoritative.</div>
    {role !== 'admin' ? <div className="panel"><Empty title="Admin role required" note="The configured session role does not allow the audit endpoint." /></div> : state.loading ? <div className="panel"><Busy /></div> : state.error ? <div className="panel"><PageError message={state.error} retry={() => void state.reload()} /></div> : !state.data?.items.length ? <div className="panel"><Empty title="No audit events returned" note="The API audit log is empty or unavailable." /></div> : <section className="panel"><div className="table-scroll"><table className="metric-table"><thead><tr><th>Time</th><th>Event</th><th>Actor</th><th>Source</th><th>Previous hash</th><th>Event hash</th></tr></thead><tbody>{state.data.items.map((event, index) => <tr key={event.id || index}><td>{event.occurred_at}</td><td><TypeBadge kind="FACT" /> {event.event_type}</td><td>{event.actor}</td><td>{event.source || 'UNKNOWN'}</td><td className="hash-cell">{event.previous_hash}</td><td className="hash-cell">{event.event_hash}</td></tr>)}</tbody></table></div></section>}
  </div>
}

export function SettingsScreen({ client, role, apiUrl, onSaveUrl, dark, onToggleTheme, onKillSwitch }: { client: ApiClient; role: Role; apiUrl: string; onSaveUrl: (url: string) => void; dark: boolean; onToggleTheme: () => void; onKillSwitch: (enabled: boolean) => void }) {
  const [url, setUrl] = useState(apiUrl)
  const [kill, setKill] = useState<boolean | null>(null)
  const [loadingKill, setLoadingKill] = useState(role === 'admin')
  const [reason, setReason] = useState('')
  const [target, setTarget] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  useEffect(() => { if (role !== 'admin') { setKill(null); setLoadingKill(false); return } setLoadingKill(true); client.killSwitch().then((value) => setKill(value.enabled)).catch((err: unknown) => setMessage(err instanceof Error ? err.message : 'Could not read kill switch')).finally(() => setLoadingKill(false)) }, [client, role])
  async function applyToggle() {
    if (target === null || !reason.trim() || role !== 'admin') return
    setBusy(true); setMessage(null)
    try { const result = await client.toggleKillSwitch({ enabled: target, reason: reason.trim() }); setKill(result.enabled); onKillSwitch(result.enabled); setTarget(null); setReason(''); setMessage(`Kill switch is ${result.enabled ? 'ON' : 'OFF'}. Audit event recorded.`) }
    catch (err) { setMessage(err instanceof Error ? err.message : 'Kill-switch update failed') }
    finally { setBusy(false) }
  }
  return <div className="space-y-5"><section className="page-intro"><div><p className="eyebrow">SYSTEM / SETTINGS</p><h2>Console settings</h2><p>Local connection, appearance, and admin-controlled safety state.</p></div><TypeBadge kind="FACT" /></section>
    <section className="panel p-5"><h3 className="text-sm font-semibold">API connection</h3><p className="mt-1 text-xs text-muted">Only the local FastAPI backend is supported by this console.</p><div className="mt-4 flex flex-col gap-2 sm:flex-row"><input aria-label="API URL" className="text-input" value={url} onChange={(event) => setUrl(event.target.value)} /><button className="primary-button justify-center" disabled={!url.trim()} onClick={() => onSaveUrl(url.trim())}>Save URL</button></div><p className="mt-2 break-all text-[10px] text-muted">API root: {url}/api/v1</p></section>
    <section className="panel p-5"><div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-semibold">Appearance</h3><p className="mt-1 text-xs text-muted">Theme preference is stored in this browser session.</p></div><button className="secondary-button" onClick={onToggleTheme}>{dark ? <Sun size={15} /> : <Moon size={15} />}{dark ? 'Light theme' : 'Dark theme'}</button></div></section>
    <section className="panel p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><ShieldAlert size={17} className="text-amber-700" /><h3 className="text-sm font-semibold">Global kill switch</h3></div><p className="mt-2 max-w-2xl text-xs leading-5 text-muted">{role === 'admin' ? 'This setting is fetched from and written to the local API. Each change requires a reason and is audited.' : 'State is hidden because the API contract restricts kill-switch access to admin keys.'}</p></div><span className="status-chip">{loadingKill ? 'Loading…' : kill === null ? 'UNKNOWN' : kill ? 'ON' : 'OFF'}</span></div>
      {role === 'admin' && <button className={kill ? 'danger-button mt-4' : 'secondary-button mt-4'} disabled={loadingKill || kill === null} onClick={() => setTarget(!kill)}>{kill ? 'Turn kill switch OFF' : 'Turn kill switch ON'}</button>}
      {message && <p className="mt-3 text-xs text-muted" role="status">{message}</p>}
    </section>
    {target !== null && <div className="dialog-backdrop"><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="kill-dialog-title"><p className="eyebrow">ADMIN CONFIRMATION</p><h3 id="kill-dialog-title" className="mt-1 text-base font-semibold">Turn kill switch {target ? 'ON' : 'OFF'}?</h3><p className="mt-2 text-xs leading-5 text-muted">This changes the process-local API safety state and writes an audit event. Provide a reason to continue.</p><label className="form-label mt-4">Reason<input className="text-input mt-2" autoFocus value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Required reason" /></label><div className="mt-4 flex justify-end gap-2"><button className="secondary-button" disabled={busy} onClick={() => { setTarget(null); setReason('') }}>Cancel</button><button className="danger-button" disabled={!reason.trim() || busy} onClick={() => void applyToggle()}>{busy ? 'Saving…' : 'Confirm change'}</button></div></section></div>}
  </div>
}
