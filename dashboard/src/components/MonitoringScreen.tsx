import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Bell, LoaderCircle, RefreshCw, ShieldAlert } from 'lucide-react'
import type { ApiClient } from '../api/client'
import type { AlertHistoryItem, Anomaly, DriftResult, Role } from '../api/types'
import { TypeBadge } from './TypeBadge'

const roleRank: Record<Role, number> = { viewer: 1, analyst: 2, reviewer: 3, admin: 4 }
const can = (role: Role, min: Role) => roleRank[role] >= roleRank[min]

function Spinner() { return <LoaderCircle size={16} className="animate-spin text-muted" /> }
function ErrBox({ msg }: { msg: string }) {
  return (
    <div className="ds-err" role="alert">
      <AlertTriangle size={15} /><span>{msg}</span>
    </div>
  )
}

// ── Drift panel ────────────────────────────────────────────────────────────────

function DriftPanel({ client, role, datasetName }: { client: ApiClient; role: Role; datasetName: string }) {
  const [drift, setDrift] = useState<DriftResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setDrift(await client.datasetDrift(datasetName)) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load drift') }
    finally { setLoading(false) }
  }, [client, datasetName])

  useEffect(() => { void load() }, [load])

  if (!can(role, 'reviewer')) {
    return (
      <div className="ds-perm-denied">
        🔒 Reviewer role required to view drift results for {datasetName}.
      </div>
    )
  }

  return (
    <div className="panel p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-ink dark:text-white">{datasetName}</h4>
          <p className="text-xs text-muted">Drift vs. prior baseline</p>
        </div>
        <button className="icon-button" aria-label={`Refresh drift for ${datasetName}`}
          onClick={() => void load()}>
          <RefreshCw size={13} />
        </button>
      </div>

      {loading && <div className="ds-loading"><Spinner />Loading drift…</div>}
      {error && <ErrBox msg={error} />}

      {drift && (
        <>
          <div className="drift-schema">
            <p className="text-xs font-bold uppercase tracking-wider text-muted">Schema changes</p>
            <div className="mt-2 grid gap-2 text-xs sm:grid-cols-3">
              <div className="drift-schema-cell"><span className="text-emerald-700">Added ({drift.schema_changes.added.length})</span><p>{drift.schema_changes.added.join(', ') || 'none'}</p></div>
              <div className="drift-schema-cell"><span className="text-rose-700">Removed ({drift.schema_changes.removed.length})</span><p>{drift.schema_changes.removed.join(', ') || 'none'}</p></div>
              <div className="drift-schema-cell"><span className="text-amber-700">Retyped ({Object.keys(drift.schema_changes.retyped).length})</span>
                <p>{Object.entries(drift.schema_changes.retyped).map(([col, t]) => `${col}: ${t.from}→${t.to}`).join(', ') || 'none'}</p>
              </div>
            </div>
          </div>

          {Object.keys(drift.feature_drift).length > 0 && (
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-muted mb-2">Feature drift</p>
              <div className="table-scroll">
                <table className="metric-table">
                  <thead><tr><th>Feature</th><th>Mean shift</th><th>Std shift</th><th>Null rate Δ</th><th>Severity</th></tr></thead>
                  <tbody>
                    {Object.entries(drift.feature_drift).map(([feat, d]) => (
                      <tr key={feat}>
                        <td className="font-mono text-xs">{feat}</td>
                        <td>{d.mean_shift != null ? d.mean_shift.toFixed(4) : '—'}</td>
                        <td>{d.std_shift != null ? d.std_shift.toFixed(4) : '—'}</td>
                        <td>{d.null_rate_change != null ? d.null_rate_change.toFixed(4) : '—'}</td>
                        <td><span className={`status-chip ${d.severity === 'HIGH' ? 'chip-err' : d.severity === 'MEDIUM' ? 'chip-warn' : 'chip-ok'}`}>{d.severity}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="drift-warning-banner">
            <AlertTriangle size={14} />
            <span>{drift.warning}</span>
          </div>
        </>
      )}
    </div>
  )
}

// ── Anomalies section ──────────────────────────────────────────────────────────

function AnomaliesSection({ client }: { client: ApiClient }) {
  const [items, setItems] = useState<Anomaly[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setItems((await client.anomalies()).items) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load anomalies') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  const sorted = [...(items ?? [])].sort((a, b) => {
    const rank: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 }
    return (rank[b.severity ?? ''] ?? 0) - (rank[a.severity ?? ''] ?? 0)
  })

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>Anomalies</h3><TypeBadge kind="FACT" /></div>
          <p>Sorted by severity desc. Source record references and baselines shown as returned.</p>
        </div>
        <button className="icon-button" aria-label="Refresh anomalies" onClick={() => void load()}>
          <RefreshCw size={14} />
        </button>
      </div>

      {loading && <div className="loading-state py-10"><Spinner />Loading anomalies…</div>}
      {error && <div className="p-5"><ErrBox msg={error} /></div>}
      {!loading && !error && sorted.length === 0 && (
        <div className="empty-state"><ShieldAlert size={20} /><p>No anomalies stored for this scope.</p></div>
      )}
      {sorted.map((a) => (
        <div key={a.id} className="anomaly-card">
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge kind="FACT" />
            <span className={`status-chip ${a.severity === 'HIGH' ? 'chip-err' : a.severity === 'MEDIUM' ? 'chip-warn' : 'chip-ok'}`}>{a.severity ?? 'UNKNOWN'}</span>
            <span className="text-sm font-semibold text-ink dark:text-white">{a.feature}</span>
          </div>
          <div className="mt-2 grid gap-2 text-xs sm:grid-cols-3">
            <div><span className="text-muted">Observed</span><p className="font-mono">{JSON.stringify(a.observed_value)}</p></div>
            <div><span className="text-muted">Baseline</span><p className="font-mono">{JSON.stringify(a.baseline)}</p></div>
            <div><span className="text-muted">Detector</span><p>{a.detector}</p></div>
          </div>
          <p className="mt-1 text-xs text-muted">Source: {a.source} · Record: {a.record_ref}</p>
        </div>
      ))}
    </section>
  )
}

// ── Alert history section ──────────────────────────────────────────────────────

function AlertHistorySection({ client, role }: { client: ApiClient; role: Role }) {
  const [items, setItems] = useState<AlertHistoryItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ackBusy, setAckBusy] = useState<string | null>(null)
  const [ackReason, setAckReason] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setItems((await client.alertHistory()).items) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load alert history') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void load() }, [load])

  async function acknowledge(groupId: string) {
    const reason = ackReason[groupId]?.trim()
    if (!reason || !can(role, 'analyst')) return
    setAckBusy(groupId); setMsg(null)
    try {
      await client.acknowledgeAlert(groupId, reason)
      setMsg(`Alert ${groupId} acknowledged.`)
      await load()
    } catch (e) { setMsg(e instanceof Error ? e.message : 'Acknowledge failed') }
    finally { setAckBusy(null) }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <div className="flex items-center gap-2"><h3>Alert history</h3><TypeBadge kind="FACT" /></div>
          <p>Acknowledgement and assignment require analyst or higher.</p>
        </div>
        <button className="icon-button" aria-label="Refresh alerts" onClick={() => void load()}><RefreshCw size={14} /></button>
      </div>

      {loading && <div className="loading-state py-10"><Spinner />Loading alert history…</div>}
      {error && <div className="p-5"><ErrBox msg={error} /></div>}
      {!loading && !error && (!items?.length) && (
        <div className="empty-state"><Bell size={20} /><p>No alert history returned by the backend.</p></div>
      )}
      {items?.map((item, i) => {
        const gid = String(item.group_id ?? item.event_type ?? i)
        return (
          <div key={gid} className="history-card">
            <div className="flex flex-wrap items-center gap-2">
              <TypeBadge kind="FACT" />
              <strong>{String(item.event_type ?? item.type ?? 'Alert event')}</strong>
              {item.acknowledged && <span className="status-chip chip-ok">Acknowledged</span>}
              {item.assigned_to && <span className="status-chip chip-queued">→ {String(item.assigned_to)}</span>}
            </div>
            <p className="mt-1 text-xs text-muted">Source: {String(item.source ?? 'UNKNOWN')} · Time: {String(item.occurred_at ?? item.created_at ?? 'UNKNOWN')}</p>
            {!item.acknowledged && can(role, 'analyst') && item.group_id && (
              <div className="flex gap-2 mt-2 flex-wrap">
                <input className="text-input flex-1 min-w-40 text-xs" value={ackReason[gid] ?? ''}
                  aria-label={`Acknowledge reason ${gid}`}
                  onChange={(e) => setAckReason((prev) => ({ ...prev, [gid]: e.target.value }))}
                  placeholder="Reason to acknowledge" />
                <button className="primary-button text-xs" disabled={!ackReason[gid]?.trim() || ackBusy === gid}
                  onClick={() => void acknowledge(gid)}>
                  {ackBusy === gid ? <Spinner /> : 'Acknowledge'}
                </button>
              </div>
            )}
          </div>
        )
      })}
      {msg && <p className="m-4 text-xs" role="status">{msg}</p>}
    </section>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────────

export function MonitoringScreen({ client, role, knownSources }: {
  client: ApiClient; role: Role; knownSources: string[]
}) {
  return (
    <div className="space-y-7">
      <section className="page-intro">
        <div>
          <p className="eyebrow">MONITORING / DRIFT & ANOMALIES</p>
          <h2>Monitoring and anomalies</h2>
          <p>Schema/feature drift (reviewer only), detected anomalies and alert history.</p>
        </div>
        <TypeBadge kind="FACT" />
      </section>

      {/* Drift per known source */}
      <section>
        <h3 className="section-heading">Data drift — per source</h3>
        {knownSources.length === 0 ? (
          <div className="ds-empty">
            No data sources found. Upload a dataset first to see drift analysis.
            {!can(role, 'reviewer') && ' Reviewer role required to view drift.'}
          </div>
        ) : (
          <div className="space-y-4">
            {knownSources.map((name) => (
              <DriftPanel key={name} client={client} role={role} datasetName={name} />
            ))}
          </div>
        )}
      </section>

      <AnomaliesSection client={client} />
      <AlertHistorySection client={client} role={role} />
    </div>
  )
}
