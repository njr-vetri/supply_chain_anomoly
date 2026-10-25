import { useCallback, useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import fcose from 'cytoscape-fcose'
import {
  AlertTriangle,
  LoaderCircle,
  Search,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Play,
  Pause,
  RotateCcw,
  Network,
  Layers,
  ArrowRight,
  Info,
  ShieldAlert,
} from 'lucide-react'
import type { ApiClient } from '../api/client'
import type {
  AggregatedGraphNode,
  AggregatedGraphResponse,
  CandidateSource,
  HealthStatus,
  PeerMetricBaseline,
} from '../api/types'
import { TypeBadge } from './TypeBadge'

// ── Register cytoscape layout extensions ─────────────────────────────────────
try {
  cytoscape.use(dagre)
  cytoscape.use(fcose)
} catch {
  // Cytoscape throws if layout is already registered
}

// ── Health coloring constants ────────────────────────────────────────────────
const HEALTH_COLOR: Record<HealthStatus, string> = {
  HEALTHY: '#22c55e',
  WATCH: '#f59e0b',
  PROBLEM: '#ef4444',
  AT_RISK: '#f59e0b',
  INCIDENT: '#ef4444',
  UNKNOWN: '#94a3b8',
}

function healthColor(h?: string | null): string {
  if (!h) return HEALTH_COLOR.UNKNOWN
  return HEALTH_COLOR[h as HealthStatus] ?? HEALTH_COLOR.UNKNOWN
}

// Exposure size mapping: min 26px, max 68px
function nodeSize(exposure?: number | null): number {
  if (exposure == null || exposure <= 0) return 28
  return Math.min(68, Math.max(26, 26 + Math.sqrt(exposure) * 4))
}

// Edge style by kind
function edgeStyle(flag?: string | null): { lineStyle: 'solid' | 'dashed' | 'dotted'; width: number } {
  if (flag === 'ESTABLISHED') return { lineStyle: 'solid', width: 2 }
  if (flag === 'USER_ENTERED') return { lineStyle: 'dotted', width: 1.5 }
  return { lineStyle: 'dashed', width: 1.5 } // INFERRED default
}

// ── Side panel ───────────────────────────────────────────────────────────────

function SidePanel({
  node,
  onClose,
  onTraceUp,
  onTraceDown,
  onClearTrace,
  isTraced,
  busy,
  traceDisclaimer,
}: {
  node: AggregatedGraphNode
  onClose: () => void
  onTraceUp: () => void
  onTraceDown: () => void
  onClearTrace: () => void
  isTraced: boolean
  busy: boolean
  traceDisclaimer?: string | null
}) {
  const baselines = node.metrics_vs_peer_baseline ? Object.entries(node.metrics_vs_peer_baseline) : []

  return (
    <div className="graph-side-panel" data-testid="graph-side-panel">
      <div className="graph-panel-header">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted">{node.type}</p>
          <h4 className="text-sm font-semibold text-ink dark:text-white break-all">{node.label || node.id}</h4>
          <span className="text-[10px] text-muted font-mono">{node.id}</span>
        </div>
        <button className="icon-button" aria-label="Close side panel" onClick={onClose}>
          <X size={15} />
        </button>
      </div>

      <div className="graph-panel-body space-y-4">
        {/* Health & Status Badges */}
        <div className="flex flex-wrap gap-2 items-center">
          <TypeBadge kind="FACT" />
          <span
            className={`status-chip ${node.health === 'PROBLEM' ? 'pulse-problem-ring' : ''}`}
            style={{ background: healthColor(node.health), color: '#fff' }}
          >
            {node.health}
          </span>
          {node.candidate_source_rank != null && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300">
              Rank #{node.candidate_source_rank} Candidate
            </span>
          )}
        </div>

        {node.health_reason && (
          <p className="text-xs text-muted italic bg-slate-50 dark:bg-slate-900 p-2 rounded border border-line">
            {node.health_reason}
          </p>
        )}

        {/* Metrics Overview */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="eval-metric-cell">
            <p className="text-muted">Exposure Volume</p>
            <p className="font-semibold text-ink dark:text-white">{Number(node.exposure).toLocaleString()}</p>
          </div>
          <div className="eval-metric-cell">
            <p className="text-muted">Anomalies Detected</p>
            <p className={`font-semibold ${node.anomaly_count > 0 ? 'text-red-600' : 'text-ink dark:text-white'}`}>
              {node.anomaly_count}
            </p>
          </div>
        </div>

        {/* Peer Baselines */}
        {baselines.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
                Peer Baseline Comparisons
              </span>
              <span className="text-[10px] text-muted">vs group mean</span>
            </div>
            <div className="space-y-2">
              {baselines.map(([k, metric]: [string, PeerMetricBaseline]) => {
                const isHighZ = Math.abs(metric.z_score) >= 2.0
                return (
                  <div key={k} className="peer-baseline-card">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-ink dark:text-slate-200 capitalize">
                        {k.replace(/_/g, ' ')}
                      </span>
                      <span
                        className={`peer-zscore-badge ${isHighZ ? 'peer-zscore-high' : 'peer-zscore-norm'}`}
                      >
                        z = {metric.z_score > 0 ? `+${metric.z_score.toFixed(1)}` : metric.z_score.toFixed(1)}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-1 text-[10px] text-muted">
                      <div>Node value: <strong className="text-ink dark:text-white">{metric.node_value.toFixed(1)}</strong></div>
                      <div>Peer mean: {metric.peer_mean.toFixed(1)} (±{metric.peer_std.toFixed(1)})</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Trace Actions */}
        <div className="space-y-2 pt-2 border-t border-line">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Exposure Tracing</p>
          <div className="flex flex-col gap-2">
            <button
              className="btn-secondary w-full justify-center"
              onClick={onTraceDown}
              disabled={busy}
              aria-label="Trace downstream affected nodes"
            >
              {busy ? <LoaderCircle size={13} className="animate-spin" /> : <ArrowRight size={13} />}
              <span>Trace Downstream Exposure</span>
            </button>
            <button
              className="btn-secondary w-full justify-center"
              onClick={onTraceUp}
              disabled={busy}
              aria-label="Trace upstream candidate sources"
            >
              {busy ? <LoaderCircle size={13} className="animate-spin" /> : <RotateCcw size={13} />}
              <span>Trace Upstream Sources</span>
            </button>
            {isTraced && (
              <button
                className="text-xs text-muted hover:text-ink underline text-center pt-1"
                onClick={onClearTrace}
              >
                Clear path highlights
              </button>
            )}
          </div>
          {traceDisclaimer && (
            <div className="p-2 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded text-[10px] text-amber-800 dark:text-amber-300">
              <div className="flex items-start gap-1.5">
                <ShieldAlert size={13} className="flex-shrink-0 mt-0.5 text-amber-600" />
                <span>{traceDisclaimer}</span>
              </div>
            </div>
          )}
        </div>

        {/* Evidence Refs */}
        {node.evidence_refs && node.evidence_refs.length > 0 && (
          <div className="pt-2 border-t border-line">
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted mb-1.5">Evidence Provenance</p>
            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
              {node.evidence_refs.map((ref) => (
                <span
                  key={ref}
                  className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-[10px] text-muted font-mono"
                >
                  {ref}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Persistent Legend Component ──────────────────────────────────────────────

export function GraphLegend() {
  return (
    <div className="graph-legend" data-testid="graph-legend">
      <span className="font-semibold text-muted mr-1">HEALTH:</span>
      <span className="legend-item">
        <span className="legend-dot" style={{ background: HEALTH_COLOR.HEALTHY }} />
        Healthy
      </span>
      <span className="legend-item">
        <span className="legend-dot" style={{ background: HEALTH_COLOR.WATCH }} />
        Watch
      </span>
      <span className="legend-item">
        <span className="legend-dot" style={{ background: HEALTH_COLOR.PROBLEM, border: '2px solid #ef4444' }} />
        Problem (Pulsing)
      </span>
      <span className="legend-item">
        <span className="legend-dot" style={{ background: HEALTH_COLOR.UNKNOWN }} />
        Unknown
      </span>

      <span className="font-semibold text-muted ml-3 mr-1">EDGES:</span>
      <span className="legend-item" title="Established from confirmed foreign key links">
        <span className="edge-swatch" />
        Established (Solid)
      </span>
      <span className="legend-item" title="Inferred statistical or temporal connection">
        <span className="edge-swatch inferred" />
        Inferred (Dashed)
      </span>
      <span className="legend-item" title="Manually entered domain rule">
        <span className="edge-swatch dotted" />
        User Entered (Dotted)
      </span>

      <span className="font-semibold text-muted ml-3 mr-1">NODE SIZE:</span>
      <span className="legend-item text-muted">Proportional to Exposure Volume</span>
    </div>
  )
}

// ── Main SupplyGraphScreen Component ─────────────────────────────────────────

export function SupplyGraphScreen({
  client,
  projectId,
  incidentId,
}: {
  client: ApiClient
  projectId: string
  incidentId?: string
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const traceExposureRef = useRef<(direction: 'upstream' | 'downstream', startNodeId?: string) => Promise<void>>(() => Promise.resolve())

  const [graphData, setGraphData] = useState<AggregatedGraphResponse | null>(null)
  const [selectedNode, setSelectedNode] = useState<AggregatedGraphNode | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Layout view toggle: 'network' (fcose / cose) vs 'process' (dagre left-to-right)
  const [viewMode, setViewMode] = useState<'network' | 'process'>('network')

  // Traced elements
  const [tracedNodeIds, setTracedNodeIds] = useState<Set<string>>(new Set())
  const [traceDisclaimer, setTraceDisclaimer] = useState<string | null>(null)

  // Time Slider
  const [timeBucketIdx, setTimeBucketIdx] = useState<number | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const playTimerRef = useRef<number | null>(null)

  // Filters
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('ALL')
  const [healthFilter, setHealthFilter] = useState('ALL')

  // Available node types in current graph
  const nodeTypes = Array.from(new Set(graphData?.nodes.map((n) => n.type) ?? []))

  // ── Build Cytoscape Elements ───────────────────────────────────────────────
  const buildElements = useCallback(
    (data: AggregatedGraphResponse, currentBucketIdx: number | null, tracedSet: Set<string>) => {
      const currentBucket = currentBucketIdx != null && data.time_buckets[currentBucketIdx]
        ? data.time_buckets[currentBucketIdx]
        : null

      const nodes = data.nodes.map((node) => {
        let currentHealth = node.health
        if (currentBucket && node.time_series) {
          const snapshot = node.time_series.find((s) => s.bucket === currentBucket)
          if (snapshot) currentHealth = snapshot.health
        }

        const isProblem = currentHealth === 'PROBLEM'
        const isTraced = tracedSet.has(node.id)

        return {
          data: {
            id: node.id,
            label: node.label || node.id,
            type: node.type,
            health: currentHealth,
            exposure: node.exposure,
            anomaly_count: node.anomaly_count,
            health_color: healthColor(currentHealth),
            size: nodeSize(node.exposure),
            is_problem: isProblem,
            is_traced: isTraced,
            candidate_rank: node.candidate_source_rank ?? 0,
            culprit: node.culprit ?? false,
            affected: node.affected ?? false,
          },
        }
      })

      const edges = data.edges.map((edge, idx) => {
        const es = edgeStyle(edge.flag)
        return {
          data: {
            id: `edge-${idx}`,
            source: edge.source,
            target: edge.target,
            type: edge.type,
            weight: edge.weight,
            flag: edge.flag,
            lineStyle: es.lineStyle,
            width: Math.min(6, Math.max(1.5, Math.sqrt(edge.weight || 1))),
            label: `${edge.type} (${edge.weight})`,
          },
        }
      })

      return [...nodes, ...edges]
    },
    [],
  )

  // ── Layout Runner ──────────────────────────────────────────────────────────
  const runLayout = useCallback((cy: cytoscape.Core, mode: 'network' | 'process') => {
    if (mode === 'process') {
      const l = cy.layout({
        name: 'dagre',
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        rankDir: 'LR' as any,
        nodeSep: 45,
        rankSep: 70,
        animate: true,
        animationDuration: 350,
      } as cytoscape.LayoutOptions)
      l.run()
    } else {
      const l = cy.layout({
        name: 'cose',
        animate: true,
        animationDuration: 350,
        randomize: false,
        nodeRepulsion: () => 9000,
        idealEdgeLength: () => 90,
      } as cytoscape.LayoutOptions)
      l.run()
    }
  }, [])

  // ── Initialize Cytoscape Instance ──────────────────────────────────────────
  const initCy = useCallback(
    (data: AggregatedGraphResponse, bucketIdx: number | null, traced: Set<string>, mode: 'network' | 'process') => {
      if (!containerRef.current) return
      if (cyRef.current) cyRef.current.destroy()

      const elements = buildElements(data, bucketIdx, traced)

      const cy = cytoscape({
        container: containerRef.current,
        elements,
        style: [
          {
            selector: 'node',
            style: {
              label: 'data(label)',
              'font-size': 9,
              'text-wrap': 'ellipsis',
              'text-max-width': '85px',
              color: '#334155',
              'text-valign': 'bottom',
              'text-margin-y': 4,
              'background-color': 'data(health_color)',
              width: 'data(size)',
              height: 'data(size)',
              'border-width': (el: cytoscape.NodeSingular) => (el.data('is_problem') ? 3 : el.data('is_traced') ? 3 : 1),
              'border-color': (el: cytoscape.NodeSingular) =>
                el.data('is_traced') ? '#a855f7' : el.data('is_problem') ? '#ef4444' : '#ffffff',
            },
          },
          {
            selector: 'edge',
            style: {
              label: 'data(label)',
              'font-size': 7,
              width: 'data(width)',
              'line-style': 'data(lineStyle)' as unknown as 'solid' | 'dashed' | 'dotted',
              'line-color': '#94a3b8',
              'target-arrow-shape': 'triangle',
              'target-arrow-color': '#94a3b8',
              'curve-style': 'bezier',
              color: '#64748b',
              'text-rotation': 'autorotate',
            },
          },
          {
            selector: 'node:selected',
            style: {
              'border-width': 4,
              'border-color': '#3157d5',
            },
          },
          {
            selector: '.dimmed',
            style: {
              opacity: 0.22,
            },
          },
          {
            selector: '.highlight-problem',
            style: {
              'border-width': 4,
              'border-color': '#ef4444',
            },
          },
        ],
        userZoomingEnabled: true,
        userPanningEnabled: true,
        boxSelectionEnabled: false,
      })

      cy.on('tap', 'node', (evt) => {
        const id = evt.target.id()
        const node = data.nodes.find((n) => n.id === id)
        if (node) setSelectedNode(node)
      })

      cy.on('tap', (evt) => {
        if (evt.target === cy) setSelectedNode(null)
      })

      // Double-click on node triggers downstream trace
      cy.on('dbltap', 'node', (evt) => {
        const id = evt.target.id()
        const node = data.nodes.find((n) => n.id === id)
        if (node) {
          setSelectedNode(node)
          void traceExposureRef.current('downstream', node.id)
        }
      })

      cyRef.current = cy
      runLayout(cy, mode)
    },
    [buildElements, runLayout],
  )

  // ── Load Graph ─────────────────────────────────────────────────────────────
  const loadGraph = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    setSelectedNode(null)
    setTracedNodeIds(new Set())
    setTraceDisclaimer(null)

    try {
      const resp = incidentId
        ? await client.incidentAggregatedSupplyGraph(incidentId, { max_nodes: 150 })
        : await client.aggregatedSupplyGraph(projectId, { max_nodes: 150 })

      setGraphData(resp)
      setTimeBucketIdx(resp.time_buckets.length > 0 ? resp.time_buckets.length - 1 : null)
      initCy(resp, resp.time_buckets.length > 0 ? resp.time_buckets.length - 1 : null, new Set(), viewMode)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load aggregated supply network'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [client, projectId, incidentId, initCy, viewMode])

  useEffect(() => {
    if (projectId) void loadGraph()
    return () => {
      if (playTimerRef.current) clearInterval(playTimerRef.current)
      cyRef.current?.destroy()
      cyRef.current = null
    }
  }, [loadGraph, projectId])

  // ── View Mode Switching ────────────────────────────────────────────────────
  const switchViewMode = (mode: 'network' | 'process') => {
    setViewMode(mode)
    if (cyRef.current) {
      runLayout(cyRef.current, mode)
    }
  }

  // ── Update Health on Time Slider Change ────────────────────────────────────
  const updateTimeBucket = useCallback(
    (idx: number) => {
      setTimeBucketIdx(idx)
      if (!cyRef.current || !graphData) return
      const bucket = graphData.time_buckets[idx]
      if (!bucket) return

      cyRef.current.batch(() => {
        graphData.nodes.forEach((n) => {
          const cyNode = cyRef.current?.$id(n.id)
          if (!cyNode || cyNode.length === 0) return
          let h = n.health
          if (n.time_series) {
            const snap = n.time_series.find((s) => s.bucket === bucket)
            if (snap) h = snap.health
          }
          const col = healthColor(h)
          cyNode.data('health', h)
          cyNode.data('health_color', col)
          cyNode.style('background-color', col)
          if (h === 'PROBLEM') {
            cyNode.style('border-color', '#ef4444')
            cyNode.style('border-width', 3)
          } else if (!tracedNodeIds.has(n.id)) {
            cyNode.style('border-color', '#ffffff')
            cyNode.style('border-width', 1)
          }
        })
      })
    },
    [graphData, tracedNodeIds],
  )

  // ── Play/Pause Time Replay ─────────────────────────────────────────────────
  const togglePlay = () => {
    if (isPlaying) {
      if (playTimerRef.current) clearInterval(playTimerRef.current)
      setIsPlaying(false)
    } else {
      if (!graphData || graphData.time_buckets.length <= 1) return
      setIsPlaying(true)
      playTimerRef.current = window.setInterval(() => {
        setTimeBucketIdx((prev) => {
          const next = prev == null || prev >= graphData.time_buckets.length - 1 ? 0 : prev + 1
          updateTimeBucket(next)
          return next
        })
      }, 1400)
    }
  }

  // ── Filtering (Search, Node Type, Health) ───────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.nodes().forEach((n) => {
      const data = n.data() as Record<string, unknown>
      const label = String(data.label || n.id()).toLowerCase()
      const matchesSearch = !search || label.includes(search.toLowerCase()) || n.id().toLowerCase().includes(search.toLowerCase())
      const matchesType = typeFilter === 'ALL' || data.type === typeFilter
      const matchesHealth = healthFilter === 'ALL' || data.health === healthFilter

      n.style('display', matchesSearch && matchesType && matchesHealth ? 'element' : 'none')
    })
  }, [search, typeFilter, healthFilter])

  // ── Trace Exposure (Upstream / Downstream) ──────────────────────────────────
  const traceExposure = async (direction: 'upstream' | 'downstream', startNodeId?: string) => {
    const targetId = startNodeId || selectedNode?.id
    if (!targetId || !projectId) return

    setBusy(true)
    try {
      const traceResp = await client.aggregatedSupplyGraphTrace(projectId, targetId, direction, 6)
      const newTraced = new Set<string>([targetId, ...traceResp.reached_nodes.map((n) => n.id)])
      setTracedNodeIds(newTraced)
      setTraceDisclaimer(traceResp.disclaimer)

      const cy = cyRef.current
      if (cy) {
        cy.batch(() => {
          cy.nodes().forEach((n) => {
            if (newTraced.has(n.id())) {
              n.removeClass('dimmed')
              n.style('border-color', '#a855f7')
              n.style('border-width', 3)
            } else {
              n.addClass('dimmed')
              n.style('border-width', 1)
            }
          })
          cy.edges().forEach((e) => {
            const s = e.source().id()
            const t = e.target().id()
            if (newTraced.has(s) && newTraced.has(t)) {
              e.removeClass('dimmed')
              e.style('line-color', '#a855f7')
              e.style('target-arrow-color', '#a855f7')
              e.style('width', 3)
            } else {
              e.addClass('dimmed')
              e.style('line-color', '#cbd5e1')
              e.style('target-arrow-color', '#cbd5e1')
            }
          })
        })
      }
    } catch {
      // ignore
    } finally {
      setBusy(false)
    }
  }
  traceExposureRef.current = traceExposure

  const clearTrace = () => {
    setTracedNodeIds(new Set())
    setTraceDisclaimer(null)
    const cy = cyRef.current
    if (!cy || !graphData) return
    cy.batch(() => {
      cy.elements().removeClass('dimmed')
      cy.edges().forEach((e) => {
        const edge = graphData.edges.find((x) => x.source === e.source().id() && x.target === e.target().id())
        const es = edgeStyle(edge?.flag)
        e.style('line-color', '#94a3b8')
        e.style('target-arrow-color', '#94a3b8')
        e.style('width', es.width)
      })
      cy.nodes().forEach((n) => {
        const isProblem = n.data('is_problem')
        n.style('border-color', isProblem ? '#ef4444' : '#ffffff')
        n.style('border-width', isProblem ? 3 : 1)
      })
    })
  }

  // ── Candidate Source Selection ─────────────────────────────────────────────
  const focusCandidateSource = (candidate: CandidateSource) => {
    const node = graphData?.nodes.find((n) => n.id === candidate.node_id)
    if (node) {
      setSelectedNode(node)
      const cy = cyRef.current
      if (cy) {
        const cyNode = cy.$id(node.id)
        if (cyNode.length > 0) {
          cy.animate({
            center: { eles: cyNode },
            zoom: 1.5,
            duration: 400,
          })
          void traceExposure('downstream', node.id)
        }
      }
    }
  }

  return (
    <div className="space-y-4">
      {/* Page Header */}
      <section className="page-intro">
        <div>
          <p className="eyebrow">INVESTIGATION / NETWORK VISUALIZER</p>
          <h2 className="text-xl font-bold tracking-tight text-ink dark:text-white">
            Aggregated Supply-Chain Network
          </h2>
          <p className="text-sm text-muted mt-1 max-w-3xl">
            Interactive network of supplier cohorts, product families, carriers, and operational process groups.
            Health is computed against peer baselines. Problem nodes are highlighted with pulsing indicators.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            SYNTHETIC DATA READY
          </span>
          <TypeBadge kind="FACT" />
        </div>
      </section>

      {/* No Project Selected State */}
      {!projectId && (
        <div className="ds-info">
          <span>Select a project in the company switcher (sidebar) to load the supply graph.</span>
          <p className="text-xs text-muted mt-2">Backend gap: no project list endpoint is available. Enter the project ID manually.</p>
        </div>
      )}

      {projectId && (
        <div className="panel overflow-hidden border border-line rounded-xl bg-white dark:bg-slate-900 shadow-sm">
          {/* Main Toolbar */}
          <div className="graph-toolbar">
            <div className="graph-filter-bar">
              {/* Search */}
              <div className="graph-search-box">
                <Search size={14} className="text-muted" />
                <input
                  type="text"
                  placeholder="Search node name or ID…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  aria-label="Search graph nodes"
                />
                {search && (
                  <button className="text-muted hover:text-ink text-xs" onClick={() => setSearch('')}>
                    <X size={12} />
                  </button>
                )}
              </div>

              {/* Node Type Filter */}
              <select
                className="graph-filter-select"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                aria-label="Filter by node type"
              >
                <option value="ALL">All Roles ({graphData?.nodes.length ?? 0})</option>
                {nodeTypes.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>

              {/* Health Filter */}
              <select
                className="graph-filter-select"
                value={healthFilter}
                onChange={(e) => setHealthFilter(e.target.value)}
                aria-label="Filter by health status"
              >
                <option value="ALL">All Health</option>
                <option value="PROBLEM">Problem (Requires Attention)</option>
                <option value="WATCH">Watch (Elevated Variance)</option>
                <option value="HEALTHY">Healthy</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
            </div>

            {/* View Mode Switcher Toggle */}
            <div className="graph-view-toggle ml-auto mr-2" data-testid="graph-view-toggle">
              <button
                className={`graph-view-btn ${viewMode === 'network' ? 'active' : ''}`}
                onClick={() => switchViewMode('network')}
                title="Force-directed network cluster view"
                aria-label="Network layout view"
              >
                <Network size={13} className="inline mr-1" />
                Network View
              </button>
              <button
                className={`graph-view-btn ${viewMode === 'process' ? 'active' : ''}`}
                onClick={() => switchViewMode('process')}
                title="Layered left-to-right process flow view"
                aria-label="Process flow layout view"
              >
                <Layers size={13} className="inline mr-1" />
                Process Flow
              </button>
            </div>

            {/* Canvas Zoom Controls */}
            <div className="flex gap-1">
              <button
                className="icon-button"
                aria-label="Zoom in"
                onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.25)}
              >
                <ZoomIn size={14} />
              </button>
              <button
                className="icon-button"
                aria-label="Zoom out"
                onClick={() => cyRef.current?.zoom(cyRef.current.zoom() / 1.25)}
              >
                <ZoomOut size={14} />
              </button>
              <button
                className="icon-button"
                aria-label="Fit graph"
                onClick={() => cyRef.current?.fit(undefined, 30)}
              >
                <Maximize2 size={14} />
              </button>
            </div>
          </div>

          {/* Persistent Legend */}
          <GraphLegend />

          {/* Capped Graph Banner */}
          {graphData?.capping?.capped && (
            <div className="graph-capping-banner">
              <div className="flex items-center gap-2">
                <AlertTriangle size={15} className="flex-shrink-0" />
                <span>
                  Network capped at <strong>{graphData.capping.max_nodes}</strong> groups (original{' '}
                  {graphData.capping.original_count}).{' '}
                  <strong>{graphData.capping.clustered_into_other}</strong> tail groups clustered into "Other" nodes.
                </span>
              </div>
            </div>
          )}

          {/* Missing Roles Indicator */}
          {graphData?.missing_roles && graphData.missing_roles.length > 0 && (
            <div className="missing-roles-banner">
              <Info size={13} className="text-muted" />
              <span className="font-semibold text-muted">Omitted node roles:</span>
              {graphData.missing_roles.map((r) => (
                <span key={r.role} className="missing-role-tag" title={r.omitted_reason}>
                  {r.role} ({r.omitted_reason})
                </span>
              ))}
            </div>
          )}

          {/* Candidate Sources Ranked Strip (Problem Focus) */}
          {graphData?.candidate_sources && graphData.candidate_sources.length > 0 && (
            <div className="candidate-sources-strip">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-semibold text-red-800 dark:text-red-300">
                  <ShieldAlert size={14} className="text-red-600" />
                  <span>Ranked Candidate Source Nodes</span>
                  <span className="text-[10px] text-muted italic">(candidate / hypothesis, not confirmed cause)</span>
                </div>
                {tracedNodeIds.size > 0 && (
                  <button className="text-xs text-red-700 hover:underline" onClick={clearTrace}>
                    Reset focus
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {graphData.candidate_sources.map((cand) => (
                  <button
                    key={cand.node_id}
                    className="candidate-source-chip"
                    onClick={() => focusCandidateSource(cand)}
                    title={`Click to focus on ${cand.label} and trace downstream exposure`}
                  >
                    <span className="w-4 h-4 rounded-full bg-red-600 text-white font-bold text-[9px] flex items-center justify-center">
                      {cand.rank}
                    </span>
                    <span>{cand.label}</span>
                    <span className="text-[10px] text-red-500">
                      ({cand.anomaly_count} anomalies · score {cand.score.toFixed(1)})
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Canvas & States */}
          {loading && (
            <div className="loading-state py-24 flex items-center justify-center gap-2">
              <LoaderCircle size={20} className="animate-spin text-brand" />
              <span>Building aggregated supply network…</span>
            </div>
          )}

          {error && !loading && (
            <div className="ds-err m-5" role="alert">
              <AlertTriangle size={15} />
              <span>{error}</span>
              <button className="ml-2 underline text-xs font-semibold" onClick={() => void loadGraph()}>
                Retry
              </button>
            </div>
          )}

          {!loading && !error && graphData && graphData.nodes.length === 0 && (
            <div className="empty-state py-24">No graph nodes returned for this project scope.</div>
          )}

          {!loading && !error && graphData && graphData.nodes.length > 0 && (
            <div className="graph-canvas-area relative">
              <div ref={containerRef} className="graph-canvas-cyto" style={{ height: '620px' }} />

              {/* Side Panel */}
              {selectedNode && (
                <SidePanel
                  node={selectedNode}
                  onClose={() => setSelectedNode(null)}
                  onTraceUp={() => void traceExposure('upstream')}
                  onTraceDown={() => void traceExposure('downstream')}
                  onClearTrace={clearTrace}
                  isTraced={tracedNodeIds.size > 0}
                  busy={busy}
                  traceDisclaimer={traceDisclaimer}
                />
              )}
            </div>
          )}

          {/* Time Slider for Health Replay */}
          {graphData && graphData.time_buckets.length > 0 && (
            <div className="graph-time-slider-bar">
              <button
                className="icon-button"
                onClick={togglePlay}
                title={isPlaying ? 'Pause replay' : 'Play health evolution replay'}
                aria-label={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? <Pause size={13} /> : <Play size={13} />}
              </button>

              <span className="text-xs font-bold text-ink dark:text-white whitespace-nowrap">
                {timeBucketIdx != null ? graphData.time_buckets[timeBucketIdx] : 'Latest Aggregated'}
              </span>

              <input
                type="range"
                className="graph-time-slider-input"
                min={0}
                max={graphData.time_buckets.length - 1}
                value={timeBucketIdx ?? graphData.time_buckets.length - 1}
                onChange={(e) => updateTimeBucket(parseInt(e.target.value, 10))}
                aria-label="Time replay slider"
              />

              <span className="text-[10px] text-muted whitespace-nowrap">
                {graphData.time_buckets.length} time buckets
              </span>

              <button
                className="text-xs text-muted hover:text-ink underline"
                onClick={() => updateTimeBucket(graphData.time_buckets.length - 1)}
                title="Jump to latest aggregate"
              >
                Latest
              </button>
            </div>
          )}

          {/* Disclaimer Footer */}
          <div className="graph-warning m-4 flex items-start gap-2 text-xs text-muted">
            <AlertTriangle size={15} className="flex-shrink-0 text-amber-500 mt-0.5" />
            <p>
              Candidate source nodes and downstream traced paths represent <strong>exposure and hypotheses</strong>,
              never confirmed root causes. Confirmed causes require human reviewer verification in the Incidents screen.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
