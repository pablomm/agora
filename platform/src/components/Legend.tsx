import { copy } from '../app/copy'
import { formatCompact } from '../app/format'
import type { Observations, Variable } from '../data/api'
import { choroplethClasses, type BoundaryBasemap } from '../map/boundaries'

interface Props {
  variable: Variable
  basemap: BoundaryBasemap
  /** The map's level, as the catalogue names it (undefined: a layer without statistics). */
  levelLabel: string | undefined
  observations: Observations | undefined
  status: 'ready' | 'loading' | 'unavailable' | 'failed'
}

/** What the colors mean: the variable, level, year and source, and one row per class. */
export function Legend({ variable, basemap, levelLabel, observations, status }: Props) {
  let body
  if (!levelLabel) body = <p className="legend-note">{copy.legend.noLevel}</p>
  else if (status === 'unavailable') body = <p className="legend-note">{copy.legend.unavailable(levelLabel)}</p>
  else if (status === 'failed') body = <p className="legend-note">{copy.legend.failed}</p>
  else if (status === 'loading' || !observations) body = <p className="legend-note">{copy.legend.loading}</p>
  else {
    const { breaks, colors } = choroplethClasses(observations.stats.quantiles, basemap)
    const unit = observations.unit
    const rows = colors.map((color, index) => {
      const from = breaks[index - 1]
      const to = breaks[index]
      const text =
        from === undefined ? `< ${formatCompact(to, unit)}` : to === undefined ? `≥ ${formatCompact(from, unit)}` : `${formatCompact(from, unit)} – ${formatCompact(to, unit)}`
      return { color, text }
    })
    const attribution = observations.facet.license?.attribution
    body = (
      <>
        <p className="legend-meta">
          {levelLabel} · {observations.period} · {observations.facet.label}
        </p>
        <ul className="legend-classes">
          {(breaks.length ? rows : [{ color: colors[0], text: formatCompact(observations.stats.min ?? 0, unit) }]).map((row) => (
            <li key={row.text}>
              <span className="map-legend-swatch" style={{ background: row.color }} aria-hidden="true" />
              {row.text}
            </li>
          ))}
        </ul>
        {attribution && (
          <p className="legend-source">
            {copy.legend.source}: {attribution}
          </p>
        )}
      </>
    )
  }
  return (
    <div className="map-legend" role="group" aria-label={`${copy.legend.label}: ${variable.label}`}>
      <p className="legend-title">
        {observations?.label ?? variable.label} {variable.unit !== 'personas' && <span className="legend-unit">({variable.unit})</span>}
      </p>
      {body}
    </div>
  )
}
