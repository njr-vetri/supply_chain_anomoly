import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Network } from 'lucide-react'
import { Background, Controls, ReactFlow, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { ApiClient } from '../api/client'
import type { FindingKind, GraphResponse, Incident } from '../api/types'
import { TypeBadge } from './TypeBadge'
import { graphElements } from './graphElements'

function TypedRecordNode({ id, data }: NodeProps) {
  const record = data as { category?: FindingKind; recordType?: string; source?: string }
  return <div className="flex flex-col gap-2"><TypeBadge kind={record.category || 'FACT'} /><strong className="break-all text-[11px]">{record.recordType || 'Record'}</strong><span className="break-all text-[10px] text-muted">{id}</span><span className="text-[10px] text-muted">Source: {record.source || 'UNKNOWN'}</span></div>
}
const nodeTypes = { typedRecord: TypedRecordNode }

export function DependencyGraph({ client, incidents }: { client: ApiClient; incidents: Incident[] }) {
  const [incidentId, setIncidentId] = useState(incidents[0]?.id || '')
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => { if (!incidentId) return; setLoading(true); setError(null); client.graph(incidentId).then(setGraph).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Could not load graph')).finally(() => setLoading(false)) }, [client, incidentId])
  const elements = useMemo(() => graph ? graphElements(graph) : { nodes: [], edges: [] }, [graph])
  return <div className="space-y-5"><section className="page-intro"><div><p className="eyebrow">INVESTIGATION / GRAPH</p><h2>Incident relationship graph</h2><p>Only relationships returned by the selected incident graph endpoint are displayed.</p></div><TypeBadge kind="FACT" /></section>
    <div className="panel p-5"><label className="form-label max-w-lg">Incident<select className="text-input mt-2" value={incidentId} onChange={(event) => setIncidentId(event.target.value)}><option value="">Select incident</option>{incidents.map((incident) => <option key={incident.id} value={incident.id}>{incident.title} · {incident.id}</option>)}</select></label>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-muted"><span className="flex items-center gap-2"><span className="edge-swatch" />ESTABLISHED</span><span className="flex items-center gap-2"><span className="edge-swatch inferred" />INFERRED</span><span>Edge labels include meaning and source reference.</span></div>
      {error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      {loading ? <div className="loading-state py-20">Loading incident graph…</div> : !incidentId ? <div className="empty-state"><Network size={20} /><p>Select an incident to inspect relationships.</p></div> : !graph?.nodes.length ? <div className="empty-state"><Network size={20} /><p>No graph nodes returned for this incident.</p></div> : <div className="graph-canvas mt-4"><ReactFlow nodes={elements.nodes} edges={elements.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.18 }} nodesDraggable={false} nodesConnectable={false} elementsSelectable><Background color="#dbe3f1" gap={20} /><Controls /></ReactFlow></div>}
      <div className="graph-warning mt-4"><AlertTriangle size={16} /><p>INFERRED paths are hypotheses, not confirmed causes. This API currently returns incident/evidence/hypothesis/recommendation nodes; it does not expose supplier/order dependency relationships.</p></div>
    </div>
  </div>
}
