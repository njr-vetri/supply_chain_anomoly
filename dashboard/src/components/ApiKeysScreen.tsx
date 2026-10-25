import { useState, useEffect, useCallback } from 'react'
import { Key, Plus, Trash2, AlertCircle, Check, Copy, Loader2, RefreshCw, Info } from 'lucide-react'
import { ApiClient } from '../api/client'

interface ApiKeyItem {
  id: string
  name: string
  prefix: string
  role: 'viewer' | 'analyst'
  scopes: string[]
  created_at: string | null
  last_used_at: string | null
}

interface Props {
  client: ApiClient
}

export function ApiKeysScreen({ client }: Props) {
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Generate Key Modal
  const [isGenerateOpen, setIsGenerateOpen] = useState(false)
  const [name, setName] = useState('')
  const [role, setRole] = useState<'viewer' | 'analyst'>('viewer')
  const [submitting, setSubmitting] = useState(false)

  // Key Display Modal
  const [newKey, setNewKey] = useState<{ name: string; key: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const fetchKeys = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await client.listApiKeys()
      setKeys(res.items || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not fetch API keys')
    } finally {
      setLoading(false)
    }
  }, [client])

  useEffect(() => {
    void fetchKeys()
  }, [fetchKeys])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await client.createApiKey({
        name: name.trim(),
        role,
        scopes: role === 'analyst' ? ['read', 'write'] : ['read'],
      })
      setIsGenerateOpen(false)
      setName('')
      setRole('viewer')
      fetchKeys()
      setNewKey({
        name: res.name,
        key: res.api_key,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate API key')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevoke = async (keyItem: ApiKeyItem) => {
    if (!confirm(`Revoke API key "${keyItem.name}" (${keyItem.prefix}...)? Connected automated pipelines will immediately lose access.`)) return
    try {
      await client.revokeApiKey(keyItem.id)
      setSuccess(`API key "${keyItem.name}" revoked`)
      fetchKeys()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke API key')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-white">Machine API Keys</h1>
          <p className="mt-1 text-sm text-muted dark:text-slate-400">
            Keys for automated CI pipelines, data connectors, and external integrations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchKeys}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-surface dark:border-slate-800 dark:text-white"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={() => setIsGenerateOpen(true)}
            className="btn btn-primary flex items-center gap-1.5 text-xs"
          >
            <Plus size={14} />
            Generate Key
          </button>
        </div>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50/70 p-4 text-xs text-sky-900 dark:border-sky-900/50 dark:bg-sky-950/30 dark:text-sky-200">
        <Info size={16} className="mt-0.5 shrink-0 text-sky-600 dark:text-sky-400" />
        <div>
          <span className="font-semibold">Security Governance Rule:</span> Machine API keys are scoped strictly to one company and capped at Analyst role. For transparency and human oversight, machine keys can <strong>never</strong> confirm root cause hypotheses or approve high-impact actions.
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
          <div className="flex items-center gap-2">
            <Check size={16} />
            <span>{success}</span>
          </div>
          <button onClick={() => setSuccess(null)} className="font-bold">✕</button>
        </div>
      )}

      {/* Keys Table */}
      <div className="panel overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-line bg-card/40 text-[11px] font-semibold uppercase tracking-wider text-muted dark:border-slate-800 dark:text-slate-400">
            <tr>
              <th className="px-5 py-3">Key Name</th>
              <th className="px-4 py-3">Prefix</th>
              <th className="px-4 py-3">Role & Scopes</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3">Last Used</th>
              <th className="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line dark:divide-slate-800">
            {keys.map((k) => (
              <tr key={k.id} className="transition hover:bg-card/50">
                <td className="px-5 py-3.5 font-semibold text-ink dark:text-white">
                  {k.name}
                </td>
                <td className="px-4 py-3.5 font-mono text-[11px] text-muted dark:text-slate-400">
                  {k.prefix}...
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-1.5">
                    <span className="rounded bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-medium uppercase text-sky-600 dark:text-sky-400">
                      {k.role}
                    </span>
                    <span className="text-[11px] text-muted">
                      ({k.scopes?.join(', ') || 'read'})
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3.5 text-muted dark:text-slate-400">
                  {k.created_at ? new Date(k.created_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-4 py-3.5 text-muted dark:text-slate-400">
                  {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'Never'}
                </td>
                <td className="px-5 py-3.5 text-right">
                  <button
                    onClick={() => handleRevoke(k)}
                    className="rounded-lg border border-line p-1.5 text-rose-500 transition hover:bg-rose-50 hover:text-rose-600 dark:border-slate-800 dark:hover:bg-rose-950/40"
                    title="Revoke Key"
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
            {keys.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-muted">
                  No machine API keys found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Generate Key Modal */}
      {isGenerateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <h3 className="text-lg font-bold text-ink dark:text-white">Generate Machine API Key</h3>
            <p className="mt-1 text-xs text-muted dark:text-slate-400">
              API keys provide programmatic access to this company's workspace only.
            </p>
            <form onSubmit={handleCreate} className="mt-4 space-y-3.5">
              <div>
                <label className="text-xs font-semibold text-ink dark:text-slate-300">Key Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. ERP Ingestion Service"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="text-input mt-1 w-full text-xs"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink dark:text-slate-300">Permitted Role</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as 'viewer' | 'analyst')}
                  className="text-input mt-1 w-full text-xs"
                >
                  <option value="viewer">Viewer (Read datasets, anomalies, and metrics)</option>
                  <option value="analyst">Analyst (Upload datasets, map columns, run pipelines)</option>
                </select>
                <p className="mt-1 text-[11px] text-muted dark:text-slate-400">
                  Reviewer and Admin permissions are prohibited for machine keys by policy.
                </p>
              </div>
              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setIsGenerateOpen(false)}
                  className="rounded-lg border border-line px-3.5 py-1.5 text-xs font-medium text-muted hover:bg-card dark:border-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn btn-primary flex items-center gap-1.5 text-xs"
                >
                  {submitting && <Loader2 size={12} className="animate-spin" />}
                  Generate
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Key Display Modal */}
      {newKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
              <Key size={20} />
              <h3 className="text-base font-bold text-ink dark:text-white">API Key Generated</h3>
            </div>
            <p className="mt-2 text-xs text-muted dark:text-slate-400">
              Copy this API key now. For security reasons, it will <strong>never</strong> be shown again.
            </p>
            <div className="mt-4 flex items-center justify-between rounded-xl border border-line bg-card p-3 font-mono text-xs dark:border-slate-800">
              <span className="select-all break-all font-semibold text-ink dark:text-white">{newKey.key}</span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(newKey.key)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 2000)
                }}
                className="ml-2 flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-sky-600 transition hover:bg-sky-50 dark:text-sky-400 dark:hover:bg-sky-950/40"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setNewKey(null)}
                className="btn btn-primary text-xs"
              >
                I have copied the key
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
