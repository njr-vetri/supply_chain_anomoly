import type { FindingKind } from '../api/types'

const BADGE_CONFIG: Record<
  FindingKind,
  { label: string; cls: string }
> = {
  FACT:           { label: 'FACT',           cls: 'badge-fact' },
  PREDICTION:     { label: 'PREDICTION',     cls: 'badge-prediction' },
  HYPOTHESIS:     { label: 'HYPOTHESIS',     cls: 'badge-hypothesis' },
  RECOMMENDATION: { label: 'RECOMMENDATION', cls: 'badge-recommendation' },
  SYNTHETIC:      { label: 'SYNTHETIC',      cls: 'badge-synthetic' },
  SIMULATED:      { label: 'SIMULATED',      cls: 'badge-simulated' },
  DRY_RUN:        { label: 'DRY_RUN',        cls: 'badge-dry-run' },
}

export function TypeBadge({ kind }: { kind: FindingKind }) {
  const cfg = BADGE_CONFIG[kind] ?? { label: kind, cls: 'badge-fact' }
  return <span className={`type-badge ${cfg.cls}`}>{cfg.label}</span>
}
