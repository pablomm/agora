import { useEffect, useId, useState } from 'react'
import { copy } from '../app/copy'
import { formatValue } from '../app/format'
import { PopulationPyramid } from '../charts/PopulationPyramid'
import { SeriesChart } from '../charts/SeriesChart'
import { api, periodFor, type Breakdown, type Catalog, type Choices, type DataLevel, type Series } from '../data/api'
import { unitLabel, type SelectedUnit } from '../map/boundaries'

/** The dataset whose sex × age split draws the pyramid. */
const PYRAMID_DATASET = 'population_sex_age'
/** What the panel shows when no variable is painted on the map. */
const DEFAULT_VARIABLE = 'population'

const NO_CHOICES: Choices = {}

/** Kinds of unit with statistics, and their level (the others, like parcels, have none yet). */
const KIND_LEVEL: Record<string, DataLevel> = {
  autonomous_community: 'autonomous_community',
  province: 'province',
  municipality: 'municipality',
  census_district: 'census_district',
  census_section: 'census_section',
}

interface Props {
  unit: SelectedUnit
  catalog: Catalog | undefined
  /** The variable painted on the map (the panel shows population when there's none). */
  variableId: string | undefined
  /** Its options and source, as picked on the map. */
  choices: Choices
  facetId: string | undefined
  /** The year chosen on the map (undefined: the latest). */
  period: number | undefined
  onClose: () => void
}

/** The unit clicked on the map: side panel on desktop, bottom sheet on phones (see styles). */
export function DetailPanel({ unit, catalog, variableId, choices, facetId, period, onClose }: Props) {
  const titleId = useId()
  const level = KIND_LEVEL[unit.kind]
  const entityId = String(unit.target.id)
  const variable = catalog?.variables.find((item) => item.id === (variableId ?? DEFAULT_VARIABLE))
  const [series, setSeries] = useState<{ key: string; data?: Series }>()
  const [pyramid, setPyramid] = useState<{ key: string; data?: Breakdown }>()

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // The default variable shows with its own defaults, not the painted one's choices.
  const picked = variableId ? choices : NO_CHOICES
  const seriesKey = `${entityId}|${variable?.id}|${JSON.stringify(Object.entries(picked).sort())}`
  useEffect(() => {
    if (!level || !variable) return
    let current = true
    api.series(entityId, variable.id, picked).then(
      (data) => current && setSeries({ key: seriesKey, data }),
      () => current && setSeries({ key: seriesKey }),
    )
    return () => {
      current = false
    }
    // The key covers the choices.
  }, [entityId, level, variable, picked, seriesKey])

  // The pyramid's year follows the map's when the dataset has it, otherwise its latest.
  const pyramidFacet = catalog?.variables.flatMap((item) => item.facets).find((facet) => facet.dataset === PYRAMID_DATASET)
  const pyramidYear = level && pyramidFacet ? periodFor(pyramidFacet, level, period) : undefined
  const pyramidKey = `${entityId}|${pyramidYear}`
  useEffect(() => {
    if (!level || pyramidYear === undefined) return
    let current = true
    api.breakdown(entityId, PYRAMID_DATASET, pyramidYear).then(
      (data) => current && setPyramid({ key: pyramidKey, data }),
      () => current && setPyramid({ key: pyramidKey }),
    )
    return () => {
      current = false
    }
  }, [entityId, level, pyramidYear, pyramidKey])

  const seriesData = series?.key === seriesKey ? series.data : undefined
  const loading = level && variable && series?.key !== seriesKey
  // The headline: the default source's value in the map's year (or the latest it has).
  const main =
    seriesData?.facets.find((facet) => facet.id === (variableId ? facetId : undefined)) ??
    seriesData?.facets.find((facet) => facet.id === seriesData.default_facet) ??
    seriesData?.facets[0]
  const point = main && (main.values.find((value) => value.period === period) ?? main.values[main.values.length - 1])

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
        {!level && <p className="sidebar-empty">{copy.detail.noData}</p>}
        {loading && <p className="sidebar-empty">{copy.detail.loading}</p>}
        {level && !loading && !main && <p className="sidebar-empty">{copy.detail.empty}</p>}
        {variable && main && point && seriesData && (
          <>
            <section className="stat">
              <p className="stat-label">{seriesData.label}</p>
              <p className="stat-value">{formatValue(point.value, variable.unit)}</p>
              <p className="stat-meta">
                {point.period} · {main.label}
                {variable.unit !== 'personas' && ` · ${variable.unit}`}
              </p>
            </section>
            <section className="panel-section">
              <h3>{copy.detail.series}</h3>
              <SeriesChart series={seriesData} period={point.period} />
            </section>
          </>
        )}
        {pyramid?.key === pyramidKey && pyramid.data && (
          <section className="panel-section">
            <h3>{copy.detail.pyramid(pyramid.data.period)}</h3>
            <PopulationPyramid breakdown={pyramid.data} />
          </section>
        )}
        {main?.license?.attribution && (
          <p className="panel-source">
            {copy.detail.source}: {main.license.attribution}
          </p>
        )}
      </div>
    </aside>
  )
}
