import type { Map as MaplibreMap } from 'maplibre-gl'
import { useId } from 'react'
import { copy } from '../app/copy'
import { boundaryModes, boundaryOverlays, type BoundaryMode } from '../app/settings'
import { activeLevel } from '../map/boundaries'
import { useZoom } from '../map/useZoom'
import { usePopover } from './usePopover'

interface Props {
  mode: BoundaryMode
  onChange: (mode: BoundaryMode) => void
  /** To name the level the automatic mode shows at the current zoom. */
  map: MaplibreMap | undefined
}

/**
 * Which administrative level the map shows: automatic (changes with the zoom, the default) or one
 * level fixed at every zoom. A fixed level marks the button with a dot, as a reminder.
 */
export function BoundariesMenu({ mode, onChange, map }: Props) {
  const { open, setOpen, root, button } = usePopover()
  const panelId = useId()
  const zoom = useZoom(map)
  const fixed = mode !== 'auto'
  const label = fixed ? `${copy.boundaries.label} · ${copy.boundaries.fixed}` : copy.boundaries.label

  return (
    <div className="settings" ref={root}>
      <button
        ref={button}
        type="button"
        className={`tool-button${fixed ? ' has-dot' : ''}`}
        aria-label={label}
        title={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="m12 4 8.5 4.5L12 13 3.5 8.5 12 4Zm-8.5 8L12 16.5l8.5-4.5M3.5 15.5 12 20l8.5-4.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div id={panelId} className="settings-panel" role="group" aria-label={copy.boundaries.heading}>
          <p className="settings-heading">{copy.boundaries.heading}</p>
          <div className="option-list" role="radiogroup" aria-label={copy.boundaries.heading}>
            {boundaryModes.map((option) => (
              <button
                key={option}
                type="button"
                role="radio"
                // Overlays don't nest in the levels above: a line sets them apart.
                className={option === boundaryOverlays[0] ? 'is-separated' : undefined}
                aria-checked={mode === option}
                onClick={() => onChange(option)}
              >
                {copy.boundaries.modes[option]}
                {option === 'auto' && zoom !== undefined && (
                  <small>
                    {copy.boundaries.autoHint} · {copy.boundaries.modes[activeLevel('auto', zoom)]}
                  </small>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
