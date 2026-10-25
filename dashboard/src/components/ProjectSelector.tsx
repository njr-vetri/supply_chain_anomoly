import { useState, useEffect, useCallback } from 'react'
import { Folder, Plus, ChevronDown, Check, Loader2 } from 'lucide-react'
import { ApiClient } from '../api/client'

interface Project {
  id: string
  name: string
  workspace_id: string
}

interface Props {
  client: ApiClient
  currentProjectId?: string | null
  onSelectProject: (project: Project) => void
}

export function ProjectSelector({ client, currentProjectId, onSelectProject }: Props) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadProjects = useCallback(async () => {
    setLoading(true)
    try {
      const res = await client.listProjects()
      setProjects(res.items || [])
      if (res.items?.length && !currentProjectId) {
        onSelectProject(res.items[0])
      }
    } catch {
      // Silently handle if unauthenticated or offline
    } finally {
      setLoading(false)
    }
  }, [client, currentProjectId, onSelectProject])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  const currentProject = projects.find((p) => p.id === currentProjectId) || (projects.length ? projects[0] : null)

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newProjectName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const created = await client.createProject(newProjectName.trim())
      setProjects((prev) => [...prev, created])
      onSelectProject(created)
      setNewProjectName('')
      setIsModalOpen(false)
      setIsOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="relative inline-block text-left">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 rounded-lg border border-line bg-card/60 px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-card dark:border-slate-800 dark:text-white"
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        <Folder size={14} className="text-sky-500" />
        <span className="max-w-[140px] truncate">
          {currentProject ? currentProject.name : loading ? 'Loading...' : 'Select Project'}
        </span>
        <ChevronDown size={12} className="text-muted dark:text-slate-400" />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 z-50 mt-1.5 w-56 rounded-xl border border-line bg-surface p-1 shadow-xl dark:border-slate-800 dark:bg-slate-900">
            <div className="px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted dark:text-slate-400">
              Projects
            </div>
            <div className="max-h-56 overflow-y-auto">
              {projects.map((proj) => (
                <button
                  key={proj.id}
                  onClick={() => {
                    onSelectProject(proj)
                    setIsOpen(false)
                  }}
                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition ${
                    proj.id === currentProject?.id
                      ? 'bg-sky-500/10 font-semibold text-sky-600 dark:text-sky-400'
                      : 'text-ink hover:bg-card dark:text-slate-300 dark:hover:bg-slate-800'
                  }`}
                >
                  <span className="truncate">{proj.name}</span>
                  {proj.id === currentProject?.id && <Check size={14} className="text-sky-500" />}
                </button>
              ))}
              {projects.length === 0 && !loading && (
                <div className="px-2.5 py-2 text-xs text-muted">No projects found</div>
              )}
            </div>
            <div className="mt-1 border-t border-line pt-1 dark:border-slate-800">
              <button
                onClick={() => {
                  setIsModalOpen(true)
                  setIsOpen(false)
                }}
                className="flex w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-sky-600 hover:bg-sky-50 dark:text-sky-400 dark:hover:bg-sky-950/40"
              >
                <Plus size={14} />
                <span>New project</span>
              </button>
            </div>
          </div>
        </>
      )}

      {/* New Project Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <h3 className="text-base font-semibold text-ink dark:text-white">Create New Project</h3>
            <p className="mt-1 text-xs text-muted dark:text-slate-400">
              Projects organize datasets, mapping versions, and pipelines.
            </p>
            {error && (
              <div className="mt-3 rounded-lg bg-rose-50 p-2.5 text-xs text-rose-600 dark:bg-rose-950/40 dark:text-rose-400">
                {error}
              </div>
            )}
            <form onSubmit={handleCreate} className="mt-4 space-y-3">
              <div>
                <label className="text-xs font-medium text-ink dark:text-slate-300">Project name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Kaveri Operations"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="text-input mt-1 w-full text-xs"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-muted hover:bg-card dark:border-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !newProjectName.trim()}
                  className="btn btn-primary flex items-center gap-1.5 text-xs"
                >
                  {creating && <Loader2 size={12} className="animate-spin" />}
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
