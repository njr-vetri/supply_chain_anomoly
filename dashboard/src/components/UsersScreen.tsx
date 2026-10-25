import { useState, useEffect, useCallback } from 'react'
import { UserPlus, KeyRound, Trash2, Lock, AlertCircle, Check, Copy, Loader2, RefreshCw } from 'lucide-react'
import { ApiClient } from '../api/client'

interface UserItem {
  id: string
  username: string
  email: string
  role: 'viewer' | 'analyst' | 'reviewer' | 'admin'
  is_active: boolean
  must_change_password: boolean
  locked_until: string | null
  created_at: string | null
}

interface Props {
  client: ApiClient
}

export function UsersScreen({ client }: Props) {
  const [users, setUsers] = useState<UserItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Add User Modal
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'viewer' | 'analyst' | 'reviewer' | 'admin'>('viewer')
  const [submitting, setSubmitting] = useState(false)

  // Password Notification Modal
  const [tempPwdModal, setTempPwdModal] = useState<{ title: string; username: string; tempPwd: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await client.listUsers()
      setUsers(res.items || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not fetch users')
    } finally {
      setLoading(false)
    }
  }, [client])

  useEffect(() => {
    void fetchUsers()
  }, [fetchUsers])

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !email.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await client.createUser({
        username: username.trim(),
        email: email.trim(),
        role,
      })
      setIsAddOpen(false)
      setUsername('')
      setEmail('')
      setRole('viewer')
      fetchUsers()
      if (res.temporary_password) {
        setTempPwdModal({
          title: 'User Created',
          username: res.user.username,
          tempPwd: res.temporary_password,
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setSubmitting(false)
    }
  }

  const handleResetPassword = async (user: UserItem) => {
    if (!confirm(`Reset password for ${user.username}? A temporary password will be generated.`)) return
    try {
      const res = await client.adminResetPassword(user.id)
      setTempPwdModal({
        title: 'Password Reset',
        username: user.username,
        tempPwd: res.temporary_password,
      })
      fetchUsers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset password')
    }
  }

  const handleDeleteUser = async (user: UserItem) => {
    if (!confirm(`Are you sure you want to delete user ${user.username}?`)) return
    try {
      await client.deleteUser(user.id)
      setSuccess(`User ${user.username} deleted`)
      fetchUsers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user')
    }
  }

  const roleColors: Record<string, string> = {
    admin: 'bg-purple-500/10 text-purple-600 border-purple-200 dark:border-purple-900 dark:text-purple-400',
    reviewer: 'bg-blue-500/10 text-blue-600 border-blue-200 dark:border-blue-900 dark:text-blue-400',
    analyst: 'bg-emerald-500/10 text-emerald-600 border-emerald-200 dark:border-emerald-900 dark:text-emerald-400',
    viewer: 'bg-slate-500/10 text-slate-600 border-slate-200 dark:border-slate-800 dark:text-slate-400',
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-white">User Accounts</h1>
          <p className="mt-1 text-sm text-muted dark:text-slate-400">
            Manage company users, role assignments, temporary passwords, and account security.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchUsers}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-surface dark:border-slate-800 dark:text-white"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={() => setIsAddOpen(true)}
            className="btn btn-primary flex items-center gap-1.5 text-xs"
          >
            <UserPlus size={14} />
            Add User
          </button>
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

      {/* Users Table */}
      <div className="panel overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-line bg-card/40 text-[11px] font-semibold uppercase tracking-wider text-muted dark:border-slate-800 dark:text-slate-400">
            <tr>
              <th className="px-5 py-3">User</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Security Status</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line dark:divide-slate-800">
            {users.map((u) => (
              <tr key={u.id} className="transition hover:bg-card/50">
                <td className="px-5 py-3.5">
                  <div className="font-semibold text-ink dark:text-white">{u.username}</div>
                  <div className="text-[11px] text-muted dark:text-slate-400">{u.email}</div>
                </td>
                <td className="px-4 py-3.5">
                  <span
                    className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize ${
                      roleColors[u.role] || roleColors.viewer
                    }`}
                  >
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3.5">
                  <div className="space-y-1">
                    {u.must_change_password && (
                      <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                        <Lock size={10} /> Temp password (change required)
                      </span>
                    )}
                    {u.locked_until && (
                      <span className="inline-flex items-center gap-1 rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-600 dark:text-rose-400">
                        <AlertCircle size={10} /> Account locked
                      </span>
                    )}
                    {!u.must_change_password && !u.locked_until && (
                      <span className="text-muted dark:text-slate-400">Standard active</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3.5 text-muted dark:text-slate-400">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-5 py-3.5 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={() => handleResetPassword(u)}
                      className="rounded-lg border border-line p-1.5 text-muted transition hover:bg-card hover:text-ink dark:border-slate-800 dark:text-slate-400 dark:hover:text-white"
                      title="Reset Password"
                    >
                      <KeyRound size={14} />
                    </button>
                    <button
                      onClick={() => handleDeleteUser(u)}
                      className="rounded-lg border border-line p-1.5 text-rose-500 transition hover:bg-rose-50 hover:text-rose-600 dark:border-slate-800 dark:hover:bg-rose-950/40"
                      title="Delete User"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && !loading && (
              <tr>
                <td colSpan={5} className="p-8 text-center text-muted">
                  No users found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Add User Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <h3 className="text-lg font-bold text-ink dark:text-white">Add New User</h3>
            <p className="mt-1 text-xs text-muted dark:text-slate-400">
              Users will receive a secure temporary password and must change it on their first login.
            </p>
            <form onSubmit={handleCreateUser} className="mt-4 space-y-3.5">
              <div>
                <label className="text-xs font-semibold text-ink dark:text-slate-300">Username</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. jdoe"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="text-input mt-1 w-full text-xs"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink dark:text-slate-300">Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="e.g. jdoe@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="text-input mt-1 w-full text-xs"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink dark:text-slate-300">Role</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as 'viewer' | 'analyst' | 'reviewer' | 'admin')}
                  className="text-input mt-1 w-full text-xs"
                >
                  <option value="viewer">Viewer (Read-only access)</option>
                  <option value="analyst">Analyst (Upload, map, pipeline, draft hypotheses)</option>
                  <option value="reviewer">Reviewer (Analyst + confirm hypotheses, approve actions)</option>
                  <option value="admin">Admin (Full privileges: users, settings, scheduler)</option>
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setIsAddOpen(false)}
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
                  Create User
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Temporary Password Modal */}
      {tempPwdModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
              <KeyRound size={20} />
              <h3 className="text-base font-bold text-ink dark:text-white">{tempPwdModal.title}</h3>
            </div>
            <p className="mt-2 text-xs text-muted dark:text-slate-400">
              Temporary password for <strong>{tempPwdModal.username}</strong>. Provide this to the user; forced change is enabled.
            </p>
            <div className="mt-4 flex items-center justify-between rounded-xl border border-line bg-card p-3 font-mono text-sm dark:border-slate-800">
              <span className="select-all font-semibold text-ink dark:text-white">{tempPwdModal.tempPwd}</span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(tempPwdModal.tempPwd)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 2000)
                }}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-sky-600 transition hover:bg-sky-50 dark:text-sky-400 dark:hover:bg-sky-950/40"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setTempPwdModal(null)}
                className="btn btn-primary text-xs"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
