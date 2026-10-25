import { FileQuestion } from 'lucide-react'

export function NotFoundPage({ goHome }: { goHome: () => void }) {
  return <main className="error-page"><div className="error-page-card"><span className="empty-icon"><FileQuestion size={20} /></span><p className="eyebrow mt-4">404 · PAGE NOT FOUND</p><h1>This view is unavailable</h1><p>The requested dashboard path does not match a Phase 11 screen.</p><button className="primary-button mt-5" onClick={goHome}>Return to overview</button></div></main>
}
