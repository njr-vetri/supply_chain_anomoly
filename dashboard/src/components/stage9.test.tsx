/**
 * Stage 9 component tests.
 * All data is SYNTHETIC. Never used to claim production accuracy.
 */
import { describe, expect, it, vi, beforeAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { TypeBadge } from '../components/TypeBadge'
import { LoginScreen } from '../components/LoginScreen'
import { DataSourcesScreen } from '../components/DataSourcesScreen'
import { MonitoringScreen } from '../components/MonitoringScreen'
import { PredictionsScreen } from '../components/PredictionsScreen'
import { RecommendationsScreen } from '../components/RecommendationsScreen'
import { SupplyGraphScreen } from '../components/SupplyGraphScreen'
import { SystemHealthScreen } from '../components/SystemHealthScreen'
import type { ApiClient } from '../api/client'

// Suppress expected console.error noise from React inside tests
beforeAll(() => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

// ── TypeBadge ─────────────────────────────────────────────────────────────────

describe('TypeBadge – new badge variants', () => {
  it('renders SYNTHETIC badge with correct text', () => {
    render(<TypeBadge kind="SYNTHETIC" />)
    expect(screen.getByText('SYNTHETIC')).toBeInTheDocument()
  })

  it('renders SIMULATED badge with correct text', () => {
    render(<TypeBadge kind="SIMULATED" />)
    expect(screen.getByText('SIMULATED')).toBeInTheDocument()
  })

  it('renders DRY_RUN badge with correct text', () => {
    render(<TypeBadge kind="DRY_RUN" />)
    expect(screen.getByText('DRY_RUN')).toBeInTheDocument()
  })
})

// ── LoginScreen ───────────────────────────────────────────────────────────────

describe('LoginScreen', () => {
  it('shows error when API health check rejects with a connection error', async () => {
    // Patch fetch to simulate a network failure
    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('synthetic network failure')) as typeof fetch
    const onLogin = vi.fn()
    render(<LoginScreen onLogin={onLogin} />)

    const { fireEvent } = await import('@testing-library/react')
    const usernameInput = await screen.findByLabelText(/Email or Username/i)
    const passwordInput = screen.getByLabelText(/Password/i)
    const submitBtn = screen.getByRole('button', { name: /Sign In/i })

    // Fill in credentials so the form can submit
    fireEvent.change(usernameInput, { target: { value: 'testuser' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    expect(onLogin).not.toHaveBeenCalled()
    globalThis.fetch = originalFetch
  })
})

// ── DataSourcesScreen ─────────────────────────────────────────────────────────

describe('DataSourcesScreen', () => {
  const syntheticClient = {
    datasets: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    importHistory: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    datasetSuggestions: vi.fn().mockResolvedValue({ suggestions: [], capabilities: [] }),
  } as unknown as ApiClient

  it('shows permission denied on Upload tab when role is viewer', async () => {
    render(<DataSourcesScreen client={syntheticClient} role="viewer" />)
    // Click Upload tab
    const uploadTab = screen.getByRole('button', { name: 'Upload' })
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.click(uploadTab)
    await waitFor(() => {
      expect(screen.getByText(/Analyst role required to upload files/i)).toBeInTheDocument()
    })
  })

  it('shows "suggestions are never auto-confirmed" notice on Mapping tab', async () => {
    render(<DataSourcesScreen client={syntheticClient} role="reviewer" />)
    const mappingTab = screen.getByRole('button', { name: 'Mapping wizard' })
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.click(mappingTab)
    await waitFor(() => {
      expect(screen.getByText(/suggestions are never auto-confirmed/i)).toBeInTheDocument()
    })
  })
})

// ── MonitoringScreen ──────────────────────────────────────────────────────────

describe('MonitoringScreen', () => {
  const syntheticClient = {
    anomalies: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    alertHistory: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    datasetDrift: vi.fn().mockResolvedValue({
      dataset_name: 'synthetic_orders',
      drift_is_warning_only: true,
      triggers_automatic_retrain: false,
      warning: 'Drift is advisory, never an automatic retrain trigger.',
      schema_changes: { added: [], removed: [], retyped: {} },
      feature_drift: {},
    }),
  } as unknown as ApiClient

  it('renders "Drift is advisory, never an automatic retrain trigger" warning when reviewer', async () => {
    render(<MonitoringScreen client={syntheticClient} role="reviewer" knownSources={['synthetic_orders']} />)
    await waitFor(() => {
      expect(screen.getByText(/Drift is advisory, never an automatic retrain trigger/i)).toBeInTheDocument()
    })
  })

  it('shows permission denied for drift when role is viewer', () => {
    render(<MonitoringScreen client={syntheticClient} role="viewer" knownSources={['synthetic_orders']} />)
    expect(screen.getByText(/Reviewer role required to view drift/i)).toBeInTheDocument()
  })
})

// ── PredictionsScreen ─────────────────────────────────────────────────────────

describe('PredictionsScreen', () => {
  const syntheticClient = {
    evaluationOutcomes: vi.fn().mockResolvedValue({
      status: 'INSUFFICIENT_VERIFIED_OUTCOMES',
      message: 'not enough verified outcomes',
    }),
    predictions: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    outcomes: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  } as unknown as ApiClient

  it('renders "not enough verified outcomes" verbatim from the API response', async () => {
    render(<PredictionsScreen client={syntheticClient} />)
    await waitFor(() => {
      expect(screen.getByText('not enough verified outcomes')).toBeInTheDocument()
    })
  })

  it('renders the Insufficient evidence label above the message', async () => {
    render(<PredictionsScreen client={syntheticClient} />)
    await waitFor(() => {
      expect(screen.getByText('Insufficient evidence')).toBeInTheDocument()
    })
  })
})

// ── SupplyGraphScreen ─────────────────────────────────────────────────────────

describe('SupplyGraphScreen', () => {
  const syntheticClient = {} as unknown as ApiClient

  it('shows "Select a project" empty state when projectId is empty', () => {
    render(<SupplyGraphScreen client={syntheticClient} projectId="" />)
    expect(screen.getByText(/Select a project in the company switcher/i)).toBeInTheDocument()
  })

  it('shows backend gap notice when projectId is empty', () => {
    render(<SupplyGraphScreen client={syntheticClient} projectId="" />)
    expect(screen.getByText(/no project list endpoint is available/i)).toBeInTheDocument()
  })
})

// ── RecommendationsScreen ─────────────────────────────────────────────────────

describe('RecommendationsScreen', () => {
  const syntheticDryRunAction = {
    id: 'synthetic-action-1',
    recommendation_id: 'synthetic-rec-1',
    source: 'synthetic',
    record_refs: [],
    dry_run: true,
    status: 'DRY_RUN',
    created_at: '2026-01-01T00:00:00Z',
  }
  const syntheticClient = {
    recommendations: vi.fn().mockResolvedValue({
      items: [{
        id: 'synthetic-rec-1',
        action: 'Synthetic dry-run recommendation',
        rationale: 'Synthetic rationale',
        evidence_refs: [],
        prediction_refs: [],
        hypothesis_refs: [],
        source: 'synthetic',
        record_refs: [],
        human_approval_required: true,
        assumptions: [],
        uncertainty: 'UNKNOWN',
        constraints: [],
        created_at: '2026-01-01T00:00:00Z',
      }],
      count: 1,
    }),
    approvals: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    actions: vi.fn().mockResolvedValue({ items: [syntheticDryRunAction], count: 1 }),
    outcomes: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  } as unknown as ApiClient

  it('shows DRY_RUN badge on a dry-run action record', async () => {
    render(<RecommendationsScreen client={syntheticClient} role="reviewer" />)
    await waitFor(() => {
      expect(screen.getByText('DRY_RUN')).toBeInTheDocument()
    })
  })
})

// ── SystemHealthScreen ────────────────────────────────────────────────────────

describe('SystemHealthScreen', () => {
  const syntheticClient = {
    models: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  } as unknown as ApiClient

  it('shows "no pipeline run history endpoint" notice', async () => {
    render(<SystemHealthScreen client={syntheticClient} role="reviewer" onAudit={() => undefined} />)
    await waitFor(() => {
      expect(screen.getByText(/no pipeline run history endpoint/i)).toBeInTheDocument()
    })
  })
})
