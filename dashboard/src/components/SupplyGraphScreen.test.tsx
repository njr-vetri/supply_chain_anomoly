import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SupplyGraphScreen, GraphLegend } from './SupplyGraphScreen'
import type { ApiClient } from '../api/client'
import type { AggregatedGraphResponse } from '../api/types'

describe('GraphLegend', () => {
  it('renders all required health colors and edge line kinds', () => {
    render(<GraphLegend />)
    expect(screen.getByTestId('graph-legend')).toBeInTheDocument()
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    expect(screen.getByText('Watch')).toBeInTheDocument()
    expect(screen.getByText(/Problem/i)).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
    expect(screen.getByText(/Established/i)).toBeInTheDocument()
    expect(screen.getByText(/Inferred/i)).toBeInTheDocument()
    expect(screen.getByText(/User Entered/i)).toBeInTheDocument()
    expect(screen.getByText(/Proportional to Exposure Volume/i)).toBeInTheDocument()
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
        id: 'SUP:SUP-FAULTY',
        label: 'SUP-FAULTY',
        type: 'Supplier',
        exposure: 450,
        health: 'PROBLEM',
        health_reason: 'Elevated anomaly rate vs peers (z=3.2)',
        anomaly_count: 8,
        evidence_refs: ['doc-1'],
        time_series: [
          { bucket: '2026-01-05', exposure: 200, anomalies: 0, health: 'HEALTHY' },
          { bucket: '2026-01-12', exposure: 250, anomalies: 8, health: 'PROBLEM' },
        ],
        metrics_vs_peer_baseline: {
          price: { node_value: 4500.0, peer_mean: 100.0, peer_std: 15.0, z_score: 3.2 },
        },
        candidate_source_rank: 1,
        culprit: true,
      },
      {
        id: 'PROD:PROD-A',
        label: 'PROD-A',
        type: 'Product',
        exposure: 450,
        health: 'WATCH',
        anomaly_count: 2,
        evidence_refs: [],
        time_series: [],
      },
    ],
    edges: [
      {
        source: 'SUP:SUP-FAULTY',
        target: 'PROD:PROD-A',
        type: 'SUPPLIES',
        weight: 450,
        flag: 'ESTABLISHED',
        source_refs: ['order-ref-1'],
      },
    ],
    time_buckets: ['2026-01-05', '2026-01-12'],
    capping: {
      capped: true,
      max_nodes: 150,
      original_count: 220,
      returned_count: 150,
      clustered_into_other: 70,
    },
    missing_roles: [
      { role: 'Warehouse', omitted_reason: 'no warehouse foreign keys in active dataset' },
    ],
    candidate_sources: [
      {
        node_id: 'SUP:SUP-FAULTY',
        label: 'SUP-FAULTY',
        type: 'Supplier',
        score: 9.6,
        anomaly_count: 8,
        exposure: 450,
        rank: 1,
        health: 'PROBLEM',
        disclaimer: 'candidate / hypothesis, not confirmed cause',
      },
    ],
  }

  it('shows empty state notice when projectId is empty', () => {
    render(<SupplyGraphScreen client={mockClient} projectId="" />)
    expect(screen.getByText(/Select a project in the company switcher/i)).toBeInTheDocument()
    expect(screen.getByText(/no project list endpoint is available/i)).toBeInTheDocument()
  })

  it('renders toolbar, view toggle, and calls aggregatedSupplyGraph', async () => {
    vi.mocked(mockClient.aggregatedSupplyGraph).mockResolvedValueOnce(mockGraphData)

    render(<SupplyGraphScreen client={mockClient} projectId="proj-synthetic-1" />)

    expect(screen.getByText(/Aggregated Supply-Chain Network/i)).toBeInTheDocument()
    expect(screen.getByTestId('graph-view-toggle')).toBeInTheDocument()
    expect(screen.getByLabelText(/Network layout view/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Process flow layout view/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(mockClient.aggregatedSupplyGraph).toHaveBeenCalledWith('proj-synthetic-1', { max_nodes: 150 })
    })

    // Check Capping banner
    expect(screen.getByText(/Network capped at/i)).toBeInTheDocument()
    expect(screen.getByText(/70/i)).toBeInTheDocument()

    // Check Missing roles banner
    expect(screen.getByText(/Omitted node roles:/i)).toBeInTheDocument()
    expect(screen.getByText(/Warehouse \(no warehouse foreign keys in active dataset\)/i)).toBeInTheDocument()

    // Check Candidate sources strip
    expect(screen.getByText(/Ranked Candidate Source Nodes/i)).toBeInTheDocument()
    expect(screen.getByText(/candidate \/ hypothesis, not confirmed cause/i)).toBeInTheDocument()
    expect(screen.getByText('SUP-FAULTY')).toBeInTheDocument()
  })

  it('allows switching view mode to Process Flow', async () => {
    vi.mocked(mockClient.aggregatedSupplyGraph).mockResolvedValueOnce(mockGraphData)

    render(<SupplyGraphScreen client={mockClient} projectId="proj-synthetic-1" />)

    await waitFor(() => {
      expect(screen.getByLabelText(/Process flow layout view/i)).toBeInTheDocument()
    })

    const processBtn = screen.getByLabelText(/Process flow layout view/i)
    fireEvent.click(processBtn)

    expect(processBtn).toHaveClass('active')
  })
})
