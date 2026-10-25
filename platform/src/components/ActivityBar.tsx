import { copy } from '../app/copy'
import { views, type ViewId } from '../sidebar/views'

interface Props {
  /** The view open in the sidebar, if any. */
  active: ViewId | undefined
  onSelect: (id: ViewId) => void
}

/** Narrow strip on the left edge, as in VS Code: one icon per view; the open one toggles it closed. */
export function ActivityBar({ active, onSelect }: Props) {
  return (
    <nav className="activity-bar" aria-label={copy.sidebar.label}>
      {views.map((view) => (
        <button
          key={view.id}
          type="button"
          className="activity-button"
          aria-label={view.label}
          title={view.label}
          aria-pressed={active === view.id}
          onClick={() => onSelect(view.id)}
        >
          <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
            {view.icon}
          </svg>
        </button>
      ))}
    </nav>
  )
}
