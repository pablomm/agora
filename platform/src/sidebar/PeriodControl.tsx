import { copy } from '../app/copy'

type Period = number | string

interface Props {
  /** The versions a layer has, newest first. */
  periods: Period[]
  /** The one chosen (undefined: the latest, which keeps following the latest when the level changes). */
  value: Period | undefined
  onChange: (period: Period | undefined) => void
}

const isYear = (period: Period) => typeof period === 'number' && Number.isInteger(period)

/**
 * A layer's version: a slider when versions are years (over the years it has, so gaps are
 * skipped), a select when they're named otherwise.
 */
export function PeriodControl({ periods, value, onChange }: Props) {
  if (!periods.length) return null
  const current = value !== undefined && periods.includes(value) ? value : periods[0]
  // Choosing the newest means "the latest", not that year in particular.
  const choose = (period: Period) => onChange(period === periods[0] ? undefined : period)

  if (!periods.every(isYear)) {
    return (
      <label className="period-control">
        <span className="period-label">{copy.mapView.version}</span>
        <select value={String(current)} onChange={(event) => choose(periods.find((period) => String(period) === event.target.value)!)}>
          {periods.map((period) => (
            <option key={period} value={period}>
              {period}
            </option>
          ))}
        </select>
      </label>
    )
  }

  const years = [...periods].reverse()
  const index = years.indexOf(current)
  return (
    <div className="period-control is-slider">
      <div className="period-header">
        <span className="period-label">{copy.mapView.year}</span>
        <output className="period-value">
          {current}
          {current === periods[0] && <span className="period-latest">{copy.mapView.latestTag}</span>}
        </output>
      </div>
      {years.length > 1 && (
        <>
          <input
            type="range"
            min={0}
            max={years.length - 1}
            step={1}
            value={index}
            aria-label={copy.mapView.year}
            aria-valuetext={String(current)}
            style={{ '--fill': `${(index / (years.length - 1)) * 100}%` } as React.CSSProperties}
            onChange={(event) => choose(years[Number(event.target.value)])}
          />
          <div className="period-range" aria-hidden="true">
            <span>{years[0]}</span>
            <span>{years[years.length - 1]}</span>
          </div>
        </>
      )}
    </div>
  )
}
