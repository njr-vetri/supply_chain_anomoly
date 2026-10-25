export function EvidenceState({ value }: { value: string }) {
  return <p className="text-sm font-medium text-amber-800 dark:text-amber-200" role="status">{value}</p>
}
