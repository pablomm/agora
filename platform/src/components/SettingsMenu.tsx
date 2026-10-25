import { useId } from 'react'
import { copy } from '../app/copy'
import { basemaps, themeModes, type Settings, type ThemeMode } from '../app/settings'
import { usePopover } from './usePopover'

interface Props {
  settings: Settings
  onChange: (settings: Settings) => void
}

/** Settings button, first in the top-right column: the basemap, map layers as switches, and the theme. */
export function SettingsMenu({ settings, onChange }: Props) {
  const { open, setOpen, root, button } = usePopover()
  const panelId = useId()
  const set = (patch: Partial<Settings>) => onChange({ ...settings, ...patch })

  return (
    <div className="settings" ref={root}>
      <button
        ref={button}
        type="button"
        className="tool-button"
        aria-label={copy.settings.label}
        title={copy.settings.label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm7.4-2.1.1-1.4-.1-1.4 2-1.6-2-3.4-2.4 1a7 7 0 0 0-2.4-1.4L14.2 2h-4l-.4 2.6a7 7 0 0 0-2.4 1.4l-2.4-1-2 3.4 2 1.6-.1 1.4.1 1.4-2 1.6 2 3.4 2.4-1c.7.6 1.5 1.1 2.4 1.4l.4 2.6h4l.4-2.6c.9-.3 1.7-.8 2.4-1.4l2.4 1 2-3.4z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div id={panelId} className="settings-panel" role="group" aria-label={copy.settings.label}>
          <p className="settings-heading">{copy.settings.basemap}</p>
          <div className="settings-chips" role="radiogroup" aria-label={copy.settings.basemap}>
            {basemaps.map((kind) => (
              <button
                key={kind}
                type="button"
                role="radio"
                aria-checked={settings.basemap === kind}
                onClick={() => set({ basemap: kind })}
              >
                {copy.settings.basemaps[kind]}
              </button>
            ))}
          </div>
          <p className="settings-heading">{copy.settings.layers}</p>
          <label className="switch">
            <input
              type="checkbox"
              role="switch"
              checked={settings.streetNames}
              onChange={(event) => set({ streetNames: event.target.checked })}
            />
            <span className="switch-track" aria-hidden="true" />
            {copy.settings.streetNames}
          </label>
          <p className="settings-heading">{copy.settings.theme}</p>
          <ThemeSwitch value={settings.theme} onChange={(theme) => set({ theme })} />
        </div>
      )}
    </div>
  )
}

const themeIcons: Record<ThemeMode, React.ReactNode> = {
  auto: <text x="8" y="11.5" textAnchor="middle" fontSize="10" fontWeight="700" fill="currentColor">A</text>,
  light: (
    <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <circle cx="8" cy="8" r="2.8" />
      <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" />
    </g>
  ),
  dark: <path d="M10 2a6 6 0 1 0 4 10.5A5 5 0 0 1 10 2Z" fill="currentColor" />,
}

/**
 * The theme switch with three positions (automatic with the system, always light, always dark):
 * the same track as the on/off switches, with a knob that slides between the three.
 */
function ThemeSwitch({ value, onChange }: { value: ThemeMode; onChange: (mode: ThemeMode) => void }) {
  const index = themeModes.indexOf(value)
  const onKeyDown = (event: React.KeyboardEvent) => {
    const step = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const next = themeModes[(index + step + themeModes.length) % themeModes.length]
    onChange(next)
    ;(event.currentTarget.querySelector(`[data-mode="${next}"]`) as HTMLElement | null)?.focus()
  }
  return (
    <div className="switch tri-switch">
      <div className="tri-track" role="radiogroup" aria-label={copy.settings.theme} onKeyDown={onKeyDown}>
        <span className="tri-knob" style={{ transform: `translateX(${index * 20}px)` }} aria-hidden="true" />
        {themeModes.map((mode) => (
          <button
            key={mode}
            type="button"
            role="radio"
            data-mode={mode}
            aria-checked={value === mode}
            aria-label={copy.settings.themeLabels[mode]}
            title={copy.settings.themeLabels[mode]}
            tabIndex={value === mode ? 0 : -1}
            onClick={() => onChange(mode)}
          >
            <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
              {themeIcons[mode]}
            </svg>
          </button>
        ))}
      </div>
      <span className="tri-options" aria-hidden="true">
        {themeModes.map((mode, i) => (
          <span key={mode}>
            {i > 0 && ' / '}
            <span className={mode === value ? 'is-current' : 'tri-value'}>{copy.settings.themes[mode]}</span>
          </span>
        ))}
      </span>
    </div>
  )
}
