import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Activity, AlertTriangle, ArrowDownUp, Bell, CheckCircle2, ChevronRight,
  CircleHelp, Clock3, Database, FileSearch, FileText, Gauge, History,
  LayoutDashboard, ListChecks, LoaderCircle, LockKeyhole, Moon, Network, RefreshCw,
  Search, Settings2, ShieldAlert, Sun, Truck, X, ClipboardCheck, Cpu, BarChart2,
  Box, Leaf, Users, Key, KeyRound, LogOut
} from 'lucide-react'
import { ApiClient, ApiError, defaultApiUrl } from './api/client'
import type { Action, Approval, FindingKind, Hypothesis, Incident, IncidentDetail, Page, QualityItem, Recommendation, Role } from './api/types'
import { EvidenceState } from './components/EvidenceState'
import { HypothesisActions } from './components/HypothesisActions'
import { TypeBadge } from './components/TypeBadge'
import { ApprovalQueueScreen, HypothesisLedgerScreen } from './components/WorkflowScreens'
import { ActivityScreen, AuditScreen, ModelsScreen, SettingsScreen } from './components/RecordScreens'
import { NotFoundPage } from './components/NotFoundPage'
import { LoginScreen, type LoginValues } from './components/LoginScreen'
import { CompanySwitcher, type CompanyContext } from './components/CompanySwitcher'
import { DataSourcesScreen } from './components/DataSourcesScreen'
import { MonitoringScreen } from './components/MonitoringScreen'
import { PredictionsScreen } from './components/PredictionsScreen'
import { SupplyGraphScreen } from './components/SupplyGraphScreen'
import { RecommendationsScreen } from './components/RecommendationsScreen'
import { SystemHealthScreen } from './components/SystemHealthScreen'
import { UsersScreen } from './components/UsersScreen'
import { ApiKeysScreen } from './components/ApiKeysScreen'
import { ProjectSelector } from './components/ProjectSelector'
import './style.css'

type Screen =
  | 'overview'
  | 'incidents'
  | 'graph'
  | 'hypotheses'
  | 'approvals'
  | 'activity'
  | 'models'
  | 'audit'
  | 'settings'
  | 'datasources'
  | 'monitoring'
  | 'predictions'
  | 'supply-graph'
  | 'recommendations'
  | 'system-health'
  | 'users'
  | 'api-keys'
  | 'notFound'

type SessionSettings = {
  apiUrl: string
  token: string
  role: Role
  companyId: string
  username: string
  email: string
}

type LoadState<T> = { value: T | null; loading: boolean; error: string | null }
const blank = <T,>(): LoadState<T> => ({ value: null, loading: false, error: null })
const sessionKey = 'risk-console-session'
const companyKey = 'risk-console-company'
const DependencyGraph = lazy(() => import('./components/DependencyGraph').then((module) => ({ default: module.DependencyGraph })))

const screenPaths: Record<Exclude<Screen, 'notFound'>, string> = {
  overview: '/',
  incidents: '/incidents',
  graph: '/graph',
  hypotheses: '/hypotheses',
  approvals: '/approvals',
  activity: '/activity',
  models: '/models',
  audit: '/audit',
  settings: '/settings',
  datasources: '/datasources',
  monitoring: '/monitoring',
  predictions: '/predictions',
  'supply-graph': '/supply-graph',
  recommendations: '/recommendations',
  'system-health': '/system-health',
  users: '/users',
  'api-keys': '/api-keys',
}

function routeFromPath(): { screen: Screen; incidentId: string | null } {
  const path = window.location.pathname
  if (path === '/' || path === '/overview') return { screen: 'overview', incidentId: null }
  if (path === '/incidents') return { screen: 'incidents', incidentId: null }
  const match = path.match(/^\/incidents\/([^/]+)$/)
  if (match) {
    try {
      return { screen: 'incidents', incidentId: decodeURIComponent(match[1]) }
    } catch {
      return { screen: 'notFound', incidentId: null }
    }
  }
  const entry = Object.entries(screenPaths).find(([, route]) => route === path)
  return entry ? { screen: entry[0] as Screen, incidentId: null } : { screen: 'notFound', incidentId: null }
}

function readSession(): SessionSettings {
  try {
    const saved = JSON.parse(sessionStorage.getItem(sessionKey) || '{}') as Partial<SessionSettings>
    return {
      apiUrl: saved.apiUrl || defaultApiUrl,
      token: saved.token || '',
      role: saved.role || 'viewer',
      companyId: saved.companyId || 'local',
      username: saved.username || '',
      email: saved.email || '',
    }
  } catch {
    return { apiUrl: defaultApiUrl, token: '', role: 'viewer', companyId: 'local', username: '', email: '' }
  }
}

function readCompany(): CompanyContext {
  try {
    return JSON.parse(sessionStorage.getItem(companyKey) || '{}') as CompanyContext
  } catch {
    return { companyId: 'local', workspaceName: '', projectId: '' }
  }
}

function formatDate(value?: string) {
  if (!value) return 'UNKNOWN'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function listOf<T>(page: Page<T> | null): T[] {
  return page?.items ?? []
}

function serialized(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

function Meta({ source, refs, version, timestamp, limitations }: { source?: string; refs?: string[]; version?: string; timestamp?: string; limitations?: string[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-3 text-[11px] text-muted dark:border-slate-800 dark:text-slate-400">
      <span>Source: {source || 'UNKNOWN'}</span>
      <span>Records: {refs?.length ? refs.join(', ') : 'UNKNOWN'}</span>
      <span>Model / rule: {version || 'UNKNOWN'}</span>
      <span>Time: {formatDate(timestamp)}</span>
      <span>Limitations: {limitations?.length ? limitations.join('; ') : 'UNKNOWN'}</span>
    </div>
  )
}

function ValueCard({ title, value, kind = 'FACT', icon, tone = 'blue', detail }: { title: string; value: string | number; kind?: FindingKind; icon: ReactNode; tone?: string; detail: string }) {
  return (
    <article className="panel p-5">
      <div className="flex items-start justify-between">
        <span className="text-sm font-medium text-muted dark:text-slate-400">{title}</span>
        <span className={`icon-tile tone-${tone}`}>{icon}</span>
      </div>
      <div className="mt-4 flex items-center gap-2">
        <p className="text-3xl font-semibold tracking-tight text-ink dark:text-white">{value}</p>
        <TypeBadge kind={kind} />
      </div>
      <p className="mt-1 text-xs text-muted dark:text-slate-400">{detail}</p>
    </article>
  )
}

function EmptyPanel({ title, message, icon = <CircleHelp size={18} /> }: { title: string; message: string; icon?: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{message}</p>
    </div>
  )
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-100">
      <div className="flex items-center gap-2 font-semibold">
        <AlertTriangle size={16} />Could not load backend data
      </div>
      <p className="mt-1 break-words">{message}</p>
      <button className="mt-3 text-xs font-bold underline" onClick={onRetry}>Retry</button>
    </div>
  )
}

function ChangePasswordModal({ client, onClose }: { client: ApiClient; onClose: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match')
      return
    }
    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters')
      return
    }
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      await client.changePassword(currentPassword, newPassword)
      setSuccess('Password updated successfully.')
      setTimeout(() => onClose(), 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="relative mx-auto mt-24 max-w-md rounded-2xl border border-line bg-surface p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900" role="dialog" aria-modal="true">
        <div className="flex items-center justify-between pb-3 border-b border-line dark:border-slate-800">
          <h3 className="text-base font-semibold text-ink dark:text-white">Change Password</h3>
          <button className="icon-button" onClick={onClose}><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {error && <div className="ds-err text-xs"><AlertTriangle size={14} /><span>{error}</span></div>}
          {success && <div className="rounded-lg bg-emerald-500/10 p-2.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">{success}</div>}
          <label className="form-label text-xs">
            Current password
            <input
              type="password"
              required
              className="text-input mt-1"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </label>
          <label className="form-label text-xs">
            New password
            <input
              type="password"
              required
              className="text-input mt-1"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </label>
          <label className="form-label text-xs">
            Confirm new password
            <input
              type="password"
              required
              className="text-input mt-1"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" disabled={busy} className="primary-button">
              {busy ? <LoaderCircle size={14} className="animate-spin" /> : 'Update password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function App() {
  const [session, setSession] = useState<SessionSettings>(readSession)
  const [company, setCompany] = useState<CompanyContext>(() => ({ ...readCompany(), companyId: readSession().companyId || 'local' }))
  const [screen, setScreen] = useState<Screen>(() => routeFromPath().screen)
  const [selected, setSelected] = useState<string | null>(() => routeFromPath().incidentId)
  const [dark, setDark] = useState(() => sessionStorage.getItem('risk-console-theme') === 'dark')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<'newest' | 'oldest' | 'title'>('newest')
  const [severity, setSeverity] = useState('all')
  const [status, setStatus] = useState('all')
  const [health, setHealth] = useState<LoadState<{ status: string; api_version: string }>>(blank())
  const [incidents, setIncidents] = useState<LoadState<Page<Incident>>>(blank())
  const [quality, setQuality] = useState<LoadState<Page<QualityItem>>>(blank())
  const [recommendations, setRecommendations] = useState<LoadState<Page<Recommendation>>>(blank())
  const [actions, setActions] = useState<LoadState<Page<Action>>>(blank())
  const [approvals, setApprovals] = useState<LoadState<Page<Approval>>>(blank())
  const [detail, setDetail] = useState<LoadState<IncidentDetail>>(blank())
  const [killSwitch, setKillSwitch] = useState<LoadState<{ enabled: boolean }>>(blank())
  const [confirming, setConfirming] = useState<string | null>(null)
  const [rationales, setRationales] = useState<Record<string, string>>({})
  const [refreshing, setRefreshing] = useState(false)
  const [knownSources, setKnownSources] = useState<string[]>([])
  const [expiredMsg, setExpiredMsg] = useState<string | null>(null)
  const [changePwdOpen, setChangePwdOpen] = useState(false)

  // Show login gate when no token is present
  const needsLogin = !session.token.trim()

  const client = useMemo(
    () => new ApiClient(session.apiUrl, session.token, company.companyId || 'local'),
    [session.apiUrl, session.token, company.companyId],
  )

  const handleAuthError = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      setExpiredMsg('Your session has expired. Please sign in again.')
      sessionStorage.removeItem(sessionKey)
      setSession({ apiUrl: session.apiUrl, token: '', role: 'viewer', companyId: 'local', username: '', email: '' })
      return 'Session expired'
    }
    return errorText(err)
  }, [session.apiUrl])

  function handleLogin(values: LoginValues) {
    const newSession: SessionSettings = {
      apiUrl: values.apiUrl,
      token: values.token,
      role: values.role,
      companyId: values.companyId,
      username: values.username,
      email: values.email,
    }
    sessionStorage.setItem(sessionKey, JSON.stringify(newSession))
    setSession(newSession)
    setExpiredMsg(null)
    const newCompany: CompanyContext = { companyId: values.companyId, workspaceName: '', projectId: company.projectId || '' }
    sessionStorage.setItem(companyKey, JSON.stringify(newCompany))
    setCompany(newCompany)
  }

  function handleLogout() {
    sessionStorage.removeItem(sessionKey)
    setSession({ apiUrl: session.apiUrl, token: '', role: 'viewer', companyId: 'local', username: '', email: '' })
    setExpiredMsg(null)
  }

  function handleCompanyChange(ctx: CompanyContext) {
    setCompany(ctx)
    sessionStorage.setItem(companyKey, JSON.stringify(ctx))
    const newSession = { ...session, companyId: ctx.companyId }
    sessionStorage.setItem(sessionKey, JSON.stringify(newSession))
    setSession(newSession)
  }

  const navItems: Array<{ id: Exclude<Screen, 'notFound'>; label: string; icon: ReactNode; section?: string }> = useMemo(() => [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={17} />, section: 'MONITOR' },
    { id: 'incidents', label: 'Incidents', icon: <ShieldAlert size={17} /> },
    { id: 'monitoring', label: 'Monitoring', icon: <Activity size={17} /> },
    { id: 'predictions', label: 'Predictions', icon: <BarChart2 size={17} /> },
    { id: 'supply-graph', label: 'Supply graph', icon: <Box size={17} />, section: 'INVESTIGATE' },
    { id: 'graph', label: 'Incident graph', icon: <Network size={17} /> },
    { id: 'hypotheses', label: 'Hypotheses', icon: <ListChecks size={17} /> },
    { id: 'datasources', label: 'Data sources', icon: <Database size={17} />, section: 'DATA' },
    { id: 'recommendations', label: 'Recommendations', icon: <ClipboardCheck size={17} />, section: 'WORKFLOW' },
    { id: 'approvals', label: 'Approval queue', icon: <Leaf size={17} /> },
    { id: 'activity', label: 'Alerts & outcomes', icon: <History size={17} /> },
    { id: 'system-health', label: 'System health', icon: <Cpu size={17} />, section: 'GOVERNANCE' },
    { id: 'models', label: 'Models & eval', icon: <Gauge size={17} /> },
    { id: 'audit', label: 'Audit log', icon: <FileSearch size={17} /> },
    { id: 'settings', label: 'Settings', icon: <Settings2 size={17} /> },
    ...(session.role === 'admin'
      ? [
          { id: 'users' as const, label: 'Users', icon: <Users size={17} />, section: 'ADMIN' },
          { id: 'api-keys' as const, label: 'API Keys', icon: <Key size={17} /> },
        ]
      : []),
  ], [session.role])

  function navigate(to: Screen) {
    if (to === 'notFound') return
    window.history.pushState({}, '', screenPaths[to])
    setScreen(to)
    setSelected(null)
  }

  const connected = health.value?.status === 'ok'
  const items = listOf(incidents.value)
  const recs = listOf(recommendations.value)
  const incidentRecs = recs.filter((item) => item.incident_id === selected)
  const relatedRecIds = new Set(incidentRecs.map((item) => item.id))
  const relatedActions = listOf(actions.value).filter((item) => relatedRecIds.has(item.recommendation_id))
  const relatedApprovals = listOf(approvals.value).filter((item) => relatedRecIds.has(item.recommendation_id))
  const dryRunKnown = listOf(actions.value).some((action) => action.dry_run || action.status === 'DRY_RUN')

  const refresh = useCallback(async () => {
    if (!session.token) return
    setRefreshing(true)
    setHealth((state) => ({ ...state, loading: true, error: null }))
    const tasks = [
      client.health().then((value) => setHealth({ value, loading: false, error: null })).catch((err: unknown) => setHealth({ value: null, loading: false, error: handleAuthError(err) })),
      client.incidents().then((value) => setIncidents({ value, loading: false, error: null })).catch((err: unknown) => setIncidents({ value: null, loading: false, error: handleAuthError(err) })),
      client.quality().then((value) => setQuality({ value, loading: false, error: null })).catch((err: unknown) => setQuality({ value: null, loading: false, error: handleAuthError(err) })),
      client.recommendations().then((value) => setRecommendations({ value, loading: false, error: null })).catch((err: unknown) => setRecommendations({ value: null, loading: false, error: handleAuthError(err) })),
      client.actions().then((value) => setActions({ value, loading: false, error: null })).catch((err: unknown) => setActions({ value: null, loading: false, error: handleAuthError(err) })),
      client.approvals().then((value) => setApprovals({ value, loading: false, error: null })).catch((err: unknown) => setApprovals({ value: null, loading: false, error: handleAuthError(err) })),
      client.datasets().then((p) => setKnownSources(p.items.map((s) => s.dataset_name).filter(Boolean) as string[])).catch(() => { /* non-fatal */ }),
    ]
    if (session.role === 'admin') {
      tasks.push(client.killSwitch().then((value) => setKillSwitch({ value, loading: false, error: null })).catch((err: unknown) => setKillSwitch({ value: null, loading: false, error: handleAuthError(err) })))
    } else {
      setKillSwitch({ value: null, loading: false, error: 'Admin role required by the API contract.' })
    }
    await Promise.all(tasks)
    setRefreshing(false)
  }, [client, session.token, session.role, handleAuthError])

  const loadDetail = useCallback((id: string) => {
    if (window.location.pathname !== `/incidents/${encodeURIComponent(id)}`) {
      window.history.pushState({}, '', `/incidents/${encodeURIComponent(id)}`)
    }
    setSelected(id)
    setScreen('incidents')
  }, [])

  const fetchDetail = useCallback(async (id: string) => {
    setDetail({ value: null, loading: true, error: null })
    try {
      setDetail({ value: await client.incident(id), loading: false, error: null })
    } catch (error) {
      setDetail({ value: null, loading: false, error: handleAuthError(error) })
    }
  }, [client, handleAuthError])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    sessionStorage.setItem('risk-console-theme', dark ? 'dark' : 'light')
  }, [dark])
  useEffect(() => {
    if (selected) void fetchDetail(selected)
    else setDetail(blank())
  }, [selected, fetchDetail])
  useEffect(() => {
    const syncRoute = () => {
      const route = routeFromPath()
      setScreen(route.screen)
      setSelected(route.incidentId)
    }
    window.addEventListener('popstate', syncRoute)
    return () => window.removeEventListener('popstate', syncRoute)
  }, [])

  const filtered = [...items]
    .filter((item) => `${item.title} ${item.description} ${item.source} ${item.id}`.toLowerCase().includes(search.toLowerCase()))
    .filter(() => severity === 'all' || severity === 'unavailable')
    .filter(() => status === 'all' || status === 'unavailable')
    .sort((a, b) =>
      sort === 'title' ? a.title.localeCompare(b.title) : sort === 'oldest' ? Date.parse(a.occurred_at) - Date.parse(b.occurred_at) : Date.parse(b.occurred_at) - Date.parse(a.occurred_at)
    )

  async function confirmHypothesis(hypothesis: Hypothesis) {
    const rationale = rationales[hypothesis.id]?.trim()
    if (!rationale || session.role !== 'reviewer' && session.role !== 'admin') return
    setConfirming(hypothesis.id)
    try {
      await client.confirmHypothesis(hypothesis.id, rationale)
      if (selected) await fetchDetail(selected)
    } catch (error) {
      setDetail((state) => ({ ...state, error: errorText(error) }))
    } finally {
      setConfirming(null)
    }
  }

  // Show login page when no authenticated token is available
  if (needsLogin) return <LoginScreen onLogin={handleLogin} expiredMessage={expiredMsg} />

  return (
    <div className="app-frame min-h-screen bg-canvas text-ink dark:bg-[#0a1020] dark:text-slate-100">
      <aside className="sidebar" style={{ overflowY: 'auto' }}>
        <div className="brand">
          <div className="brand-mark"><Activity size={19} strokeWidth={2.4} /></div>
          <div>
            <p className="brand-title">Northstar</p>
            <p className="brand-caption">RISK OPERATIONS</p>
          </div>
        </div>
        <nav aria-label="Main navigation" className="space-y-1">
          {navItems.map((entry) => (
            <div key={entry.id}>
              {entry.section && <div className="sidebar-section-label">{entry.section}</div>}
              <button
                className={`nav-link ${screen === entry.id || (selected && entry.id === 'incidents') ? 'nav-active' : ''}`}
                onClick={() => navigate(entry.id)}
              >
                {entry.icon}{entry.label}
                {entry.id === 'incidents' && <span className="nav-count">{incidents.value?.count ?? '—'}</span>}
              </button>
            </div>
          ))}
        </nav>
        <div className="side-status">
          <span className={`status-dot ${connected ? 'bg-emerald-500' : 'bg-slate-400'}`} />
          {connected ? 'Backend connected' : 'Not connected'}
        </div>
        <CompanySwitcher context={company} onChange={handleCompanyChange} />
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <LockKeyhole size={15} />
            <span>Local API only<br /><small>No external services</small></span>
          </div>
          <div className="profile-row">
            <div className="avatar">{(session.username || session.role).slice(0, 1).toUpperCase()}</div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-ink dark:text-white">{session.username || session.email}</p>
              <p className="text-[10px] text-muted dark:text-slate-400 capitalize">{session.role} · {company.companyId}</p>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="min-w-0">
            <p className="eyebrow">SUPPLY CHAIN INTELLIGENCE</p>
            <h1>
              {selected
                ? 'Incident investigation'
                : screen === 'overview'
                ? 'Operations overview'
                : (navItems.find((entry) => entry.id === screen)?.label || 'Page not found')}
            </h1>
          </div>
          <div className="top-actions flex items-center gap-3">
            {/* Project Selector */}
            <ProjectSelector
              client={client}
              currentProjectId={company.projectId}
              onSelectProject={(p) => handleCompanyChange({ ...company, projectId: p.id })}
            />

            <div className={`connection-pill ${connected ? 'connected' : ''}`}>
              <span className={`status-dot ${connected ? 'bg-emerald-500' : 'bg-slate-400'}`} />
              {connected ? 'API online' : 'API offline'}
            </div>
            <div className={`switch-pill ${killSwitch.value?.enabled ? 'switch-on' : ''}`}>
              <span className="switch-indicator" />
              Kill switch: {killSwitch.value ? (killSwitch.value.enabled ? 'ON' : 'OFF') : 'UNKNOWN'}
              {killSwitch.value && <TypeBadge kind="FACT" />}
            </div>

            {/* User Badge & Profile */}
            <div className="flex items-center gap-2 rounded-xl border border-line bg-surface/50 px-3 py-1.5 dark:border-slate-800">
              <div className="text-right">
                <p className="text-xs font-semibold leading-tight text-ink dark:text-white">{session.username || session.email || 'User'}</p>
                <p className="text-[10px] text-muted">{company.companyId}</p>
              </div>
              <span
                className="rounded-md bg-brand/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-brand"
                title={`Role: ${session.role}`}
              >
                {session.role}
              </span>
              <button
                className="icon-button ml-1 p-1 text-muted hover:text-ink"
                title="Change password"
                onClick={() => setChangePwdOpen(true)}
              >
                <KeyRound size={15} />
              </button>
              <button
                className="icon-button p-1 text-rose-500 hover:text-rose-700"
                title="Sign out"
                onClick={handleLogout}
              >
                <LogOut size={15} />
              </button>
            </div>

            <button className="icon-button" aria-label="Toggle theme" onClick={() => setDark(!dark)}>
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button className="icon-button" aria-label="Refresh data" onClick={() => void refresh()} disabled={refreshing}>
              {refreshing ? <LoaderCircle size={17} className="animate-spin" /> : <RefreshCw size={16} />}
            </button>
          </div>
        </header>

        {dryRunKnown && (
          <div className="dry-banner" role="status">
            <span className="dry-banner-icon"><ShieldAlert size={16} /></span>
            <div>
              <strong>DRY-RUN MODE CONFIRMED</strong>
              <span>Backend action history contains dry-run records. No external action has been executed.</span>
            </div>
            <TypeBadge kind="FACT" />
          </div>
        )}
        {!dryRunKnown && (
          <div className="mode-unknown" role="status">
            <span className="status-dot bg-amber-500" />
            Configured dry-run state is unavailable from the API contract.
          </div>
        )}

        <div className="content-area">
          {health.error && <div className="mb-5"><ErrorPanel message={health.error} onRetry={() => void refresh()} /></div>}
          {screen === 'notFound' ? <NotFoundPage goHome={() => navigate('overview')} />
            : selected ? <IncidentView detail={detail} recommendations={incidentRecs} actions={relatedActions} approvals={relatedApprovals} role={session.role} rationales={rationales} setRationales={setRationales} confirmHypothesis={confirmHypothesis} confirming={confirming} onBack={() => navigate('incidents')} retry={() => void fetchDetail(selected)} />
            : screen === 'overview' ? <Overview incidents={incidents} quality={quality} onOpen={() => navigate('incidents')} retry={() => void refresh()} />
            : screen === 'incidents' ? <IncidentList state={incidents} filtered={filtered} search={search} setSearch={setSearch} sort={sort} setSort={setSort} severity={severity} setSeverity={setSeverity} status={status} setStatus={setStatus} open={(id) => void loadDetail(id)} retry={() => void refresh()} />
            : screen === 'graph' ? <Suspense fallback={<LoadingState large />}><DependencyGraph client={client} incidents={items} /></Suspense>
            : screen === 'hypotheses' ? <HypothesisLedgerScreen client={client} role={session.role} incidents={items} />
            : screen === 'approvals' ? <ApprovalQueueScreen client={client} role={session.role} />
            : screen === 'activity' ? <ActivityScreen client={client} />
            : screen === 'models' ? <ModelsScreen client={client} />
            : screen === 'audit' ? <AuditScreen client={client} role={session.role} />
            : screen === 'datasources' ? <DataSourcesScreen client={client} role={session.role} />
            : screen === 'monitoring' ? <MonitoringScreen client={client} role={session.role} knownSources={knownSources} />
            : screen === 'predictions' ? <PredictionsScreen client={client} />
            : screen === 'supply-graph' ? <SupplyGraphScreen client={client} projectId={company.projectId} />
            : screen === 'recommendations' ? <RecommendationsScreen client={client} role={session.role} />
            : screen === 'system-health' ? <SystemHealthScreen client={client} role={session.role} onAudit={() => navigate('audit')} />
            : screen === 'users' ? <UsersScreen client={client} />
            : screen === 'api-keys' ? <ApiKeysScreen client={client} />
            : <SettingsScreen client={client} role={session.role} apiUrl={session.apiUrl} onSaveUrl={(apiUrl) => setSession({ ...session, apiUrl })} dark={dark} onToggleTheme={() => setDark(!dark)} onKillSwitch={(enabled) => setKillSwitch({ value: { enabled }, loading: false, error: null })} />}
        </div>
        <footer className="footer">
          <span>Supply Chain Risk Console</span>
          <span>Backend: {session.apiUrl} · Company: {company.companyId} · Role: {session.role}</span>
        </footer>
      </main>
      {changePwdOpen && <ChangePasswordModal client={client} onClose={() => setChangePwdOpen(false)} />}
    </div>
  )
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? `${error.message}${error.status ? ` (HTTP ${error.status})` : ''}` : error instanceof Error ? error.message : 'Unknown request error'
}

function Overview({ incidents, quality, onOpen, retry }: { incidents: LoadState<Page<Incident>>; quality: LoadState<Page<QualityItem>>; onOpen: () => void; retry: () => void }) {
  const rows = listOf(quality.value)
  const warnings = rows.filter((item) => !item.fresh || Object.values(item.null_rates).some((rate) => rate > 0))
  return (
    <div className="space-y-7">
      <section className="page-intro">
        <div>
          <p className="eyebrow">MONITORING / SUMMARY</p>
          <h2>Supply network at a glance</h2>
          <p>Evidence-led monitoring across the connected local data sources.</p>
        </div>
        <button className="primary-button" onClick={onOpen}>
          <ShieldAlert size={16} />View incidents<ChevronRight size={16} />
        </button>
      </section>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <ValueCard title="Stored incidents" value={incidents.value?.count ?? (incidents.loading ? '…' : '—')} icon={<ShieldAlert size={17} />} tone="blue" detail="Persisted incident records" />
        <ValueCard title="Severity breakdown" value="Unavailable" icon={<Gauge size={17} />} tone="violet" detail="Incident schema does not expose severity" />
        <ValueCard title="Quality / freshness flags" value={quality.value ? warnings.length : quality.loading ? '…' : '—'} icon={<Database size={17} />} tone="amber" detail="Rows stale or with observed nulls" />
        <ValueCard title="Latest pipeline run" value="Unavailable" icon={<Clock3 size={17} />} tone="green" detail="No pipeline run history endpoint" />
      </section>
      {(incidents.error || quality.error) && <ErrorPanel message={incidents.error || quality.error || ''} onRetry={retry} />}
      <section className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <div className="panel overflow-hidden">
          <div className="panel-heading">
            <div>
              <div className="flex items-center gap-2"><h3>Data source health</h3><TypeBadge kind="FACT" /></div>
              <p>Freshness and recorded null rates reported by the API</p>
            </div>
            <Database size={18} className="text-muted" />
          </div>
          {quality.loading ? (
            <LoadingState />
          ) : rows.length === 0 ? (
            <EmptyPanel title="No quality snapshots" message={quality.error ? 'Quality data could not be loaded.' : 'The API has not stored any data-quality snapshots.'} />
          ) : (
            <div className="divide-y divide-line dark:divide-slate-800">
              {rows.map((row) => (
                <div className="quality-row" key={`${row.source}-${row.observed_at}`}>
                  <div className="dataset-mark"><Truck size={15} /></div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-ink dark:text-slate-100">{row.source}</p>
                    <p className="text-xs text-muted dark:text-slate-400">{row.row_count.toLocaleString()} rows · observed {formatDate(row.observed_at)}</p>
                  </div>
                  <div className={`fresh-pill ${row.fresh ? 'fresh' : 'stale'}`}>{row.fresh ? 'Fresh' : 'Stale'}</div>
                  <TypeBadge kind="FACT" />
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="panel p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-ink dark:text-white">Monitoring posture</h3>
              <p className="mt-1 text-xs text-muted dark:text-slate-400">System values are sourced from the local API</p>
            </div>
            <Activity size={18} className="text-brand" />
          </div>
          <div className="mt-5 space-y-3">
            <PostureRow label="API connection" value={incidents.error ? 'Unavailable' : 'Local backend'} detail={incidents.error || 'Health endpoint is used to verify connectivity.'} />
            <PostureRow label="Kill switch" value="Role-restricted / unknown" detail="Read endpoint is admin-only." />
            <PostureRow label="Dry-run configuration" value="Not exposed" detail="History confirms past dry-run records only." />
          </div>
          <div className="mt-5 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-muted dark:bg-slate-900 dark:text-slate-400">
            This console does not infer missing severity, causality, or current execution settings from historical records.
          </div>
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <div className="flex items-center gap-2"><h3>Recent incident activity</h3><TypeBadge kind="FACT" /></div>
            <p>Newest incident records from the API</p>
          </div>
          <button className="text-xs font-semibold text-brand" onClick={onOpen}>View all</button>
        </div>
        {incidents.loading ? (
          <LoadingState />
        ) : incidents.value?.items.length ? (
          incidents.value.items.slice(0, 4).map((item) => <IncidentRow key={item.id} item={item} open={onOpen} />)
        ) : (
          <EmptyPanel title="No stored incidents" message="Incident records will appear after they are persisted by a local pipeline run." />
        )}
      </section>
    </div>
  )
}

function PostureRow({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-line p-3 dark:border-slate-800">
      <div>
        <p className="text-xs font-semibold text-ink dark:text-slate-100">{label}</p>
        <p className="mt-1 text-[11px] text-muted dark:text-slate-400">{detail}</p>
      </div>
      <span className="whitespace-nowrap text-[11px] font-semibold text-muted">{value}</span>
    </div>
  )
}

function IncidentRow({ item, open }: { item: Incident; open: () => void }) {
  return (
    <button className="incident-row w-full text-left" onClick={open}>
      <span className="incident-status-icon"><AlertTriangle size={16} /></span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <TypeBadge kind="FACT" />
          <p className="truncate text-sm font-semibold text-ink dark:text-white">{item.title}</p>
        </div>
        <p className="mt-1 truncate text-xs text-muted dark:text-slate-400">
          {item.source} · {item.record_refs?.length ? item.record_refs.join(', ') : 'record refs unavailable'}
        </p>
      </div>
      <div className="hidden text-right sm:block">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">Severity</span>
        <p className="text-xs font-medium text-muted">Not supplied</p>
      </div>
      <span className="whitespace-nowrap text-xs text-muted">{formatDate(item.occurred_at)}</span>
      <ChevronRight size={16} className="text-muted" />
    </button>
  )
}

function IncidentList({
  state, filtered, search, setSearch, sort, setSort, severity, setSeverity, status, setStatus, open, retry,
}: {
  state: LoadState<Page<Incident>>
  filtered: Incident[]
  search: string
  setSearch: (s: string) => void
  sort: 'newest' | 'oldest' | 'title'
  setSort: (s: 'newest' | 'oldest' | 'title') => void
  severity: string
  setSeverity: (s: string) => void
  status: string
  setStatus: (s: string) => void
  open: (id: string) => void
  retry: () => void
}) {
  return (
    <div className="space-y-6">
      <section className="page-intro">
        <div>
          <p className="eyebrow">MONITORING / INCIDENTS</p>
          <h2>Incident register</h2>
          <p>Browse persisted incidents and open their evidence trace.</p>
        </div>
        <span className="count-chip"><TypeBadge kind="FACT" />{state.value?.count ?? '—'} records</span>
      </section>
      <section className="panel">
        <div className="filter-bar">
          <label className="search-box">
            <Search size={16} />
            <input aria-label="Search incidents" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search title, source or record ID" />
          </label>
          <label className="filter-select">
            <span>Severity</span>
            <select aria-label="Filter by severity" value={severity} onChange={(event) => setSeverity(event.target.value)}>
              <option value="all">All / unavailable</option>
              <option value="unavailable">Not supplied</option>
            </select>
          </label>
          <label className="filter-select">
            <span>Status</span>
            <select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="all">All / unavailable</option>
              <option value="unavailable">Not supplied</option>
            </select>
          </label>
          <label className="filter-select">
            <span>Sort</span>
            <select aria-label="Sort incidents" value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="title">Title A–Z</option>
            </select>
          </label>
          <ArrowDownUp size={15} className="hidden text-muted lg:block" />
        </div>
        {state.loading ? (
          <LoadingState />
        ) : state.error ? (
          <div className="p-5"><ErrorPanel message={state.error} onRetry={retry} /></div>
        ) : filtered.length ? (
          <div>{filtered.map((item) => <IncidentRow key={item.id} item={item} open={() => open(item.id)} />)}</div>
        ) : (
          <EmptyPanel
            title="No matching incidents"
            message={state.value?.count ? 'Adjust the search or filters to see other records.' : 'No incident records are currently stored in the backend.'}
            icon={<Search size={18} />}
          />
        )}
      </section>
      <p className="text-xs text-muted dark:text-slate-500">
        Severity and status filters are present for the workflow; the current Incident response schema does not provide either field.
      </p>
    </div>
  )
}

function IncidentView({
  detail, recommendations, actions, approvals, role, rationales, setRationales, confirmHypothesis, confirming, onBack, retry,
}: {
  detail: LoadState<IncidentDetail>
  recommendations: Recommendation[]
  actions: Action[]
  approvals: Approval[]
  role: Role
  rationales: Record<string, string>
  setRationales: (v: Record<string, string>) => void
  confirmHypothesis: (h: Hypothesis) => void
  confirming: string | null
  onBack: () => void
  retry: () => void
}) {
  const item = detail.value
  if (detail.loading) return <LoadingState large />
  if (detail.error && !item) return <div className="space-y-4"><button className="back-link" onClick={onBack}>← Back to incidents</button><ErrorPanel message={detail.error} onRetry={retry} /></div>
  if (!item) return <EmptyPanel title="Incident unavailable" message="The API did not return an incident detail record." />
  const prediction = item.explanation.prediction as Record<string, unknown> | null | undefined
  const storedExplanation = item.explanation.stored_explanation
  const evidence = item.evidence ?? []

  const canConfirm = role === 'reviewer' || role === 'admin'

  return (
    <div className="space-y-6">
      <button className="back-link" onClick={onBack}>← Back to incidents</button>
      {detail.error && <ErrorPanel message={detail.error} onRetry={retry} />}
      <section className="panel p-6">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-start">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="severity-dot" />
              <TypeBadge kind="FACT" />
              <span className="text-xs font-semibold uppercase tracking-widest text-muted">Incident record</span>
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-ink dark:text-white">{item.title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted dark:text-slate-400">{item.description || 'No incident description was provided by the API.'}</p>
          </div>
          <div className="rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-900">
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted">Severity</p>
            <p className="mt-1 text-sm font-semibold text-muted">Not supplied</p>
          </div>
        </div>
        <Meta source={item.source} refs={item.record_refs} timestamp={item.occurred_at} limitations={item.limitations} />
      </section>
      <section className="grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
        <div className="space-y-5">
          <div className="panel">
            <div className="panel-heading">
              <div>
                <div className="flex items-center gap-2"><h3>Observed evidence</h3><TypeBadge kind="FACT" /></div>
                <p>Values returned from the incident evidence ledger</p>
              </div>
              <FileText size={18} className="text-muted" />
            </div>
            {evidence.length === 0 ? (
              <EmptyPanel title="No linked evidence records" message="The API returned no evidence linked to this incident." />
            ) : (
              evidence.map((entry) => (
                <div className="evidence-card" key={entry.id}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-ink dark:text-white">{entry.evidence_type || 'Observed evidence'}</p>
                      <p className="mt-1 text-xs text-muted">{entry.source} · {entry.record_refs?.length ? entry.record_refs.join(', ') : 'No source record references supplied'}</p>
                    </div>
                    <TypeBadge kind="FACT" />
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {Object.entries(entry.facts ?? {}).length ? (
                      Object.entries(entry.facts).map(([key, value]) => (
                        <div className="fact-cell" key={key}>
                          <span>{key.replaceAll('_', ' ')}</span>
                          <strong>{serialized(value)}</strong>
                        </div>
                      ))
                    ) : (
                      <div className="fact-cell sm:col-span-2">
                        <span>Observed values / baseline</span>
                        <strong>Not supplied in this evidence response.</strong>
                      </div>
                    )}
                  </div>
                  <Meta source={entry.source} refs={entry.record_refs} timestamp={entry.observed_at} limitations={[]} />
                </div>
              ))
            )}
          </div>
          <div className="panel">
            <div className="panel-heading">
              <div>
                <div className="flex items-center gap-2"><h3>Prediction & feature explanation</h3><TypeBadge kind="PREDICTION" /></div>
                <p>Model output is distinct from observed facts</p>
              </div>
              <Activity size={18} className="text-muted" />
            </div>
            {!prediction ? (
              <EmptyPanel title="No linked prediction" message="No prediction was attached to this incident response." />
            ) : (
              <div className="p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-2xl font-semibold text-ink dark:text-white">{String(prediction.value ?? 'UNKNOWN')}</span>
                  <span className="text-sm text-muted">{String(prediction.target ?? 'target unavailable')}</span>
                </div>
                <Meta
                  source={String(prediction.source || item.source)}
                  refs={Array.isArray(prediction.record_refs) ? (prediction.record_refs as string[]) : item.record_refs}
                  version={String(prediction.model_version_id || 'UNKNOWN')}
                  timestamp={String(prediction.predicted_at || '')}
                  limitations={Array.isArray(prediction.limitations) ? (prediction.limitations as string[]) : []}
                />
              </div>
            )}
            <div className="border-t border-line p-5 dark:border-slate-800">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">SHAP / feature contribution</h4>
              {storedExplanation && Object.keys(storedExplanation as object).length ? (
                <pre className="json-block mt-3">{serialized(storedExplanation)}</pre>
              ) : (
                <EvidenceState value="SHAP / feature explanation unavailable in the incident API response." />
              )}
              <p className="mt-3 text-xs italic text-muted dark:text-slate-400">feature contribution, not proven cause</p>
            </div>
          </div>
          <div className="panel">
            <div className="panel-heading">
              <div>
                <div className="flex items-center gap-2"><h3>Hypothesis ledger</h3><TypeBadge kind="HYPOTHESIS" /></div>
                <p>Review status and provenance from the backend</p>
              </div>
              <CircleHelp size={18} className="text-muted" />
            </div>
            {!item.hypotheses?.length ? (
              <EmptyPanel title="No hypotheses linked" message="No alternative cause has been recorded for this incident." />
            ) : (
              item.hypotheses.map((hypothesis) => (
                <div className="hypothesis-card" key={hypothesis.id}>
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                    <p className="text-sm font-medium leading-6 text-ink dark:text-slate-100">{hypothesis.statement}</p>
                    <div title={!canConfirm ? 'Requires reviewer role' : undefined}>
                      <HypothesisActions
                        status={hypothesis.status}
                        role={role}
                        disabled={!canConfirm || !rationales[hypothesis.id]?.trim() || confirming === hypothesis.id}
                        onConfirm={() => confirmHypothesis(hypothesis)}
                      />
                    </div>
                  </div>
                  <Meta source={hypothesis.source} refs={hypothesis.record_refs} timestamp={hypothesis.review_history?.at(-1)?.reviewed_at} limitations={[]} />
                  {hypothesis.status !== 'CONFIRMED' && canConfirm && (
                    <div className="mt-3">
                      <input
                        aria-label={`Reviewer rationale ${hypothesis.id}`}
                        className="text-input"
                        value={rationales[hypothesis.id] || ''}
                        onChange={(event) => setRationales({ ...rationales, [hypothesis.id]: event.target.value })}
                        placeholder="Reviewer rationale required to confirm"
                      />
                      {confirming === hypothesis.id && <span className="ml-2 text-xs text-muted">Saving…</span>}
                    </div>
                  )}
                  {hypothesis.review_history?.length ? (
                    <div className="mt-3 text-xs text-muted">
                      {hypothesis.review_history.map((review) => (
                        <p key={`${review.reviewed_at}-${review.reviewer_id}`}>
                          {review.previous_status} → {review.new_status} · {review.reviewer_id} · {formatDate(review.reviewed_at)} · {review.rationale}
                        </p>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>
        <div className="space-y-5">
          <div className="panel">
            <div className="panel-heading">
              <div>
                <div className="flex items-center gap-2"><h3>Risk breakdown</h3><TypeBadge kind="PREDICTION" /></div>
                <p>Factor-level prioritization from linked recommendations</p>
              </div>
              <Gauge size={18} className="text-muted" />
            </div>
            {recommendations.some((rec) => rec.priority_breakdown) ? (
              recommendations
                .filter((rec) => rec.priority_breakdown)
                .map((rec) => (
                  <div className="p-5" key={rec.id}>
                    {Object.entries(rec.priority_breakdown || {}).map(([factor, value]) => (
                      <div className="risk-row" key={factor}>
                        <span>{factor.replaceAll('_', ' ')}</span>
                        <strong>{serialized(value)}</strong>
                      </div>
                    ))}
                    <Meta source={rec.source} refs={rec.record_refs} version="risk-rule version unavailable" timestamp={rec.created_at} limitations={rec.constraints || []} />
                  </div>
                ))
            ) : (
              <EmptyPanel title="Breakdown unavailable" message="No factor-by-factor risk breakdown was returned for this incident." />
            )}
          </div>
          <div className="panel">
            <div className="panel-heading">
              <div>
                <div className="flex items-center gap-2"><h3>Recommendations</h3><TypeBadge kind="RECOMMENDATION" /></div>
                <p>Suggested actions; not executed by this view</p>
              </div>
              <Bell size={18} className="text-muted" />
            </div>
            {!recommendations.length ? (
              <EmptyPanel title="No linked recommendations" message="Recommendation records do not include this incident identifier." />
            ) : (
              recommendations.map((rec) => (
                <div className="recommendation-card" key={rec.id}>
                  <p className="font-semibold text-ink dark:text-white">{rec.action}</p>
                  <p className="mt-1 text-sm text-muted dark:text-slate-400">{rec.rationale}</p>
                  <div className="mt-3 space-y-1 text-xs text-muted">
                    {rec.assumptions?.map((assumption) => <p key={assumption}>Assumption · {assumption}</p>)}
                    {rec.uncertainty && <p>Uncertainty · {rec.uncertainty}</p>}
                    {rec.constraints?.map((constraint) => <p key={constraint}>Constraint · {constraint}</p>)}
                  </div>
                  <Meta source={rec.source} refs={rec.record_refs} timestamp={rec.created_at} limitations={rec.constraints || []} />
                </div>
              ))
            )}
          </div>
          <div className="panel">
            <div className="panel-heading">
              <div><h3>Explanations & gaps</h3><p>Information returned by the incident detail endpoint</p></div>
              <CircleHelp size={18} className="text-muted" />
            </div>
            <div className="p-5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-muted">Alternative explanations</h4>
              <EvidenceState value="Not separately supplied by the API response." />
              <h4 className="mt-5 text-xs font-bold uppercase tracking-wider text-muted">Missing evidence</h4>
              {item.limitations?.length ? (
                item.limitations.map((limit) => <p className="mt-2 text-sm text-ink dark:text-slate-200" key={limit}>• {limit}</p>)
              ) : (
                <EvidenceState value="No missing-evidence notes returned by the API." />
              )}
              <h4 className="mt-5 text-xs font-bold uppercase tracking-wider text-muted">Known limitations</h4>
              {item.limitations?.length ? (
                item.limitations.map((limit) => <p className="mt-2 text-sm text-muted dark:text-slate-400" key={limit}>{limit}</p>)
              ) : (
                <EvidenceState value="No limitations returned by the API." />
              )}
            </div>
          </div>
          <div className="panel">
            <div className="panel-heading">
              <div><h3>Action & approval history</h3><p>Linked persisted records only</p></div>
              <CheckCircle2 size={18} className="text-muted" />
            </div>
            <div className="p-5">
              {!actions.length && !approvals.length ? (
                <EmptyPanel title="No linked history" message="No actions or approvals could be linked to this incident's recommendations." />
              ) : (
                <div className="space-y-3">
                  {approvals.map((approval) => (
                    <div className="history-row" key={approval.id}>
                      <CheckCircle2 size={15} />
                      <span>Approval {approval.status} · {approval.reviewer_id || 'reviewer unknown'} · {formatDate(approval.reviewed_at)}</span>
                      <TypeBadge kind="FACT" />
                    </div>
                  ))}
                  {actions.map((action) => (
                    <div className="history-row" key={action.id}>
                      <Activity size={15} />
                      <span>{action.status}{action.dry_run ? ' · DRY_RUN' : ''} · {formatDate(action.executed_at || action.created_at)}</span>
                      <TypeBadge kind="FACT" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

function LoadingState({ large = false }: { large?: boolean }) {
  return (
    <div className={`loading-state ${large ? 'py-24' : ''}`} role="status">
      <LoaderCircle size={18} className="animate-spin" />Loading local API data…
    </div>
  )
}

export default App
