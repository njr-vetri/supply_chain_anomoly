import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SupplyGraphScreen, GraphLegend } from './SupplyGraphScreen'
import type { ApiClient } from '../api/client'
import type { AggregatedGraphResponse } from '../api/types'

// Three.js is not available in jsdom; stub out WebGL renderer
vi.mock('three', () => {
  const Vec3 = function(x=0,y=0,z=0) { return {x,y,z,copy:vi.fn(),set:vi.fn(),setScalar:vi.fn(),setHex:vi.fn()} }
  const Geo = function() { return {setAttribute:vi.fn(),setFromPoints:vi.fn()} }
  const Mat = function() { return {opacity:0,color:{setHex:vi.fn()},emissive:{setHex:vi.fn()},emissiveIntensity:0,dispose:vi.fn()} }
  const Mesh = function(_g:unknown,m:unknown) { return {position:Vec3(),add:vi.fn(),scale:{setScalar:vi.fn()},material:m} }
  const Line = function() { return {} }
  const Points = function() { return {} }
  const Camera = function() { return {position:Vec3(),aspect:1,updateProjectionMatrix:vi.fn(),lookAt:vi.fn()} }
  const Light = function() { return {position:Vec3()} }
  const Renderer = function() { return {
    domElement: document.createElement('canvas'),
    setSize:vi.fn(), setPixelRatio:vi.fn(), render:vi.fn(), dispose:vi.fn(),
    shadowMap:{enabled:false}
  } }
  const Scene = function() { return {background:null,fog:null,add:vi.fn()} }
  const Fog = function() { return {} }
  const Color = function() { return {} }
  const BufferAttr = function() { return {} }
  const Raycaster = function() { return {setFromCamera:vi.fn(),intersectObjects:vi.fn().mockReturnValue([])} }
  const Vec2 = function() { return {x:0,y:0} }
  return {
    Scene, PerspectiveCamera:Camera, WebGLRenderer:Renderer,
    AmbientLight:Light, DirectionalLight:Light, PointLight:Light,
    SphereGeometry:Geo, BufferGeometry:Geo, MeshStandardMaterial:Mat, MeshBasicMaterial:Mat,
    LineBasicMaterial:Mat, PointsMaterial:Mat,
    Mesh, Line, Points, Raycaster,
    Vector3:Vec3, Vector2:Vec2,
    Color, FogExp2:Fog,
    BufferAttribute:BufferAttr,
    BackSide:2,
  }
})

describe('GraphLegend', () => {
  it('renders all required health colours', () => {
    render(<GraphLegend />)
    expect(screen.getByTestId('graph-legend')).toBeInTheDocument()
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    expect(screen.getByText('Watch')).toBeInTheDocument()
    expect(screen.getByText(/Problem/i)).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })
})

describe('SupplyGraphScreen', () => {
  const mockClient = {
    aggregatedSupplyGraph: vi.fn(),
    aggregatedSupplyGraphTrace: vi.fn(),
    incidentAggregatedSupplyGraph: vi.fn(),
  } as unknown as ApiClient

  const mockGraphData: AggregatedGraphResponse = {
    nodes: [
      {
        id: 'SUP:SUP-FAULTY', label: 'SUP-FAULTY', type: 'Supplier',
        exposure: 450, health: 'PROBLEM',
        health_reason: 'Elevated anomaly rate vs peers (z=3.2)', anomaly_count: 8,
        evidence_refs: ['doc-1'],
        time_series: [
          { bucket: '2026-01-05', exposure: 200, anomalies: 0, health: 'HEALTHY' },
          { bucket: '2026-01-12', exposure: 250, anomalies: 8, health: 'PROBLEM' },
        ],
        metrics_vs_peer_baseline: { price: { node_value: 4500.0, peer_mean: 100.0, peer_std: 15.0, z_score: 3.2 } },
        candidate_source_rank: 1, culprit: true,
      },
      {
        id: 'PROD:PROD-A', label: 'PROD-A', type: 'Product',
        exposure: 450, health: 'WATCH', anomaly_count: 2, evidence_refs: [], time_series: [],
      },
    ],
    edges: [{ source: 'SUP:SUP-FAULTY', target: 'PROD:PROD-A', type: 'SUPPLIES', weight: 450, flag: 'ESTABLISHED', source_refs: ['order-ref-1'] }],
    time_buckets: ['2026-01-05', '2026-01-12'],
    capping: { capped: true, max_nodes: 150, original_count: 220, returned_count: 150, clustered_into_other: 70 },
    missing_roles: [{ role: 'Warehouse', omitted_reason: 'no warehouse foreign keys in active dataset' }],
    candidate_sources: [{
      node_id: 'SUP:SUP-FAULTY', label: 'SUP-FAULTY', type: 'Supplier',
      score: 9.6, anomaly_count: 8, exposure: 450, rank: 1, health: 'PROBLEM',
      disclaimer: 'candidate / hypothesis, not confirmed cause',
    }],
  }

  it('shows empty state notice when projectId is empty', () => {
    render(<SupplyGraphScreen client={mockClient} projectId="" />)
    expect(screen.getByText(/Select a project in the company switcher/i)).toBeInTheDocument()
  })

  it('renders 3D globe screen header and calls aggregatedSupplyGraph', async () => {
    vi.mocked(mockClient.aggregatedSupplyGraph).mockResolvedValueOnce(mockGraphData)
    render(<SupplyGraphScreen client={mockClient} projectId="proj-synthetic-1" />)
    expect(screen.getByText(/Supply-Chain 3D Network Globe/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(mockClient.aggregatedSupplyGraph).toHaveBeenCalledWith('proj-synthetic-1', { max_nodes: 150 })
    })
    expect(screen.getByText(/Network capped at/i)).toBeInTheDocument()
    expect(screen.getByText(/Omitted node roles:/i)).toBeInTheDocument()
    expect(screen.getByText(/Ranked Candidate Source Nodes/i)).toBeInTheDocument()
    expect(screen.getByText('SUP-FAULTY')).toBeInTheDocument()
  })

  it('renders Three.js canvas mount when graph data is loaded', async () => {
    vi.mocked(mockClient.aggregatedSupplyGraph).mockResolvedValueOnce(mockGraphData)
    render(<SupplyGraphScreen client={mockClient} projectId="proj-synthetic-1" />)
    await waitFor(() => {
      expect(screen.getByTestId('three-canvas-mount')).toBeInTheDocument()
    })
  })
})
