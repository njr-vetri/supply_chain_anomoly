import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Activity, LoaderCircle, RefreshCw } from 'lucide-react'
import type { ApiClient } from '../api/client'
import type { EvalOutcomeResult, Outcome, Prediction } from '../api/types'
import { TypeBadge } from './TypeBadge'

function Spinner() { return <LoaderCircle size={16} className="animate-spin text-muted" /> }
function ErrBox({ msg, retry }: { msg: string; retry: () => void }) {
  return (
    <div className="ds-err" role="alert">
      <AlertTriangle size={15} /><span>{msg}</span>
      <button className="ml-2 underline text-xs font-semibold" onClick={retry}>Retry</button>
    </div>
  )
}

// ── Evaluation summary ─────────────────────────────────────────────────────────

function EvalSummary({ client }: { client: ApiClient }) {
  const [result, setResult] = useState<EvalOutcomeResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setResult(await client.evaluationOutcomes()) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load evaluation') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  const isInsufficient =
    result?.status === 'INSUFFICIENT_VERIFIED_OUTCOMES' ||
    result?.message === 'not enough verified outcomes'

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>Outcome evaluation</h3><TypeBadge kind="FACT" /></div>
          <p>Forecast-vs-actual, prediction-vs-outcome, and alert precision where verified labels exist.</p>
        </div>
        <button className="icon-button" aria-label="Refresh evaluation" onClick={() => void load()}><RefreshCw size={14} /></button>
      </div>

      {loading && <div className="loading-state py-8"><Spinner />Loading evaluation…</div>}
      {error && <div className="p-5"><ErrBox msg={error} retry={load} /></div>}

      {result && !loading && (
        <div className="p-5">
          {isInsufficient ? (
            <div className="insufficient-evidence-box">
              <span className="ie-label">Insufficient evidence</span>
              <p className="ie-text">{result.message ?? 'not enough verified outcomes'}</p>
              <p className="ie-hint">Outcome evaluation requires reviewer-verified labels linked to stored predictions or forecasts.</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[
                { label: 'Forecast MAE', val: result.forecast_mae },
                { label: 'Forecast MAPE', val: result.forecast_mape },
                { label: 'Prediction accuracy', val: result.prediction_accuracy },
                { label: 'Brier score', val: result.brier_score },
                { label: 'Alert precision', val: result.alert_precision },
                { label: 'Missed events', val: result.missed_events },
              ].map(({ label, val }) => (
                <div key={label} className="eval-metric-cell">
                  <p className="text-xs text-muted font-semibold uppercase tracking-wide">{label}</p>
                  <p className="text-xl font-semibold mt-1">{val != null ? String(val) : 'UNKNOWN'}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

// ── Predictions list ───────────────────────────────────────────────────────────

function PredictionsList({ client }: { client: ApiClient }) {
  const [items, setItems] = useState<Prediction[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setItems((await client.predictions()).items) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load predictions') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>Prediction records</h3><TypeBadge kind="PREDICTION" /></div>
          <p>All stored prediction records. Model output is distinct from observed facts.</p>
        </div>
        <button className="icon-button" aria-label="Refresh predictions" onClick={() => void load()}><RefreshCw size={14} /></button>
      </div>

      {loading && <div className="loading-state py-8"><Spinner />Loading predictions…</div>}
      {error && <div className="p-5"><ErrBox msg={error} retry={load} /></div>}
      {!loading && !error && (!items?.length) && (
        <div className="empty-state"><Activity size={20} /><p>No prediction records stored for this scope.</p></div>
      )}
      {items?.map((p) => (
        <article key={p.id} className="history-card">
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge kind="PREDICTION" />
            <strong className="text-sm">{p.target}: {String(p.value)}</strong>
            <span className="status-chip chip-queued">Model {p.model_version_id}</span>
          </div>
          <p className="mt-2 text-xs text-muted">
            Confidence: {p.confidence ?? 'UNKNOWN'} · Source: {p.source} · Records: {p.record_refs.join(', ') || 'UNKNOWN'}
          </p>
          <p className="mt-1 text-xs text-muted">Predicted: {p.predicted_at}</p>
          {p.limitations.length > 0 && (
            <p className="mt-1 text-xs text-muted">Limitations: {p.limitations.join('; ')}</p>
          )}
          <p className="mt-1 text-[10px] italic text-muted">model output, not observed fact</p>
        </article>
      ))}
    </section>
  )
}

// ── Forecasts (demand subset) ─────────────────────────────────────────────────

function ForecastsSection({ client }: { client: ApiClient }) {
  const [items, setItems] = useState<Prediction[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const all = (await client.predictions()).items
      setItems(all.filter((p) => /demand|forecast|quantity/i.test(p.target)))
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load forecasts') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>Demand forecasts</h3><TypeBadge kind="PREDICTION" /></div>
          <p>Subset of predictions with demand/quantity targets. Labelled "demand pressure" — not stockout status.</p>
        </div>
      </div>
      {loading && <div className="loading-state py-8"><Spinner />Loading forecasts…</div>}
      {error && <div className="p-5"><ErrBox msg={error} retry={load} /></div>}
      {!loading && !error && (!items?.length) && (
        <div className="empty-state"><p>No demand forecast predictions stored for this scope.</p></div>
      )}
      {items?.map((p) => (
        <article key={p.id} className="history-card">
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge kind="PREDICTION" />
            <strong className="text-sm">{p.target}: {String(p.value)}</strong>
          </div>
          <p className="mt-1 text-xs text-muted">Demand pressure indicator. Does not imply stockout status.</p>
          <p className="mt-1 text-xs text-muted">Model: {p.model_version_id} · Predicted: {p.predicted_at}</p>
        </article>
      ))}
    </section>
  )
}

// ── Outcomes (best-effort, no prediction_id in schema) ─────────────────────────

function OutcomesSection({ client }: { client: ApiClient }) {
  const [items, setItems] = useState<Outcome[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setItems((await client.outcomes()).items) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load outcomes') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>Observed outcomes</h3><TypeBadge kind="FACT" /></div>
          <p>Facts are kept separate from predictions.</p>
        </div>
      </div>
      {loading && <div className="loading-state py-8"><Spinner />Loading outcomes…</div>}
      {error && <div className="p-5"><ErrBox msg={error} retry={load} /></div>}
      {!loading && !error && (!items?.length) && (
        <div className="empty-state"><p>No observed outcomes stored for this scope.</p></div>
      )}
      {items?.map((o) => (
        <article key={o.id} className="history-card">
          <div className="flex items-center gap-2"><TypeBadge kind="FACT" /><strong className="text-sm">Observed outcome</strong></div>
          <p className="mt-1 text-xs text-muted">Action: {o.action_id} · Source: {o.source} · Observed: {o.observed_at}</p>
          <pre className="json-block mt-2">{JSON.stringify(o.facts, null, 2)}</pre>
        </article>
      ))}
      <div className="m-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
        <strong>Backend gap:</strong> The Outcome schema has no <code>prediction_id</code> field. Prediction-vs-outcome pairing is unavailable from the current API contract.
      </div>
    </section>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────────

export function PredictionsScreen({ client }: { client: ApiClient }) {
  return (
    <div className="space-y-7">
      <section className="page-intro">
        <div>
          <p className="eyebrow">ANALYTICS / PREDICTIONS & FORECASTS</p>
          <h2>Predictions and forecasts</h2>
          <p>Model outputs labelled as PREDICTION. Outcomes kept separate as FACT. Evaluation shows "Insufficient evidence" when verified labels are absent.</p>
        </div>
        <TypeBadge kind="PREDICTION" />
      </section>

      <EvalSummary client={client} />
      <PredictionsList client={client} />
      <ForecastsSection client={client} />
      <OutcomesSection client={client} />
    </div>
  )
}
