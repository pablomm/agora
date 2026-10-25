import { useState } from 'react'
import { copy } from '../app/copy'
import { formatCompact, formatValue } from '../app/format'
import type { Series } from '../data/api'

const WIDTH = 340
const HEIGHT = 170
const MARGIN = { top: 12, right: 14, bottom: 22, left: 46 }

interface Props {
  series: Series
  /** The year shown on the map, marked on the chart. */
  period: number | undefined
}

/**
 * A unit's values over the years: one line per source (each its own series, never joined),
 * categorical colors in fixed order, a legend when there are two, and a crosshair tooltip.
 */
export function SeriesChart({ series, period }: Props) {
  const [hoverYear, setHoverYear] = useState<number>()
  const lines = series.facets.filter((facet) => facet.values.length)
  const points = lines.flatMap((line) => line.values)
  if (!points.length) return null
  const years = [...new Set(points.map((point) => point.period))].sort((a, b) => a - b)
  const [firstYear, lastYear] = [years[0], years[years.length - 1]]
  const values = points.map((point) => point.value)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const padding = (high - low) * 0.1 || Math.abs(high) * 0.05 || 1
  const [yMin, yMax] = [low - padding, high + padding]
  const innerWidth = WIDTH - MARGIN.left - MARGIN.right
  const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const x = (year: number) => MARGIN.left + (lastYear === firstYear ? innerWidth / 2 : ((year - firstYear) / (lastYear - firstYear)) * innerWidth)
  const y = (value: number) => MARGIN.top + innerHeight - ((value - yMin) / (yMax - yMin)) * innerHeight
  const yTicks = [yMin + (yMax - yMin) * 0.15, (yMin + yMax) / 2, yMax - (yMax - yMin) * 0.15]
  const xTicks = years.length <= 6 ? years : [firstYear, Math.round((firstYear + lastYear) / 2), lastYear]

  const onMove = (event: React.PointerEvent<SVGRectElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const position = ((event.clientX - box.left) / box.width) * innerWidth + MARGIN.left
    const nearest = years.reduce((best, year) => (Math.abs(x(year) - position) < Math.abs(x(best) - position) ? year : best), years[0])
    setHoverYear(nearest)
  }
  const hovered = hoverYear === undefined ? [] : lines.map((line) => ({ line, point: line.values.find((point) => point.period === hoverYear) }))

  return (
    <figure className="chart">
      {lines.length > 1 && (
        <ul className="chart-legend">
          {lines.map((line, index) => (
            <li key={line.id}>
              <span className={`chart-key series-${index + 1}`} aria-hidden="true" />
              {line.label}
            </li>
          ))}
        </ul>
      )}
      <div className="chart-plot">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${copy.detail.series}: ${series.label}`}>
          {yTicks.map((tick) => (
            <g key={tick}>
              <line className="chart-grid" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(tick)} y2={y(tick)} />
              <text className="chart-tick" x={MARGIN.left - 6} y={y(tick)} textAnchor="end" dominantBaseline="middle">
                {formatCompact(tick, series.unit)}
              </text>
            </g>
          ))}
          <line className="chart-axis" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={HEIGHT - MARGIN.bottom} y2={HEIGHT - MARGIN.bottom} />
          {xTicks.map((year) => (
            <text key={year} className="chart-tick" x={x(year)} y={HEIGHT - 6} textAnchor="middle">
              {year}
            </text>
          ))}
          {period !== undefined && period >= firstYear && period <= lastYear && (
            <line className="chart-period" x1={x(period)} x2={x(period)} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} />
          )}
          {lines.map((line, index) => {
            const last = line.values[line.values.length - 1]
            return (
              <g key={line.id} className={`series-${index + 1}`}>
                <polyline className="chart-line" points={line.values.map((point) => `${x(point.period)},${y(point.value)}`).join(' ')} />
                <circle className="chart-dot" cx={x(last.period)} cy={y(last.value)} r={4} />
              </g>
            )
          })}
          {hoverYear !== undefined && (
            <g>
              <line className="chart-crosshair" x1={x(hoverYear)} x2={x(hoverYear)} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} />
              {hovered.map(({ line, point }, index) =>
                point ? <circle key={line.id} className={`chart-dot series-${index + 1}`} cx={x(point.period)} cy={y(point.value)} r={4} /> : null,
              )}
            </g>
          )}
          <rect
            className="chart-hit"
            x={MARGIN.left}
            y={MARGIN.top}
            width={innerWidth}
            height={innerHeight}
            onPointerMove={onMove}
            onPointerLeave={() => setHoverYear(undefined)}
          />
        </svg>
        {hoverYear !== undefined && (
          <div className="chart-tooltip" style={{ left: `${(x(hoverYear) / WIDTH) * 100}%` }} role="status">
            <strong>{hoverYear}</strong>
            {hovered.map(({ line, point }, index) =>
              point ? (
                <span key={line.id}>
                  <span className={`chart-key series-${index + 1}`} aria-hidden="true" />
                  {lines.length > 1 && `${line.label}: `}
                  {formatValue(point.value, series.unit)}
                </span>
              ) : null,
            )}
          </div>
        )}
      </div>
      <details className="chart-table">
        <summary>{copy.detail.seriesTable}</summary>
        <table>
          <thead>
            <tr>
              <th>{copy.detail.year}</th>
              {lines.map((line) => (
                <th key={line.id}>{line.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...years].reverse().map((year) => (
              <tr key={year}>
                <td>{year}</td>
                {lines.map((line) => {
                  const point = line.values.find((value) => value.period === year)
                  return <td key={line.id}>{point ? formatValue(point.value, series.unit) : '–'}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
