import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { EvidenceState } from './EvidenceState'
import { HypothesisActions } from './HypothesisActions'
import { TypeBadge } from './TypeBadge'

describe('transparency components', () => {
  it('renders each finding type with its explicit label', () => {
    const kinds = ['FACT', 'PREDICTION', 'HYPOTHESIS', 'RECOMMENDATION'] as const
    render(<div>{kinds.map((kind) => <TypeBadge key={kind} kind={kind} />)}</div>)
    for (const kind of kinds) expect(screen.getByText(kind)).toBeInTheDocument()
  })

  it('shows the exact insufficient-evidence state supplied by the backend', () => {
    render(<EvidenceState value="Insufficient evidence" />)
    expect(screen.getByRole('status')).toHaveTextContent('Insufficient evidence')
  })

  it('enables hypothesis confirmation only for reviewer roles', () => {
    const onConfirm = vi.fn()
    const { rerender } = render(<HypothesisActions status="SUPPORTED" role="analyst" onConfirm={onConfirm} />)
    const button = screen.getByRole('button', { name: 'Confirm' })
    expect(button).toBeDisabled()
    rerender(<HypothesisActions status="SUPPORTED" role="admin" onConfirm={onConfirm} />)
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
    rerender(<HypothesisActions status="SUPPORTED" role="reviewer" onConfirm={onConfirm} />)
    const reviewerButton = screen.getByRole('button', { name: 'Confirm' })
    expect(reviewerButton).toBeEnabled()
    fireEvent.click(reviewerButton)
    expect(onConfirm).toHaveBeenCalledOnce()
  })
})
