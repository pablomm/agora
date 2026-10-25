import { useEffect, useId } from 'react'
import { copy } from '../app/copy'
import { unitLabel, type SelectedUnit } from '../map/boundaries'

interface Props {
  unit: SelectedUnit
  onClose: () => void
}

/** The unit clicked on the map: side panel on desktop, bottom sheet on phones (see styles). */
export function DetailPanel({ unit, onClose }: Props) {
  const titleId = useId()

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <aside className="detail-panel" aria-labelledby={titleId}>
      <div className="panel-header">
        <div className="panel-title">
          <h2 id={titleId}>{unitLabel(unit.properties)}</h2>
          <span className="panel-kind">{copy.detail.kinds[unit.kind] ?? unit.kind}</span>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label={copy.detail.close} title={copy.detail.close}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className="panel-body">
        <p className="sidebar-empty">{copy.detail.empty}</p>
      </div>
    </aside>
  )
}
