import { Component, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props { children: ReactNode }
interface State { failed: boolean }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State { return { failed: true } }
  componentDidCatch(): void { /* Rendering errors are shown without exposing internals. */ }

  render() {
    if (this.state.failed) return <main className="error-page"><div className="error-page-card"><span className="empty-icon"><AlertTriangle size={20} /></span><p className="eyebrow mt-4">APPLICATION ERROR</p><h1>Something went wrong</h1><p>The view could not be rendered. Your local API records were not changed.</p><button className="primary-button mt-5" onClick={() => window.location.reload()}>Reload console</button></div></main>
    return this.props.children
  }
}
