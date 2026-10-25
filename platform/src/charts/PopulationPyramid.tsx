import { useState } from 'react'
import { copy } from '../app/copy'
import { formatCompact, formatInteger } from '../app/format'
import type { Breakdown } from '../data/api'

const WIDTH = 340
const ROW = 9
const GAP = 2
const LABEL = 34
const AXIS = 16

/**
 * A population pyramid from a sex × age breakdown: men to the left, women to the right, youngest
 * at the bottom, one bar per five-year group, a tooltip per group.
 */
export function PopulationPyramid({ breakdown }: { breakdown: Breakdown }) {
  const [hover, setHover] = useState<number>()
  const ages = breakdown.dimensions.find((dimension) => dimension.id === 'age')?.values.filter((value) => value.code !== 'total') ?? []
  const valueOf = (sex: string, age: string) =>
    breakdown.rows.find((row) => row.sex === sex && row.age === age && (row.nationality === undefined || row.nationality === 'total'))?.value ?? 0
  const groups = ages.map((age) => ({ age, men: valueOf('male', age.code), women: valueOf('female', age.code) })).reverse()
  const max = Math.max(1, ...groups.flatMap((group) => [group.men, group.women]))
  const half = (WIDTH - LABEL) / 2
  const height = groups.length * (ROW + GAP) + AXIS
  const scale = (value: number) => (value / max) * (half - 4)
  const centre = half

  return (
    <figure className="chart">
      <ul className="chart-legend">
        <li>
          <span className="chart-key series-1" aria-hidden="true" />
          {copy.detail.men}
        </li>
        <li>
          <span className="chart-key series-2" aria-hidden="true" />
          {copy.detail.women}
        </li>
      </ul>
      <div className="chart-plot">
        <svg viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={copy.detail.pyramid(breakdown.period)}>
          {groups.map((group, index) => {
            const top = index * (ROW + GAP)
            const short = group.age.label.replace(/^De (\d+) a (\d+) años$/, '$1–$2').replace(/^(\d+) y más años$/, '$1+')
            return (
              <g key={group.age.code} className={hover === index ? 'is-hovered' : undefined} onPointerEnter={() => setHover(index)} onPointerLeave={() => setHover(undefined)}>
                <rect className="chart-hit" x={0} y={top} width={WIDTH} height={ROW + GAP} />
                <rect className="pyramid-bar series-1" x={centre - scale(group.men)} y={top} width={scale(group.men)} height={ROW} rx={2} />
                <rect className="pyramid-bar series-2" x={centre + LABEL} y={top} width={scale(group.women)} height={ROW} rx={2} />
                {(index % 2 === 0 || hover === index) && (
                  <text className="chart-tick" x={centre + LABEL / 2} y={top + ROW / 2} textAnchor="middle" dominantBaseline="middle">
                    {short}
                  </text>
                )}
              </g>
            )
          })}
          <text className="chart-tick" x={2} y={height - 4}>
            {formatCompact(max, 'personas')}
          </text>
          <text className="chart-tick" x={WIDTH - 2} y={height - 4} textAnchor="end">
            {formatCompact(max, 'personas')}
          </text>
        </svg>
        {hover !== undefined && (
          <div className="chart-tooltip is-row" style={{ top: `${((hover * (ROW + GAP)) / height) * 100}%` }} role="status">
            <strong>{groups[hover].age.label}</strong>
            <span>
              <span className="chart-key series-1" aria-hidden="true" />
              {copy.detail.men}: {formatInteger(groups[hover].men)}
            </span>
            <span>
              <span className="chart-key series-2" aria-hidden="true" />
              {copy.detail.women}: {formatInteger(groups[hover].women)}
            </span>
          </div>
        )}
      </div>
    </figure>
  )
}
