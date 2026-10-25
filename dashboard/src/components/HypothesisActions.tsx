import type { Role } from '../api/types'

const statuses = ['UNVERIFIED', 'SUPPORTED', 'CONFIRMED', 'REJECTED', 'CLOSED'] as const
export function HypothesisActions({ status, role, onConfirm, disabled = false }: { status: string; role: Role; onConfirm?: () => void; disabled?: boolean }) {
  const canConfirm = role === 'reviewer'
  return <div className="flex flex-wrap items-center gap-2">
    <span className="rounded-md bg-slate-100 px-2.5 py-1 text-[10px] font-bold tracking-widest text-slate-700 dark:bg-slate-800 dark:text-slate-200">{statuses.includes(status as typeof statuses[number]) ? status : 'UNVERIFIED'}</span>
    {status !== 'CONFIRMED' && <button type="button" disabled={!canConfirm || disabled} onClick={onConfirm} title={canConfirm ? 'Confirm hypothesis' : 'Reviewer role required'} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:text-slate-100">Confirm</button>}
  </div>
}
