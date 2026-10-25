import { useState, useEffect } from 'react'
import { Activity, Loader2, AlertCircle } from 'lucide-react'
import { ApiClient, ApiError, defaultApiUrl } from '../api/client'
import type { Role } from '../api/types'

export interface LoginValues {
  apiUrl: string
  token: string
  role: Role
  companyId: string
  username: string
  email: string
}

interface Props {
  onLogin: (values: LoginValues) => void
  expiredMessage?: string | null
}

export function LoginScreen({ onLogin, expiredMessage }: Props) {
  const apiUrl = defaultApiUrl
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null)
  const [checkingSetup, setCheckingSetup] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(expiredMessage || null)

  // Login form state
  const [usernameOrEmail, setUsernameOrEmail] = useState('')
  const [password, setPassword] = useState('')

  // Setup form state
  const [setupCompanyId, setSetupCompanyId] = useState('')
  const [setupCompanyName, setSetupCompanyName] = useState('')
  const [adminUsername, setAdminUsername] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')

  // Forced password change state
  const [changePwdUser, setChangePwdUser] = useState<{ token: string; role: Role; companyId: string; username: string; email: string } | null>(null)
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  useEffect(() => {
    let active = true
    setCheckingSetup(true)
    const client = new ApiClient(apiUrl.trim(), '')
    client.setupStatus()
      .then((res) => { if (active) setSetupRequired(res.setup_required) })
      .catch(() => { if (active) setSetupRequired(false) })
      .finally(() => { if (active) setCheckingSetup(false) })
    return () => { active = false }
  }, [apiUrl])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!usernameOrEmail.trim() || !password.trim()) {
      setError('Please provide username/email and password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const client = new ApiClient(apiUrl.trim(), '')
      const res = await client.login({
        username_or_email: usernameOrEmail.trim(),
        password: password.trim(),
      })
      const user = res.user
      if (user.must_change_password) {
        setChangePwdUser({
          token: res.token,
          role: user.role,
          companyId: user.company_id,
          username: user.username,
          email: user.email,
        })
        setOldPassword(password)
        setBusy(false)
        return
      }
      onLogin({
        apiUrl: apiUrl.trim(),
        token: res.token,
        role: user.role,
        companyId: user.company_id,
        username: user.username,
        email: user.email,
      })
    } catch (err) {
      if (err instanceof ApiError && err.status === 423) {
        setError('Account temporarily locked due to repeated failed attempts. Please try again later.')
      } else if (err instanceof ApiError && err.status === 401) {
        setError('Invalid username/email or password.')
      } else {
        setError(err instanceof Error ? err.message : 'Login failed.')
      }
    } finally {
      setBusy(false)
    }
  }

  const handleSetup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!setupCompanyId.trim() || !setupCompanyName.trim() || !adminUsername.trim() || !adminEmail.trim() || !adminPassword.trim()) {
      setError('All fields are required for initial setup.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const client = new ApiClient(apiUrl.trim(), '')
      const res = await client.setup({
        company_id: setupCompanyId.trim(),
        company_name: setupCompanyName.trim(),
        admin_username: adminUsername.trim(),
        admin_email: adminEmail.trim(),
        admin_password: adminPassword.trim(),
      })
      onLogin({
        apiUrl: apiUrl.trim(),
        token: res.token,
        role: res.user.role,
        companyId: res.user.company_id,
        username: res.user.username,
        email: res.user.email,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Initial setup failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newPassword || newPassword.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    if (!changePwdUser) return
    setBusy(true)
    setError(null)
    try {
      const client = new ApiClient(apiUrl.trim(), changePwdUser.token, changePwdUser.companyId)
      await client.changePassword(oldPassword, newPassword)
      onLogin({
        apiUrl: apiUrl.trim(),
        token: changePwdUser.token,
        role: changePwdUser.role,
        companyId: changePwdUser.companyId,
        username: changePwdUser.username,
        email: changePwdUser.email,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Password change failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        {/* Brand */}
        <div className="login-brand">
          <div className="brand-mark"><Activity size={22} strokeWidth={2.4} /></div>
          <div>
            <p className="brand-title">Northstar</p>
            <p className="brand-caption">SUPPLY CHAIN RISK CONSOLE</p>
          </div>
        </div>

        {error && (
          <div role="alert" className="mb-4 flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-xs text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300">
            <AlertCircle size={15} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {checkingSetup ? (
          <div className="py-12 text-center">
            <Loader2 size={24} className="mx-auto animate-spin text-sky-500" />
            <p className="mt-2 text-xs text-muted">Connecting to system...</p>
          </div>
        ) : changePwdUser ? (
          <div>
            <h1 className="login-title">Change Password Required</h1>
            <p className="login-subtitle">
              You are logging in with a temporary password. Please set a new secure password (minimum 8 characters).
            </p>
            <form onSubmit={handleChangePassword} className="login-form mt-4">
              <label className="form-label">
                Current temporary password
                <input
                  type="password"
                  required
                  className="text-input mt-1.5"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                />
              </label>
              <label className="form-label">
                New password
                <input
                  type="password"
                  required
                  minLength={8}
                  className="text-input mt-1.5"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Minimum 8 characters"
                />
              </label>
              <label className="form-label">
                Confirm new password
                <input
                  type="password"
                  required
                  minLength={8}
                  className="text-input mt-1.5"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat new password"
                />
              </label>
              <button
                type="submit"
                disabled={busy}
                className="btn btn-primary mt-2 flex w-full items-center justify-center gap-2"
              >
                {busy && <Loader2 size={16} className="animate-spin" />}
                Save Password & Enter
              </button>
            </form>
          </div>
        ) : setupRequired ? (
          <div>
            <h1 className="login-title">First-Run System Setup</h1>
            <p className="login-subtitle">
              Initialize the autonomous risk monitoring system by registering your initial company and administrator account.
            </p>
            <form onSubmit={handleSetup} className="login-form mt-4 space-y-3">
              <div>
                <label className="form-label">Company ID</label>
                <input
                  type="text"
                  required
                  pattern="^[a-zA-Z0-9_-]+$"
                  placeholder="e.g. kaveri_foods"
                  className="text-input mt-1"
                  value={setupCompanyId}
                  onChange={(e) => setSetupCompanyId(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label">Company Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Kaveri Foods Ltd"
                  className="text-input mt-1"
                  value={setupCompanyName}
                  onChange={(e) => setSetupCompanyName(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label">Admin Username</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. admin"
                  className="text-input mt-1"
                  value={adminUsername}
                  onChange={(e) => setAdminUsername(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label">Admin Email</label>
                <input
                  type="email"
                  required
                  placeholder="e.g. admin@kaverifoods.com"
                  className="text-input mt-1"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label">Admin Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  placeholder="Minimum 8 characters"
                  className="text-input mt-1"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                />
              </div>
              <button
                type="submit"
                disabled={busy}
                className="btn btn-primary mt-3 flex w-full items-center justify-center gap-2"
              >
                {busy && <Loader2 size={16} className="animate-spin" />}
                Complete Initial Setup
              </button>
            </form>
          </div>
        ) : (
          <div>
            <h1 className="login-title">Sign In</h1>
            <p className="login-subtitle">
              Sign in with your email or username and password. Role permissions and company workspace are loaded automatically.
            </p>
            <form onSubmit={handleLogin} className="login-form mt-4 space-y-3.5">
              <div>
                <label className="form-label" htmlFor="login-username">Email or Username</label>
                <input
                  id="login-username"
                  type="text"
                  required
                  autoComplete="username"
                  placeholder="Username or email address"
                  className="text-input mt-1"
                  value={usernameOrEmail}
                  onChange={(e) => setUsernameOrEmail(e.target.value)}
                  autoFocus
                />
              </div>
              <div>
                <label className="form-label" htmlFor="login-password">Password</label>
                <input
                  id="login-password"
                  type="password"
                  required
                  autoComplete="current-password"
                  placeholder="Enter password"
                  className="text-input mt-1"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <button
                id="login-submit-button"
                type="submit"
                disabled={busy}
                className="btn btn-primary mt-2 flex w-full items-center justify-center gap-2"
              >
                {busy && <Loader2 size={16} className="animate-spin" />}
                Sign In
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  )
}
