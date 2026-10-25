import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import * as THREE from 'three'
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

const HEALTH_COLOR: Record<HealthStatus, string> = {
  HEALTHY:  '#22c55e',
  WATCH:    '#f59e0b',
  PROBLEM:  '#ef4444',
  AT_RISK:  '#f59e0b',
  INCIDENT: '#ef4444',
  UNKNOWN:  '#94a3b8',
}

function healthColor(h?: string | null): string {
  return HEALTH_COLOR[(h as HealthStatus)] ?? HEALTH_COLOR.UNKNOWN
}

function healthHex(h?: string | null): number {
  const s = HEALTH_COLOR[(h as HealthStatus)] ?? HEALTH_COLOR.UNKNOWN
  return parseInt(s.replace('#', ''), 16)
}

function isProblemHealth(h?: string | null): boolean {
  return h === 'PROBLEM' || h === 'INCIDENT'
}

function nodeRadius(exposure?: number | null): number {
  if (exposure == null || exposure <= 0) return 0.35
  return Math.min(0.85, Math.max(0.3, 0.3 + Math.sqrt(exposure) * 0.045))
}

function fibonacciSphere(n: number, radius: number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = []
  const phi = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1 || 1)) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = phi * i
    pts.push(new THREE.Vector3(r * Math.cos(theta) * radius, y * radius, r * Math.sin(theta) * radius))
  }
  return pts
}

function SidePanel({
  node, onClose, onTraceUp, onTraceDown, onClearTrace, isTraced, busy, traceDisclaimer,
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
        <button className="icon-button" aria-label="Close side panel" onClick={onClose}><X size={15} /></button>
      </div>
      <div className="graph-panel-body space-y-4">
        <div className="flex flex-wrap gap-2 items-center">
          <TypeBadge kind="FACT" />
          <span className={`status-chip ${isProblemHealth(node.health) ? 'pulse-problem-ring' : ''}`}
            style={{ background: healthColor(node.health), color: '#fff' }}>{node.health}</span>
          {node.candidate_source_rank != null && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300">
              Rank #{node.candidate_source_rank} Candidate
            </span>
          )}
        </div>
        {node.health_reason && (
          <p className="text-xs text-muted italic bg-slate-50 dark:bg-slate-900 p-2 rounded border border-line">{node.health_reason}</p>
        )}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="eval-metric-cell">
            <p className="text-muted">Exposure Volume</p>
            <p className="font-semibold text-ink dark:text-white">{Number(node.exposure).toLocaleString()}</p>
          </div>
          <div className="eval-metric-cell">
            <p className="text-muted">Anomalies Detected</p>
            <p className={`font-semibold ${node.anomaly_count > 0 ? 'text-red-600' : 'text-ink dark:text-white'}`}>{node.anomaly_count}</p>
          </div>
        </div>
        {baselines.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted">Peer Baseline Comparisons</span>
              <span className="text-[10px] text-muted">vs group mean</span>
            </div>
            <div className="space-y-2">
              {baselines.map(([k, metric]: [string, PeerMetricBaseline]) => {
                const isHighZ = Math.abs(metric.z_score) >= 2.0
                return (
                  <div key={k} className="peer-baseline-card">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-ink dark:text-slate-200 capitalize">{k.replace(/_/g, ' ')}</span>
                      <span className={`peer-zscore-badge ${isHighZ ? 'peer-zscore-high' : 'peer-zscore-norm'}`}>
                        z = {metric.z_score > 0 ? `+${metric.z_score.toFixed(1)}` : metric.z_score.toFixed(1)}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-1 text-[10px] text-muted">
                      <div>Node value: <strong className="text-ink dark:text-white">{metric.node_value.toFixed(1)}</strong></div>
                      <div>Peer mean: {metric.peer_mean.toFixed(1)} (+-{metric.peer_std.toFixed(1)})</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
        <div className="space-y-2 pt-2 border-t border-line">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Exposure Tracing</p>
          <div className="flex flex-col gap-2">
            <button className="btn-secondary w-full justify-center" onClick={onTraceDown} disabled={busy}>
              {busy ? <LoaderCircle size={13} className="animate-spin" /> : <ArrowRight size={13} />}
              <span>Trace Downstream Exposure</span>
            </button>
            <button className="btn-secondary w-full justify-center" onClick={onTraceUp} disabled={busy}>
              {busy ? <LoaderCircle size={13} className="animate-spin" /> : <RotateCcw size={13} />}
              <span>Trace Upstream Sources</span>
            </button>
            {isTraced && (
              <button className="text-xs text-muted hover:text-ink underline text-center pt-1" onClick={onClearTrace}>Clear path highlights</button>
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
        {node.evidence_refs && node.evidence_refs.length > 0 && (
          <div className="pt-2 border-t border-line">
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted mb-1.5">Evidence Provenance</p>
            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
              {node.evidence_refs.map((ref) => (
                <span key={ref} className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-[10px] text-muted font-mono">{ref}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function GraphLegend() {
  return (
    <div className="graph-legend" data-testid="graph-legend">
      <span className="font-semibold text-muted mr-1">HEALTH:</span>
      <span className="legend-item"><span className="legend-dot" style={{ background: HEALTH_COLOR.HEALTHY }} />Healthy</span>
      <span className="legend-item"><span className="legend-dot" style={{ background: HEALTH_COLOR.WATCH }} />Watch</span>
      <span className="legend-item"><span className="legend-dot" style={{ background: HEALTH_COLOR.PROBLEM, border: '2px solid #ef4444' }} />Problem (Red Glow)</span>
      <span className="legend-item"><span className="legend-dot" style={{ background: HEALTH_COLOR.UNKNOWN }} />Unknown</span>
      <span className="font-semibold text-muted ml-3 mr-1">SIZE:</span>
      <span className="legend-item text-muted">Proportional to Exposure</span>
      <span className="font-semibold text-muted ml-3 mr-1">CONTROLS:</span>
      <span className="legend-item text-muted">Drag=Orbit, Scroll=Zoom, Click=Inspect</span>
    </div>
  )
}

type ExtDiv = HTMLDivElement & { _threeZoomIn?: () => void; _threeZoomOut?: () => void; _threeReset?: () => void }

function ThreeCanvas({
  graphData, tracedNodeIds, onNodeClick,
}: {
  graphData: AggregatedGraphResponse
  tracedNodeIds: Set<string>
  onNodeClick: (node: AggregatedGraphNode) => void
}) {
  const mountRef = useRef<HTMLDivElement | null>(null)
  const tracedRef = useRef(tracedNodeIds)
  const onClickRef = useRef(onNodeClick)
  tracedRef.current = tracedNodeIds
  onClickRef.current = onNodeClick

  useEffect(() => {
    const container = mountRef.current
    if (!container) return

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x060c1a)
    scene.fog = new THREE.FogExp2(0x060c1a, 0.015)
    const w = container.clientWidth || 800
    const h = container.clientHeight || 620
    const camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 400)
    camera.position.set(0, 0, 22)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(w, h)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    container.appendChild(renderer.domElement)

    scene.add(new THREE.AmbientLight(0x334155, 2.5))
    const dir = new THREE.DirectionalLight(0xffffff, 2.0)
    dir.position.set(10, 15, 10)
    scene.add(dir)
    const pt = new THREE.PointLight(0x6366f1, 4, 50)
    scene.add(pt)

    scene.add(new THREE.Mesh(
      new THREE.SphereGeometry(10, 48, 48),
      new THREE.MeshBasicMaterial({ color: 0x1e2a3f, wireframe: true, transparent: true, opacity: 0.12 })
    ))

    const starPos = new Float32Array(600 * 3)
    for (let i = 0; i < starPos.length; i++) starPos[i] = (Math.random() - 0.5) * 250
    const starGeo = new THREE.BufferGeometry()
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3))
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.18, transparent: true, opacity: 0.45 })))

    const { nodes, edges } = graphData
    const positions = fibonacciSphere(nodes.length, 9.5)
    const nodePosMap = new Map<string, THREE.Vector3>()
    nodes.forEach((n, i) => nodePosMap.set(n.id, positions[i]))
    const nodeIndex = new Map<string, AggregatedGraphNode>()
    nodes.forEach((n) => nodeIndex.set(n.id, n))
    const meshToNode = new Map<THREE.Mesh, string>()
    const nodeMeshes: THREE.Mesh[] = []
    const glowMeshes: THREE.Mesh[] = []

    nodes.forEach((n, i) => {
      const pos = positions[i]
      const isProblem = isProblemHealth(n.health)
      const r = nodeRadius(n.exposure)
      const mat = new THREE.MeshStandardMaterial({
        color: healthHex(n.health), roughness: 0.35, metalness: 0.45,
        emissive: isProblem ? 0xef4444 : 0x000000,
        emissiveIntensity: isProblem ? 0.6 : 0,
      })
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 16), mat)
      mesh.position.copy(pos)
      scene.add(mesh)
      meshToNode.set(mesh, n.id)
      nodeMeshes.push(mesh)
      if (isProblem) {
        const glow = new THREE.Mesh(
          new THREE.SphereGeometry(r * 2.0, 16, 16),
          new THREE.MeshBasicMaterial({ color: 0xff2222, transparent: true, opacity: 0.15, side: THREE.BackSide })
        )
        glow.position.copy(pos)
        scene.add(glow)
        glowMeshes.push(glow)
      }
    })

    edges.forEach((e) => {
      const src = nodePosMap.get(e.source)
      const tgt = nodePosMap.get(e.target)
      if (!src || !tgt) return
      scene.add(new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([src, tgt]),
        new THREE.LineBasicMaterial({ color: 0x2d3f5a, transparent: true, opacity: 0.5 })
      ))
    })

    let isDragging = false
    let prevMouse = { x: 0, y: 0 }
    let rotX = 0, rotY = 0
    let camDist = 22
    let autoRotate = true
    const onMouseDown = (e: MouseEvent) => { isDragging = true; autoRotate = false; prevMouse = { x: e.clientX, y: e.clientY } }
    const onMouseUp = () => { isDragging = false }
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging) return
      rotY += (e.clientX - prevMouse.x) * 0.008
      rotX = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotX + (e.clientY - prevMouse.y) * 0.008))
      prevMouse = { x: e.clientX, y: e.clientY }
    }
    const onWheel = (e: WheelEvent) => { camDist = Math.max(8, Math.min(70, camDist + e.deltaY * 0.04)) }
    const raycaster = new THREE.Raycaster()
    const mouse2d = new THREE.Vector2()
    let mouseDownPos = { x: 0, y: 0 }
    const onMouseDownForClick = (e: MouseEvent) => { mouseDownPos = { x: e.clientX, y: e.clientY } }
    const onClick = (e: MouseEvent) => {
      if (Math.abs(e.clientX - mouseDownPos.x) > 5 || Math.abs(e.clientY - mouseDownPos.y) > 5) return
      const rect = renderer.domElement.getBoundingClientRect()
      mouse2d.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      mouse2d.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(mouse2d, camera)
      const hits = raycaster.intersectObjects(nodeMeshes)
      if (hits.length > 0) {
        const nid = meshToNode.get(hits[0].object as THREE.Mesh)
        if (nid) { const nd = nodeIndex.get(nid); if (nd) onClickRef.current(nd) }
      }
    }
    renderer.domElement.addEventListener('mousedown', onMouseDown)
    renderer.domElement.addEventListener('mousedown', onMouseDownForClick)
    renderer.domElement.addEventListener('mouseup', onMouseUp)
    renderer.domElement.addEventListener('mousemove', onMouseMove)
    renderer.domElement.addEventListener('click', onClick)
    renderer.domElement.addEventListener('wheel', onWheel, { passive: true })

    ;(container as ExtDiv)._threeZoomIn = () => { camDist = Math.max(8, camDist * 0.8) }
    ;(container as ExtDiv)._threeZoomOut = () => { camDist = Math.min(70, camDist * 1.25) }
    ;(container as ExtDiv)._threeReset = () => { rotX = 0; rotY = 0; camDist = 22; autoRotate = true }

    let frame = 0
    let animId: number
    const animate = () => {
      animId = requestAnimationFrame(animate)
      frame++
      if (autoRotate) rotY += 0.003
      camera.position.x = camDist * Math.sin(rotY) * Math.cos(rotX)
      camera.position.y = camDist * Math.sin(rotX)
      camera.position.z = camDist * Math.cos(rotY) * Math.cos(rotX)
      camera.lookAt(0, 0, 0)
      const pulse = 0.5 + 0.5 * Math.sin(frame * 0.07)
      glowMeshes.forEach((g) => {
        ;(g.material as THREE.MeshBasicMaterial).opacity = 0.08 + 0.18 * pulse
        g.scale.setScalar(1 + 0.2 * pulse)
      })
      nodeMeshes.forEach((m) => {
        const nid = meshToNode.get(m)
        if (!nid) return
        const mat2 = m.material as THREE.MeshStandardMaterial
        if (tracedRef.current.has(nid)) {
          mat2.emissive.setHex(0xa855f7); mat2.emissiveIntensity = 0.8
        } else {
          const nd = nodeIndex.get(nid)
          if (isProblemHealth(nd?.health)) { mat2.emissive.setHex(0xef4444); mat2.emissiveIntensity = 0.5 + 0.3 * pulse }
          else { mat2.emissive.setHex(0x000000); mat2.emissiveIntensity = 0 }
        }
      })
      renderer.render(scene, camera)
    }
    animate()

    const onResize = () => {
      const w2 = container.clientWidth; const h2 = container.clientHeight
      camera.aspect = w2 / h2; camera.updateProjectionMatrix(); renderer.setSize(w2, h2)
    }
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', onResize)
      renderer.domElement.removeEventListener('mousedown', onMouseDown)
      renderer.domElement.removeEventListener('mousedown', onMouseDownForClick)
      renderer.domElement.removeEventListener('mouseup', onMouseUp)
      renderer.domElement.removeEventListener('mousemove', onMouseMove)
      renderer.domElement.removeEventListener('click', onClick)
      renderer.domElement.removeEventListener('wheel', onWheel)
      renderer.dispose()
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement)
    }
  }, [graphData])

  return <div ref={mountRef} style={{ width: '100%', height: '620px', cursor: 'grab' }} data-testid="three-canvas-mount" />
}

export function SupplyGraphScreen({
  client, projectId, incidentId,
}: {
  client: ApiClient
  projectId: string
  incidentId?: string
}) {
  const canvasRef = useRef<ExtDiv | null>(null)
  const [graphData, setGraphData] = useState<AggregatedGraphResponse | null>(null)
  const [selectedNode, setSelectedNode] = useState<AggregatedGraphNode | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tracedNodeIds, setTracedNodeIds] = useState<Set<string>>(new Set())
  const [traceDisclaimer, setTraceDisclaimer] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [healthFilter, setHealthFilter] = useState('ALL')
  const [onlyProblems, setOnlyProblems] = useState(false)
  const [timeBucketIdx, setTimeBucketIdx] = useState<number | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const playTimerRef = useRef<number | null>(null)

  const problemNodesCount = graphData?.nodes.filter((n) => isProblemHealth(n.health)).length ?? 0
  const anomalyNodesCount = graphData?.nodes.filter((n) => (n.anomaly_count ?? 0) > 0).length ?? 0
  const filteredCount = graphData?.nodes.filter((n) => {
    const ms = !search || (n.label || n.id).toLowerCase().includes(search.toLowerCase())
    const mh = healthFilter === 'ALL' || n.health === healthFilter
    const mp = !onlyProblems || isProblemHealth(n.health)
    return ms && mh && mp
  }).length ?? 0

  const loadGraph = useCallback(async () => {
    if (!projectId) return
    setLoading(true); setError(null); setSelectedNode(null); setTracedNodeIds(new Set()); setTraceDisclaimer(null)
    try {
      const resp = incidentId
        ? await client.incidentAggregatedSupplyGraph(incidentId, { max_nodes: 150 })
        : await client.aggregatedSupplyGraph(projectId, { max_nodes: 150 })
      setGraphData(resp)
      setTimeBucketIdx(resp.time_buckets.length > 0 ? resp.time_buckets.length - 1 : null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load aggregated supply network')
    } finally { setLoading(false) }
  }, [client, projectId, incidentId])

  useEffect(() => {
    if (projectId) void loadGraph()
    return () => { if (playTimerRef.current) clearInterval(playTimerRef.current) }
  }, [loadGraph, projectId])

  const togglePlay = () => {
    if (isPlaying) { if (playTimerRef.current) clearInterval(playTimerRef.current); setIsPlaying(false) }
    else {
      if (!graphData || graphData.time_buckets.length <= 1) return
      setIsPlaying(true)
      playTimerRef.current = window.setInterval(() =>
        setTimeBucketIdx((p) => p == null || p >= graphData.time_buckets.length - 1 ? 0 : p + 1), 1400)
    }
  }

  const traceExposure = useCallback(async (direction: 'upstream' | 'downstream', startNodeId?: string) => {
    const targetId = startNodeId || selectedNode?.id
    if (!targetId || !projectId) return
    setBusy(true)
    try {
      const r = await client.aggregatedSupplyGraphTrace(projectId, targetId, direction, 6)
      setTracedNodeIds(new Set([targetId, ...r.reached_nodes.map((n) => n.id)]))
      setTraceDisclaimer(r.disclaimer)
    } catch { /* ignore */ } finally { setBusy(false) }
  }, [client, projectId, selectedNode])

  const clearTrace = () => { setTracedNodeIds(new Set()); setTraceDisclaimer(null) }

  const focusCandidateSource = (candidate: CandidateSource) => {
    const node = graphData?.nodes.find((n) => n.id === candidate.node_id)
    if (node) { setSelectedNode(node); void traceExposure('downstream', node.id) }
  }

  return (
    <div className="space-y-4">
      <section className="page-intro">
        <div>
          <p className="eyebrow">INVESTIGATION / 3D NETWORK GLOBE</p>
          <h2 className="text-xl font-bold tracking-tight text-ink dark:text-white">Supply-Chain 3D Network Globe</h2>
          <p className="text-sm text-muted mt-1 max-w-3xl">
            Interactive 3D globe of supplier cohorts, product families, carriers, and process groups.
            <strong className="text-red-500"> Red glowing nodes</strong> = active anomalies / problems.
            Drag to orbit, scroll to zoom, click a node to inspect.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {problemNodesCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-red-600/10 border border-red-600/30 text-red-600 dark:text-red-400 text-xs font-bold animate-pulse">
              <span className="w-2 h-2 rounded-full bg-red-500" />{problemNodesCount} Problem Nodes
            </span>
          )}
          {anomalyNodesCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-600/10 border border-amber-600/30 text-amber-600 dark:text-amber-400 text-xs font-bold">
              <AlertTriangle size={12} />{anomalyNodesCount} with Anomalies
            </span>
          )}
          <TypeBadge kind="FACT" />
        </div>
      </section>

      {!projectId && (
        <div className="ds-info">
          <span>Select a project in the company switcher to load the 3D supply network globe.</span>
          <p className="text-xs text-muted mt-1">No project list endpoint is available.</p>
        </div>
      )}

      {projectId && (
        <div className="panel overflow-hidden border border-line rounded-xl bg-white dark:bg-slate-900 shadow-sm">
          <div className="graph-toolbar">
            <div className="graph-filter-bar">
              <div className="graph-search-box">
                <Search size={14} className="text-muted" />
                <input type="text" placeholder="Filter node by name..." value={search}
                  onChange={(e) => setSearch(e.target.value)} aria-label="Search graph nodes" />
                {search && <button className="text-muted hover:text-ink text-xs" onClick={() => setSearch('')}><X size={12} /></button>}
              </div>
              <select className="graph-filter-select" value={healthFilter}
                onChange={(e) => setHealthFilter(e.target.value)} aria-label="Filter by health status">
                <option value="ALL">All Health</option>
                <option value="PROBLEM">Problem / Incident</option>
                <option value="WATCH">Watch (Elevated)</option>
                <option value="HEALTHY">Healthy</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
              <button
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold rounded-lg border transition-all ${onlyProblems
                  ? 'bg-rose-600 text-white border-rose-700'
                  : 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900'}`}
                onClick={() => setOnlyProblems(!onlyProblems)}>
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                Only Problems ({problemNodesCount})
              </button>
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <button className="icon-button" aria-label="Zoom in" title="Zoom in" onClick={() => canvasRef.current?._threeZoomIn?.()}><ZoomIn size={14} /></button>
              <button className="icon-button" aria-label="Zoom out" title="Zoom out" onClick={() => canvasRef.current?._threeZoomOut?.()}><ZoomOut size={14} /></button>
              <button className="icon-button" aria-label="Reset camera" title="Reset camera" onClick={() => canvasRef.current?._threeReset?.()}><Maximize2 size={14} /></button>
            </div>
          </div>

          <GraphLegend />

          {graphData?.candidate_sources && graphData.candidate_sources.length > 0 && (
            <div className="candidate-sources-strip">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-semibold text-red-800 dark:text-red-300">
                  <ShieldAlert size={14} className="text-red-600" />
                  <span>Ranked Candidate Source Nodes</span>
                  <span className="text-[10px] text-muted italic">(candidate / hypothesis, not confirmed cause)</span>
                </div>
                {tracedNodeIds.size > 0 && <button className="text-xs text-red-700 hover:underline" onClick={clearTrace}>Reset focus</button>}
              </div>
              <div className="flex flex-wrap gap-2">
                {graphData.candidate_sources.map((cand) => (
                  <button key={cand.node_id} className="candidate-source-chip" onClick={() => focusCandidateSource(cand)}>
                    <span className="w-4 h-4 rounded-full bg-red-600 text-white font-bold text-[9px] flex items-center justify-center">{cand.rank}</span>
                    <span>{cand.label}</span>
                    <span className="text-[10px] text-red-500">({cand.anomaly_count} anomalies, score {cand.score.toFixed(1)})</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {graphData?.capping?.capped && (
            <div className="graph-capping-banner">
              <AlertTriangle size={15} className="flex-shrink-0" />
              <span>Network capped at <strong>{graphData.capping.max_nodes}</strong> groups (original {graphData.capping.original_count}). <strong>{graphData.capping.clustered_into_other}</strong> tail groups clustered into Other nodes.</span>
            </div>
          )}
          {graphData?.missing_roles && graphData.missing_roles.length > 0 && (
            <div className="missing-roles-banner">
              <Info size={13} className="text-muted" />
              <span className="font-semibold text-muted">Omitted node roles:</span>
              {graphData.missing_roles.map((r) => (
                <span key={r.role} className="missing-role-tag" title={r.omitted_reason}>{r.role} ({r.omitted_reason})</span>
              ))}
            </div>
          )}

          {loading && (
            <div className="loading-state py-24 flex items-center justify-center gap-2">
              <LoaderCircle size={20} className="animate-spin text-brand" /><span>Building 3D supply network globe...</span>
            </div>
          )}
          {error && !loading && (
            <div className="ds-err m-5" role="alert">
              <AlertTriangle size={15} /><span>{error}</span>
              <button className="ml-2 underline text-xs font-semibold" onClick={() => void loadGraph()}>Retry</button>
            </div>
          )}
          {!loading && !error && graphData && graphData.nodes.length === 0 && (
            <div className="empty-state py-24">No graph nodes returned for this project scope.</div>
          )}

          {!loading && !error && graphData && graphData.nodes.length > 0 && (
            <div className="relative" ref={canvasRef as RefObject<HTMLDivElement>}>
              <ThreeCanvas graphData={graphData} tracedNodeIds={tracedNodeIds} onNodeClick={setSelectedNode} />
              <div className="absolute bottom-4 left-4 flex flex-col gap-1 pointer-events-none">
                <div className="flex items-center gap-2 bg-black/70 backdrop-blur-sm rounded-lg px-3 py-2 text-xs text-white">
                  <Network size={12} className="text-indigo-400" />
                  <span className="font-semibold">{graphData.nodes.length} nodes</span>
                  <span className="text-slate-400">-</span>
                  <span className="text-slate-300">{graphData.edges.length} edges</span>
                  {(search || healthFilter !== 'ALL' || onlyProblems) && (
                    <><span className="text-slate-400">-</span><span className="text-indigo-300">{filteredCount} shown</span></>
                  )}
                  {problemNodesCount > 0 && (
                    <><span className="text-slate-400">-</span><span className="text-red-400 font-bold animate-pulse">{problemNodesCount} anomalies</span></>
                  )}
                </div>
                <div className="bg-black/60 backdrop-blur-sm rounded-lg px-3 py-1.5 text-[10px] text-slate-400">
                  Drag to orbit - Scroll to zoom - Click node for details
                </div>
              </div>
              {selectedNode && (
                <div className="absolute top-0 right-0 h-full">
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
                </div>
              )}
            </div>
          )}

          {graphData && graphData.time_buckets.length > 0 && (
            <div className="graph-time-slider-bar">
              <button className="icon-button" onClick={togglePlay} aria-label={isPlaying ? 'Pause' : 'Play'}>
                {isPlaying ? <Pause size={13} /> : <Play size={13} />}
              </button>
              <span className="text-xs font-bold text-ink dark:text-white whitespace-nowrap">
                {timeBucketIdx != null ? graphData.time_buckets[timeBucketIdx] : 'Latest'}
              </span>
              <input type="range" className="graph-time-slider-input" min={0}
                max={graphData.time_buckets.length - 1}
                value={timeBucketIdx ?? graphData.time_buckets.length - 1}
                onChange={(e) => setTimeBucketIdx(parseInt(e.target.value, 10))}
                aria-label="Time replay slider" />
              <span className="text-[10px] text-muted whitespace-nowrap">{graphData.time_buckets.length} time buckets</span>
              <button className="text-xs text-muted hover:text-ink underline"
                onClick={() => setTimeBucketIdx(graphData.time_buckets.length - 1)}>Latest</button>
            </div>
          )}

          <div className="graph-warning m-4 flex items-start gap-2 text-xs text-muted">
            <AlertTriangle size={15} className="flex-shrink-0 text-amber-500 mt-0.5" />
            <p>Candidate source nodes and traced paths represent <strong>exposure and hypotheses</strong>, never confirmed root causes. Confirmed causes require human reviewer verification in the Incidents screen.</p>
          </div>
        </div>
      )}
    </div>
  )
}
