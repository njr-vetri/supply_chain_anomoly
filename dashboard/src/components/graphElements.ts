import type { Edge, Node } from '@xyflow/react'
import type { FindingKind, GraphResponse } from '../api/types'

export function graphElements(graph: GraphResponse): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = graph.nodes.map((node, index) => ({
    id: String(node.id),
    position: { x: (index % 3) * 235, y: Math.floor(index / 3) * 125 },
    type: 'typedRecord',
    data: {
      category: node.type === 'HYPOTHESIS' ? 'HYPOTHESIS' : node.type === 'RECOMMENDATION' ? 'RECOMMENDATION' : node.type === 'PREDICTION' ? 'PREDICTION' : 'FACT' as FindingKind,
      recordType: String(node.type || 'RECORD'), source: String(node.source || 'UNKNOWN'),
    },
    style: { width: 200, border: '1px solid #dbe3f1', borderRadius: 12, padding: 12, color: '#263650', background: '#fff' },
  }))
  const edges: Edge[] = graph.edges.map((edge, index) => {
    const inferred = edge.status === 'INFERRED'
    const meaning = String(edge.meaning || 'Meaning not supplied')
    const status = String(edge.status || 'UNKNOWN')
    return {
      id: `${String(edge.from)}-${String(edge.to)}-${index}`,
      source: String(edge.from), target: String(edge.to), type: 'smoothstep',
      label: `${meaning} · ${status} · ref ${String(edge.source_ref || 'UNKNOWN')}`,
      data: { meaning, status, sourceRef: String(edge.source_ref || 'UNKNOWN'), edgeType: String(edge.type || 'UNKNOWN') },
      style: { stroke: inferred ? '#d58a19' : '#5573c9', strokeWidth: 2, ...(inferred ? { strokeDasharray: '6 4' } : {}) },
      labelStyle: { fill: inferred ? '#87560d' : '#394d78', fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: '#ffffff', fillOpacity: 0.95 },
    }
  })
  return { nodes, edges }
}
