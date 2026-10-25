import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApiClient } from '../api/client'
import { graphElements } from './graphElements'
import { ErrorBoundary } from './ErrorBoundary'
import { NotFoundPage } from './NotFoundPage'
import { SettingsScreen } from './RecordScreens'
import { ApprovalQueueScreen } from './WorkflowScreens'

const syntheticGraph = {
  nodes: [
    { id: 'synthetic-incident-1', type: 'INCIDENT', source: 'synthetic' },
    { id: 'synthetic-evidence-1', type: 'EVIDENCE', source: 'synthetic' },
  ],
  edges: [{ from: 'synthetic-incident-1', to: 'synthetic-evidence-1', type: 'SUPPORTS', meaning: 'Synthetic test relationship', source_ref: 'synthetic-row-1', status: 'INFERRED' }],
}

describe('Phase 11B transparency and safety UI', () => {
  it('shows edge meaning, evidence reference and inferred status without asserting cause', () => {
    const graph = graphElements(syntheticGraph)
    expect(graph.edges[0].label).toContain('Synthetic test relationship')
    expect(graph.edges[0].label).toContain('INFERRED')
    expect(graph.edges[0].label).toContain('synthetic-row-1')
    expect(graph.edges[0].style?.strokeDasharray).toBe('6 4')
  })

  it('shows a not-found page with a route back to overview', () => {
    const home = vi.fn()
    render(<NotFoundPage goHome={home} />)
    expect(screen.getByText('404 · PAGE NOT FOUND')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Return to overview' }))
    expect(home).toHaveBeenCalledOnce()
  })

  it('catches view errors in the global boundary', () => {
    const original = console.error
    console.error = vi.fn()
    function SyntheticFailure(): never { throw new Error('synthetic render error') }
    try {
      render(<ErrorBoundary><SyntheticFailure /></ErrorBoundary>)
      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Reload console' })).toBeInTheDocument()
    } finally { console.error = original }
  })

  it('hides the kill-switch toggle from non-admin roles', () => {
    render(<SettingsScreen client={{} as ApiClient} role="reviewer" apiUrl="http://localhost:8000" onSaveUrl={vi.fn()} dark={false} onToggleTheme={vi.fn()} onKillSwitch={vi.fn()} />)
    expect(screen.getByText(/restricts kill-switch access to admin keys/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Turn kill switch/i })).not.toBeInTheDocument()
  })

  it('requires an admin confirmation reason before toggling the kill switch', async () => {
    const client = {
      killSwitch: vi.fn().mockResolvedValue({ enabled: false }),
      toggleKillSwitch: vi.fn().mockResolvedValue({ enabled: true, reason: 'Synthetic reason' }),
    } as unknown as ApiClient
    render(<SettingsScreen client={client} role="admin" apiUrl="http://localhost:8000" onSaveUrl={vi.fn()} dark={false} onToggleTheme={vi.fn()} onKillSwitch={vi.fn()} />)
    const open = await screen.findByRole('button', { name: 'Turn kill switch ON' })
    fireEvent.click(open)
    const confirm = screen.getByRole('button', { name: 'Confirm change' })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Synthetic operator reason' } })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)
    await waitFor(() => expect(client.toggleKillSwitch).toHaveBeenCalledWith({ enabled: true, reason: 'Synthetic operator reason' }))
  })

  it('requires a reviewer reason before approving a synthetic pending item', async () => {
    const client = {
      approvals: vi.fn().mockResolvedValue({ items: [{ id: 'synthetic-approval-1', recommendation_id: 'synthetic-rec-1', status: 'pending', reviewed_at: '2026-01-01T00:00:00Z', rationale: '' }], count: 1 }),
      recommendations: vi.fn().mockResolvedValue({ items: [], count: 0 }),
      actions: vi.fn().mockResolvedValue({ items: [], count: 0 }),
      approve: vi.fn().mockResolvedValue({ id: 'synthetic-approval-1', status: 'approved' }),
    } as unknown as ApiClient
    render(<ApprovalQueueScreen client={client} role="reviewer" />)
    const approve = await screen.findByRole('button', { name: 'Approve' })
    expect(approve).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Approval reason synthetic-approval-1'), { target: { value: 'Synthetic reviewer reason' } })
    expect(approve).toBeEnabled()
    fireEvent.click(approve)
    await waitFor(() => expect(client.approve).toHaveBeenCalledWith('synthetic-approval-1', { rationale: 'Synthetic reviewer reason' }))
  })
})
