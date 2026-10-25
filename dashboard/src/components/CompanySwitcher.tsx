import { useState } from 'react'
import { Building2, Sliders, X } from 'lucide-react'

export interface CompanyContext {
  companyId: string
  workspaceName: string
  projectId: string
}

interface Props {
  context: CompanyContext
  onChange: (ctx: CompanyContext) => void
}

/** Sidebar widget that shows the active company and supply chain project scope.
 *  Clicking it opens an intuitive modal to adjust company or project IDs without
 *  cluttering the sidebar with raw inputs.
 */
export function CompanySwitcher({ context, onChange }: Props) {
  const [modalOpen, setModalOpen] = useState(false)
  const [companyId, setCompanyId] = useState(context.companyId)
  const [workspaceName, setWorkspaceName] = useState(context.workspaceName)
  const [projectId, setProjectId] = useState(context.projectId || 'project-kaveri_foods')

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    onChange({
      companyId: companyId.trim() || 'local',
      workspaceName: workspaceName.trim(),
      projectId: projectId.trim() || 'project-kaveri_foods',
    })
    setModalOpen(false)
  }

  return (
    <>
      <div
        className="company-scope-card group cursor-pointer"
        onClick={() => {
          setCompanyId(context.companyId)
          setWorkspaceName(context.workspaceName)
          setProjectId(context.projectId || 'project-kaveri_foods')
          setModalOpen(true)
        }}
        title="Click to manage company and project scope"
      >
        <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-muted">
          <span className="flex items-center gap-1.5">
            <Building2 size={12} className="text-brand" /> Company Scope
          </span>
          <Sliders size={12} className="opacity-60 group-hover:opacity-100 transition-opacity text-brand" />
        </div>
        <div className="mt-1.5 flex items-center justify-between">
          <span className="text-xs font-semibold text-ink dark:text-white truncate max-w-[120px]">
            {context.companyId || 'local'}
          </span>
          <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Active
          </span>
        </div>
        <div className="mt-1 flex items-center justify-between text-[10px] text-muted">
          <span className="truncate max-w-[130px] font-mono">{context.projectId || 'project-kaveri_foods'}</span>
          <span className="text-[9px] underline text-brand">Edit</span>
        </div>
      </div>

      {modalOpen && (
        <div className="dialog-backdrop">
          <div className="dialog-panel max-w-md w-full">
            <div className="flex items-center justify-between border-b border-line pb-3 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <Building2 size={17} className="text-brand" />
                <h3 className="font-semibold text-sm text-ink dark:text-white">Active Company & Scope</h3>
              </div>
              <button className="icon-button" onClick={() => setModalOpen(false)}><X size={15} /></button>
            </div>
            <form onSubmit={handleSave} className="py-4 space-y-3.5 text-xs">
              <label className="block">
                <span className="font-semibold text-ink dark:text-slate-200">Company ID (Tenant)</span>
                <input
                  id="switcher-company-id"
                  className="text-input mt-1 w-full"
                  value={companyId}
                  onChange={(e) => setCompanyId(e.target.value)}
                  placeholder="e.g. kaveri or local"
                />
              </label>

              <label className="block">
                <span className="font-semibold text-ink dark:text-slate-200">Workspace Label</span>
                <input
                  id="switcher-workspace"
                  className="text-input mt-1 w-full"
                  value={workspaceName}
                  onChange={(e) => setWorkspaceName(e.target.value)}
                  placeholder="e.g. local or primary"
                />
              </label>

              <label className="block">
                <span className="font-semibold text-ink dark:text-slate-200">Active Supply Chain Project ID</span>
                <input
                  id="switcher-project-id"
                  className="text-input mt-1 w-full font-mono text-[11px]"
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  placeholder="project-kaveri_foods"
                />
                <span className="field-hint mt-1 text-[10px] text-muted">
                  Selects the active knowledge graph and network nodes for the 3D Supply Chain Map.
                </span>
              </label>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="primary-button">Save Scope</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
