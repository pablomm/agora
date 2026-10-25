import type { ReactNode } from 'react'
import { copy } from '../app/copy'
import { views, type ViewId } from '../sidebar/views'

/** The open view's panel, between the activity bar and the map. */
export function Sidebar({ viewId, onClose, children }: { viewId: ViewId; onClose: () => void; children: ReactNode }) {
  const view = views.find((item) => item.id === viewId)
  if (!view) return null
  return (
    <aside className="sidebar" aria-label={view.label}>
      <div className="sidebar-header">
        <h2>{view.label}</h2>
        <button type="button" className="icon-button" aria-label={copy.sidebar.close} title={copy.sidebar.close} onClick={onClose}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className="sidebar-body">{children}</div>
    </aside>
  )
}
