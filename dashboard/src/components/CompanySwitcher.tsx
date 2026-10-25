import { Building2 } from 'lucide-react'

export interface CompanyContext {
  companyId: string
  workspaceName: string
  projectId: string
}

interface Props {
  context: CompanyContext
  onChange: (ctx: CompanyContext) => void
}

/** Sidebar widget that lets the operator set the company scope,
 *  workspace label, and project ID (needed for the supply graph).
 *  Values are persisted to session storage by the parent (App.tsx).
 *  The X-Company-Id header is injected by ApiClient.
 */
export function CompanySwitcher({ context, onChange }: Props) {
  return (
    <div className="company-switcher">
      <div className="company-switcher-header">
        <Building2 size={13} />
        <span>COMPANY SCOPE</span>
      </div>

      <label className="switcher-label">
        Company ID
        <input
          id="switcher-company-id"
          className="text-input switcher-input mt-1"
          value={context.companyId}
          onChange={(e) => onChange({ ...context, companyId: e.target.value.trim() || 'local' })}
          placeholder="local"
        />
      </label>

      <label className="switcher-label">
        Workspace (display only)
        <input
          id="switcher-workspace"
          className="text-input switcher-input mt-1"
          value={context.workspaceName}
          onChange={(e) => onChange({ ...context, workspaceName: e.target.value })}
          placeholder="optional"
        />
      </label>

      <label className="switcher-label">
        Project ID
        <input
          id="switcher-project-id"
          className="text-input switcher-input mt-1"
          value={context.projectId}
          onChange={(e) => onChange({ ...context, projectId: e.target.value })}
          placeholder="required for supply graph"
        />
        <span className="field-hint">
          Backend gap: no project list endpoint. Enter manually.
        </span>
      </label>

      {context.companyId && context.companyId !== 'local' && (
        <div className="switcher-active-pill">
          <span className="status-dot bg-emerald-500" />
          {context.companyId}
        </div>
      )}
    </div>
  )
}
