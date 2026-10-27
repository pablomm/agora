import { useEffect, useMemo, useState } from 'react'
import { config } from '../app/config'
import { copy } from '../app/copy'
import { formatBytes, formatInteger, formatPeriod } from '../app/format'
import { SeriesChart } from '../charts/SeriesChart'
import {
  api,
  datasetFileUrl,
  type Catalog,
  type DataLevel,
  type Dataset,
  type DatasetDetail,
  type FileHead,
  type Localized,
  type Observations,
  type Series,
  type Variable,
} from '../data/api'
import { classBreaks } from '../map/boundaries'
import { DatasetMap } from './DatasetMap'
import { datasetHref, licenseHref, PARTIAL_BELOW, type CatalogEntry } from './entries'
import { levelData, relatedDatasets, variablesOf } from './related'

interface Props {
  catalog: Catalog
  /** The dataset's catalogue entry (topics, levels, years…). */
  entry: CatalogEntry | undefined
  dataset: Dataset
  onShowOnMap: (variableId: string) => void
}

/** The levels a statistics preview paints, in order of preference (provinces read best at this size). */
const PREVIEW_LEVELS: { level: DataLevel; layer: string }[] = [
  { level: 'province', layer: 'provinces' },
  { level: 'autonomous_community', layer: 'autonomous_communities' },
  { level: 'municipality', layer: 'municipalities' },
]

/** The map's first view (mainland Spain and the Balearic Islands), for previews of the whole country. */
const [[WEST, SOUTH], [EAST, NORTH]] = config.map.initialBounds
const SPAIN: [number, number, number, number] = [WEST, SOUTH, EAST, NORTH]

/** The part of some bounds on the map's first view (a whole-country extent without the Canary Islands, which would shrink it). */
function onMainland([west, south, east, north]: [number, number, number, number]): [number, number, number, number] {
  const clipped: [number, number, number, number] = [Math.max(west, WEST), Math.max(south, SOUTH), Math.min(east, EAST), Math.min(north, NORTH)]
  return clipped[0] < clipped[2] && clipped[1] < clipped[3] ? clipped : [west, south, east, north]
}

const formatDate = (iso: string) => new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' })

/** Spanish text of a value the catalogue gives in both languages (or as plain text). */
const spanish = (value: Localized | string | null | undefined) => (value && typeof value === 'object' ? value.es : (value ?? undefined))

/**
 * A dataset's page: what it is and how to read it, a preview (a map of its geometries, or of a
 * variable computed from it, and its evolution in Spain), how it was made, its coverage, the
 * variables and data related to it, its columns and codes, its files with their first rows, and
 * aside, its license, origin and processing.
 */
export function DatasetPage({ catalog, entry, dataset, onShowOnMap }: Props) {
  const [detail, setDetail] = useState<{ id: string; data?: DatasetDetail; failed?: boolean }>()
  useEffect(() => {
    let current = true
    api.dataset(dataset.id).then(
      (data) => current && setDetail({ id: dataset.id, data }),
      () => current && setDetail({ id: dataset.id, failed: true }),
    )
    return () => {
      current = false
    }
  }, [dataset.id])
  const data = detail?.id === dataset.id ? detail.data : undefined
  const variables = variablesOf(dataset, catalog)
  const topicLabels = new Map(catalog.topics.map((topic) => [topic.id, topic.label]))
  const statistics = dataset.kind === 'statistics'

  return (
    <div className="catalog-content dataset-page">
      <nav className="dataset-breadcrumb">
        <a href="#">{`← ${copy.dataset.back}`}</a>
      </nav>
      <header className="dataset-header">
        <span className="catalog-card-topic">
          {[copy.catalog.kinds[dataset.kind], ...(entry?.topics ?? []).map((topic) => topicLabels.get(topic) ?? topic)].join(' · ')}
        </span>
        <h1>{dataset.title}</h1>
        {dataset.description && <p className="dataset-lead">{dataset.description.es}</p>}
        <div className="dataset-header-meta">
          {dataset.publisher && <span>{dataset.publisher}</span>}
          <code>{dataset.id}</code>
          {entry?.tags.map((tag) => (
            <span key={tag} className={`chip is-tag is-${tag}`} title={copy.catalog.tagHints[tag]}>
              {copy.catalog.tags[tag] ?? tag}
            </span>
          ))}
        </div>
        {dataset.keywords && (
          <ul className="dataset-keywords" aria-label={copy.dataset.keywords}>
            {dataset.keywords.es.map((keyword) => (
              <li key={keyword}>{keyword}</li>
            ))}
          </ul>
        )}
        <div className="dataset-actions">
          {dataset.downloadable && (
            <a className="catalog-card-action" href="#files" onClick={(event) => (event.preventDefault(), document.getElementById('dataset-files')?.scrollIntoView({ behavior: 'smooth' }))}>
              {copy.dataset.download}
            </a>
          )}
          {variables[0] && (
            <button type="button" className="text-button" onClick={() => onShowOnMap(variables[0].id)}>
              {copy.dataset.showOnMap}
            </button>
          )}
        </div>
      </header>

      <Facts catalog={catalog} dataset={dataset} entry={entry} />

      <div className="dataset-layout">
        <div className="dataset-main">
          <Preview dataset={dataset} variables={variables} />
          {dataset.processing && (
            <section className="dataset-section">
              <h2>{copy.dataset.processing}</h2>
              <p className="dataset-prose">
                <Linked text={dataset.processing.es} />
              </p>
            </section>
          )}
          {statistics && data && <Coverage catalog={catalog} detail={data} />}
          {variables.length > 0 && <Variables catalog={catalog} variables={variables} onShowOnMap={onShowOnMap} />}
          <LevelData catalog={catalog} dataset={dataset} onShowOnMap={onShowOnMap} />
          {data && <Structure dataset={dataset} detail={data} />}
          <Files dataset={dataset} detail={data} />
          <Related catalog={catalog} dataset={dataset} />
          {detail?.failed && <p className="catalog-message">{copy.dataset.failed}</p>}
        </div>
        <aside className="dataset-aside">
          <License catalog={catalog} dataset={dataset} />
          <Origin catalog={catalog} dataset={dataset} detail={data} />
          {data?.run && <Run catalog={catalog} run={data.run} />}
          <section className="dataset-card">
            <h2>{copy.dataset.api}</h2>
            <a className="dataset-link" href={new URL(`/datasets/${encodeURIComponent(dataset.id)}`, config.api.url).toString()} target="_blank" rel="noreferrer">
              {`/datasets/${dataset.id}`}
            </a>
          </section>
        </aside>
      </div>
    </div>
  )
}

/** Text with its web addresses as links (the processing notes say where to get a dataset's sources). */
function Linked({ text }: { text: string }) {
  // An address ends before a closing parenthesis, comma or final full stop.
  const parts = text.split(/(https?:\/\/[^\s),]+[^\s),.])/)
  return parts.map((part, index) =>
    index % 2 ? (
      <a key={index} className="dataset-link" href={part} target="_blank" rel="noreferrer">
        {part}
      </a>
    ) : (
      part
    ),
  )
}

/** The key facts: when, how often, at which levels, how many rows, how big, what the values are. */
function Facts({ catalog, dataset, entry }: { catalog: Catalog; dataset: Dataset; entry: CatalogEntry | undefined }) {
  const levelLabels = new Map(catalog.levels.map((level) => [level.id, level.label]))
  const rows = dataset.files.reduce((sum, file) => sum + file.rows, 0)
  const sizes = dataset.files.map((file) => file.bytes)
  const bytes = sizes.every((size): size is number => size !== null) ? sizes.reduce((sum, size) => sum + size, 0) : null
  const statistics = dataset.kind === 'statistics'
  const periods = Object.values(dataset.coverage).flat()
  const facts: [string, string][] = []
  if (statistics && periods.length) {
    const [first, last] = [Math.min(...periods), Math.max(...periods)]
    facts.push([copy.dataset.facts.period, first === last ? formatPeriod(first) : `${formatPeriod(first)} – ${formatPeriod(last)}`])
    if (dataset.frequency) facts.push([copy.dataset.facts.frequency, copy.catalog.frequencies[dataset.frequency]])
  } else {
    const asOf = dataset.validity?.as_of === 'retrieval' ? null : dataset.validity?.as_of
    facts.push([copy.dataset.facts.validity, copy.catalog.validity(dataset.validity?.kind, asOf)])
    if (dataset.entity_type) facts.push([copy.dataset.facts.rowsAre, copy.dataset.entityTypes[dataset.entity_type] ?? dataset.entity_type])
  }
  if (entry?.levels.length) facts.push([copy.dataset.facts.levels, entry.levels.map((level) => copy.catalog.levelShort[level] ?? level).join(' · ')])
  if (dataset.base_level) facts.push([copy.dataset.facts.baseLevel, levelLabels.get(dataset.base_level) ?? dataset.base_level])
  if (dataset.measure) facts.push([copy.dataset.facts.measure, copy.dataset.measure(dataset.measure.unit, dataset.measure.aggregation)])
  facts.push([copy.dataset.facts.rows, formatInteger(rows)])
  if (bytes !== null) facts.push([copy.dataset.facts.size, formatBytes(bytes)])
  return (
    <dl className="dataset-facts" aria-label={copy.dataset.facts.label}>
      {facts.map(([term, value]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * A look at the data: a geometry's own layer, or a statistical dataset's first variable on a map
 * (by provinces, or the finest level near it the dataset has) next to its evolution in Spain.
 */
function Preview({ dataset, variables }: { dataset: Dataset; variables: Variable[] }) {
  const pick = useMemo(() => previewPick(dataset, variables), [dataset, variables])
  const [observations, setObservations] = useState<{ key: string; data: Observations }>()
  const [series, setSeries] = useState<{ key: string; data: Series }>()
  const key = pick ? `${dataset.id}|${pick.variable.id}` : undefined

  useEffect(() => {
    if (!pick || !key) return
    let current = true
    api.observations(pick.variable.id, pick.level, pick.period, pick.facet).then((data) => current && setObservations({ key, data }), () => undefined)
    if (pick.spain)
      api.series('es:country:es', pick.variable.id).then(
        (data) => current && setSeries({ key, data: { ...data, facets: data.facets.filter((facet) => facet.dataset === dataset.id) } }),
        () => undefined,
      )
    return () => {
      current = false
    }
  }, [pick, key, dataset.id])

  const choropleth = useMemo(() => {
    const data = observations && observations.key === key ? observations.data : undefined
    if (!data || !pick) return undefined
    const palette = pick.variable.palette
    return { values: data.values, breaks: classBreaks(Object.values(data.values), data.stats.quantiles, palette), palette, label: data.label }
  }, [observations, key, pick])
  const shownSeries = series && series.key === key && series.data.facets.some((facet) => facet.values.length > 1) ? series.data : undefined

  if (dataset.tiles && dataset.extent) {
    const focused = Boolean(dataset.focus) && (config.boundaries.fixedMinZoom as Record<string, number>)[dataset.tiles] > 5
    return (
      <section className="dataset-section">
        <h2>{copy.dataset.preview}</h2>
        <p className="dataset-hint">{focused ? copy.dataset.focused : copy.dataset.geometries}</p>
        <DatasetMap layer={dataset.tiles} bounds={focused ? dataset.focus! : onMainland(dataset.extent)} label={dataset.title} />
      </section>
    )
  }
  if (!pick) return null
  const mapCaption = choropleth
    ? (pick.level === 'municipality' ? copy.dataset.choroplethMunicipalities : copy.dataset.choropleth)(choropleth.label, formatPeriod(pick.period))
    : copy.mapView.loading
  return (
    <section className="dataset-section">
      <h2>{copy.dataset.preview}</h2>
      <div className={shownSeries ? 'dataset-preview has-chart' : 'dataset-preview'}>
        <figure>
          <figcaption className="dataset-figure-title">{mapCaption}</figcaption>
          {choropleth ? <DatasetMap layer={pick.layer} bounds={SPAIN} choropleth={choropleth} label={mapCaption} /> : <div className="dataset-map" />}
        </figure>
        {shownSeries && (
          <figure className="dataset-chart">
            <figcaption className="dataset-figure-title">{`${copy.dataset.seriesSpain} · ${shownSeries.label}`}</figcaption>
            <SeriesChart series={shownSeries} period={pick.period} table={false} />
          </figure>
        )}
      </div>
    </section>
  )
}

/** The variable, level and period a statistics preview shows: the first variable reading the dataset at a level a small map can paint. */
function previewPick(dataset: Dataset, variables: Variable[]) {
  for (const variable of variables) {
    const facet = variable.facets.find((item) => item.dataset === dataset.id)
    if (!facet) continue
    for (const { level, layer } of PREVIEW_LEVELS) {
      const periods = facet.coverage[level]
      if (periods?.length)
        return { variable, facet: facet.id, level, layer, period: Math.max(...periods), spain: (facet.coverage.country?.length ?? 0) > 1 }
    }
  }
  return undefined
}

/** Units with data at each level and period: full, partial (light) or none; months grouped by year. */
function Coverage({ catalog, detail }: { catalog: Catalog; detail: DatasetDetail }) {
  const levels = catalog.levels.filter((level) => detail.files.some((file) => file.name === level.id))
  const monthly = detail.files.some((file) => file.periods?.some((period) => period > 9999))
  const column = (period: number) => (monthly ? Math.floor(period / 100) : period)
  const columns = [...new Set(detail.files.flatMap((file) => (file.periods ?? []).map(column)))].sort((a, b) => a - b)
  return (
    <section className="dataset-section">
      <h2>{copy.dataset.coverage}</h2>
      <p className="dataset-hint">{copy.dataset.coverageHint}</p>
      <div className="coverage-matrix" role="table">
        <div role="row" className="coverage-matrix-row">
          <span role="columnheader" />
          {columns.map((year) => (
            <span key={year} role="columnheader" className="coverage-matrix-period">
              {String(year).slice(2)}
            </span>
          ))}
        </div>
        {levels.map((level) => {
          const file = detail.files.find((item) => item.name === level.id)!
          // Per column, the most units of any of its periods (a year's months).
          const units = new Map<number, number>()
          for (const [period, count] of Object.entries(file.units_by_period ?? {})) {
            const year = column(Number(period))
            units.set(year, Math.max(units.get(year) ?? 0, count))
          }
          return (
            <div key={level.id} role="row" className="coverage-matrix-row">
              <span role="rowheader" className="coverage-matrix-level">
                {copy.catalog.levelShort[level.id]}
              </span>
              {columns.map((year) => {
                const count = units.get(year) ?? 0
                const state = !count ? 'none' : count < PARTIAL_BELOW * level.units ? 'partial' : 'full'
                return (
                  <span
                    key={year}
                    role="cell"
                    className={`coverage-matrix-cell is-${state}`}
                    title={copy.dataset.coverageCell(level.label, String(year), count, level.units)}
                  />
                )
              })}
            </div>
          )
        })}
      </div>
    </section>
  )
}

/** The variables computed from the dataset, each with its topic, unit, levels and years, to paint on the map. */
function Variables({ catalog, variables, onShowOnMap }: { catalog: Catalog; variables: Variable[]; onShowOnMap: (id: string) => void }) {
  const topicLabels = new Map(catalog.topics.map((topic) => [topic.id, topic.label]))
  return (
    <section className="dataset-section">
      <h2>{copy.dataset.variables}</h2>
      <p className="dataset-hint">{copy.dataset.variablesHint}</p>
      <ul className="dataset-tiles">
        {variables.map((variable) => {
          const levels = catalog.levels.map((level) => level.id).filter((level) => variable.facets.some((facet) => facet.coverage[level]?.length))
          const periods = variable.facets.flatMap((facet) => Object.values(facet.coverage).flat())
          const [first, last] = [Math.min(...periods), Math.max(...periods)]
          return (
            <li key={variable.id}>
              <button type="button" className="dataset-tile" onClick={() => onShowOnMap(variable.id)} title={copy.catalog.showOnMap}>
                <span className="dataset-tile-kicker">{variable.topic ? topicLabels.get(variable.topic) : ''}</span>
                <strong>{variable.label}</strong>
                <span className="dataset-tile-meta">
                  {[variable.unit, levels.map((level) => copy.catalog.levelShort[level]).join(' · '), first === last ? formatPeriod(first) : `${formatPeriod(first)} – ${formatPeriod(last)}`].join('  ·  ')}
                </span>
                <span className="dataset-tile-action">{copy.catalog.showOnMap} →</span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** Variables shown at most per topic before "and N more". */
const LEVEL_TOPIC_VARIABLES = 5

/** What a geometry's units have data on: the variables at its levels, by topic, to paint on them. */
function LevelData({ catalog, dataset, onShowOnMap }: { catalog: Catalog; dataset: Dataset; onShowOnMap: (id: string) => void }) {
  const entries = levelData(dataset, catalog)
  if (!entries.length) return null
  const topicLabels = new Map(catalog.topics.map((topic) => [topic.id, topic.label]))
  const levelLabels = new Map(catalog.levels.map((level) => [level.id, level.label]))
  return (
    <section className="dataset-section">
      <h2>{copy.dataset.levelData}</h2>
      <p className="dataset-hint">{copy.dataset.levelDataHint}</p>
      {entries.map((entry) => (
        <details key={entry.level} className="dataset-level-data" open={entries.length === 1}>
          <summary>{copy.dataset.levelVariables(levelLabels.get(entry.level) ?? entry.level, entry.count)}</summary>
          <dl className="dataset-pairs">
            {entry.topics.map(({ topic, variables }) => (
              <div key={topic ?? ''}>
                <dt>{topic ? topicLabels.get(topic) : copy.catalog.noTopic}</dt>
                <dd className="dataset-variable-links">
                  {variables.slice(0, LEVEL_TOPIC_VARIABLES).map((variable) => (
                    <button key={variable.id} type="button" className="link-button" onClick={() => onShowOnMap(variable.id)}>
                      {variable.label}
                    </button>
                  ))}
                  {variables.length > LEVEL_TOPIC_VARIABLES && <span>{copy.dataset.moreVariables(variables.length - LEVEL_TOPIC_VARIABLES)}</span>}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      ))}
    </section>
  )
}

/** The columns (with what each is) and, for statistics, each breakdown's codes. */
function Structure({ dataset, detail }: { dataset: Dataset; detail: DatasetDetail }) {
  const dimensionLabels = new Map((detail.dimensions ?? []).map((dimension) => [dimension.id, dimension.label]))
  const meaning = (column: string) =>
    spanish(detail.fields?.[column]) ??
    (column === 'value'
      ? copy.dataset.valueColumn(dataset.measure?.unit)
      : dimensionLabels.has(column)
        ? copy.dataset.dimensionColumn(dimensionLabels.get(column)!)
        : (copy.dataset.standardColumns[column] ?? ''))
  return (
    <section className="dataset-section">
      <h2>{copy.dataset.structure}</h2>
      {dataset.kind === 'statistics' && <p className="dataset-hint">{copy.dataset.structureHint}</p>}
      <table className="dataset-table is-columns">
        <thead>
          <tr>
            <th>{copy.dataset.column}</th>
            <th>{copy.dataset.type}</th>
            <th>{copy.dataset.meaning}</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(detail.columns).map(([column, type]) => (
            <tr key={column}>
              <td>
                <code>{column}</code>
              </td>
              <td className="dataset-type">{type}</td>
              <td>{meaning(column)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {detail.dimensions && detail.dimensions.length > 0 && (
        <>
          <h3>{copy.dataset.dimensions}</h3>
          {detail.dimensions.map((dimension) => (
            <DimensionValues key={dimension.id} dimension={dimension} />
          ))}
        </>
      )}
    </section>
  )
}

/** The codes shown before "see all". */
const SHOWN_VALUES = 14

function DimensionValues({ dimension }: { dimension: NonNullable<DatasetDetail['dimensions']>[number] }) {
  const [expanded, setExpanded] = useState(false)
  const values = Object.entries(dimension.values)
  const shown = expanded ? values : values.slice(0, SHOWN_VALUES)
  return (
    <div className="dataset-dimension">
      <div className="dataset-dimension-name">
        <strong>{dimension.label}</strong> <code>{dimension.id}</code>
      </div>
      <ul className="dataset-codes">
        {shown.map(([code, label]) => (
          <li key={code} className="chip is-tag" title={code}>
            {label}
          </li>
        ))}
        {values.length > SHOWN_VALUES && (
          <li>
            <button type="button" className="text-button" onClick={() => setExpanded(!expanded)}>
              {expanded ? copy.dataset.fewerValues : copy.dataset.allValues(values.length)}
            </button>
          </li>
        )}
      </ul>
    </div>
  )
}

/** Each file with its rows, size and checksum, to download as stored (Parquet); its first rows; and how to read one from code. */
function Files({ dataset, detail }: { dataset: Dataset; detail: DatasetDetail | undefined }) {
  const first = dataset.files[0]
  const statistics = dataset.kind === 'statistics'
  const snippet = first && `import duckdb\nduckdb.sql("FROM '${datasetFileUrl(dataset.id, first.name, 'parquet')}' LIMIT 10")`
  const periodsOf = (name: string) => detail?.files.find((file) => file.name === name)?.periods
  return (
    <section className="dataset-section" id="dataset-files">
      <h2>{copy.dataset.files}</h2>
      {dataset.downloadable ? (
        <p className="dataset-hint">{copy.dataset.filesHint}</p>
      ) : (
        <p className="dataset-warning">{copy.dataset.notDownloadable(Boolean(dataset.license))}</p>
      )}
      <div className="dataset-table-scroll">
        <table className="dataset-table">
          <thead>
            <tr>
              <th>{copy.dataset.file}</th>
              {statistics && <th>{copy.dataset.periods}</th>}
              <th className="is-number">{copy.dataset.rows}</th>
              <th className="is-number">{copy.dataset.size}</th>
              {dataset.downloadable && <th>{copy.dataset.formats}</th>}
            </tr>
          </thead>
          <tbody>
            {dataset.files.map((file) => {
              const periods = periodsOf(file.name)
              return (
                <tr key={file.name}>
                  <td>
                    {file.label} <code>{file.name}</code>
                    {file.sha256 && (
                      <div className="dataset-checksum" title={`${copy.dataset.checksum} (sha256): ${file.sha256}`}>
                        sha256 <code>{file.sha256.slice(0, 16)}…</code>
                      </div>
                    )}
                  </td>
                  {statistics && <td>{periods?.length ? `${formatPeriod(periods[0])} – ${formatPeriod(periods[periods.length - 1])}` : '–'}</td>}
                  <td className="is-number">{formatInteger(file.rows)}</td>
                  <td className="is-number">{file.bytes === null ? '–' : formatBytes(file.bytes)}</td>
                  {dataset.downloadable && (
                    <td className="dataset-downloads">
                      <a href={datasetFileUrl(dataset.id, file.name, 'parquet')} download>
                        Parquet
                      </a>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {dataset.downloadable && <FilePreview dataset={dataset} />}
      {dataset.downloadable && snippet && (
        <>
          <h3>{copy.dataset.fromCode}</h3>
          <p className="dataset-hint">{copy.dataset.fromCodeHint}</p>
          <CodeBlock code={snippet} />
        </>
      )}
    </section>
  )
}

/** The first rows of one of the files (the first, or the one picked), as stored. */
function FilePreview({ dataset }: { dataset: Dataset }) {
  const [file, setFile] = useState(dataset.files[0]?.name)
  const [head, setHead] = useState<{ key: string; data?: FileHead; failed?: boolean }>()
  const key = `${dataset.id}|${file}`
  useEffect(() => {
    if (!file) return
    let current = true
    api.head(dataset.id, file).then(
      (data) => current && setHead({ key, data }),
      () => current && setHead({ key, failed: true }),
    )
    return () => {
      current = false
    }
  }, [dataset.id, file, key])
  const data = head?.key === key ? head.data : undefined
  if (!file) return null
  return (
    <>
      <div className="dataset-preview-header">
        <h3>{copy.dataset.filePreview}</h3>
        {dataset.files.length > 1 && (
          <label className="catalog-sort">
            <span>{copy.dataset.previewFile}</span>
            <select value={file} onChange={(event) => setFile(event.target.value)}>
              {dataset.files.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <p className="dataset-hint">{copy.dataset.filePreviewHint}</p>
      {head?.key === key && head.failed ? (
        <p className="catalog-message">{copy.dataset.failed}</p>
      ) : !data ? (
        <p className="catalog-message">{copy.mapView.loading}</p>
      ) : (
        <div className="dataset-table-scroll">
          <table className="dataset-table is-head">
            <thead>
              <tr>
                {Object.keys(data.columns).map((column) => (
                  <th key={column} title={data.columns[column]}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, index) => (
                <tr key={index}>
                  {Object.keys(data.columns).map((column) => {
                    const value = row[column]
                    return (
                      <td key={column} className={typeof value === 'number' ? 'is-number' : undefined}>
                        {value === null ? <span className="dataset-null">null</span> : String(value)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="dataset-code">
      <pre>
        <code>{code}</code>
      </pre>
      <button
        type="button"
        className="text-button"
        onClick={() =>
          navigator.clipboard.writeText(code).then(() => {
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          })
        }
      >
        {copied ? copy.dataset.copied : copy.dataset.copy}
      </button>
    </div>
  )
}

/** Datasets worth exploring from this one, each with why. */
function Related({ catalog, dataset }: { catalog: Catalog; dataset: Dataset }) {
  const related = relatedDatasets(dataset, catalog)
  if (!related.length) return null
  return (
    <section className="dataset-section">
      <h2>{copy.dataset.related}</h2>
      <ul className="dataset-tiles">
        {related.map(({ dataset: item, relation }) => (
          <li key={item.id}>
            <a className="dataset-tile" href={datasetHref(item.id)}>
              <span className="dataset-tile-kicker">{`${copy.catalog.kinds[item.kind]} · ${copy.dataset.relations[relation]}`}</span>
              <strong>{item.title}</strong>
              {item.publisher && <span className="dataset-tile-meta">{item.publisher}</span>}
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Its license (linked to its page: what it allows and requires), and how to cite the dataset. */
function License({ catalog, dataset }: { catalog: Catalog; dataset: Dataset }) {
  const own = dataset.license
  const entry = own?.id ? catalog.licenses.find((item) => item.id === own.id) : undefined
  const note = spanish((own as { note?: Localized | string } | null)?.note)
  return (
    <section className="dataset-card">
      <h2>{copy.dataset.license}</h2>
      {!own ? (
        <p className="dataset-warning">{copy.dataset.noLicense}</p>
      ) : (
        <>
          {entry ? (
            <>
              <p>
                <a className="dataset-link is-strong" href={licenseHref(entry.id)}>
                  {entry.title_es}
                </a>
              </p>
              <p>
                <span className={`chip is-tag ${entry.open ? 'is-open' : 'is-restricted'}`}>{entry.open ? copy.dataset.open : copy.dataset.restricted}</span>
              </p>
              <ul className="dataset-list">
                {entry.conditions.es.map((condition) => (
                  <li key={condition}>{condition}</li>
                ))}
              </ul>
              <a className="dataset-link is-block" href={licenseHref(entry.id)}>
                {`${copy.dataset.seeLicense} →`}
              </a>
            </>
          ) : (
            own.id && <p>{own.id}</p>
          )}
          {note && <p className="dataset-hint">{note}</p>}
          {own.attribution && (
            <>
              <h3>{copy.dataset.attribution}</h3>
              <CodeBlock code={own.attribution} />
            </>
          )}
        </>
      )}
    </section>
  )
}

/** Who publishes it, from which operation and tables (INE's, linked), how it's made, and what it's derived from. */
function Origin({ catalog, dataset, detail }: { catalog: Catalog; dataset: Dataset; detail: DatasetDetail | undefined }) {
  const source = (detail?.source ?? dataset.source ?? {}) as Record<string, unknown>
  const text = (key: string) => (typeof source[key] === 'string' ? (source[key] as string) : undefined)
  const links = Object.keys(copy.dataset.sourceLinks).filter((key) => text(key)?.startsWith('http') && !text(key)!.includes('{'))
  const tables = detail?.run?.tables ?? []
  const ine = dataset.publisher?.includes('INE')
  const from = ([] as unknown[]).concat(source.from ?? []).filter((item): item is string => typeof item === 'string')
  const titles = new Map(catalog.datasets.map((item) => [item.id, item.title]))
  if (!dataset.publisher && !text('operation') && !tables.length && !from.length && !links.length) return null
  return (
    <section className="dataset-card">
      <h2>{copy.dataset.origin}</h2>
      <dl className="dataset-pairs">
        {dataset.publisher && (
          <div>
            <dt>{copy.dataset.publisher}</dt>
            <dd>
              {dataset.publisher_url ? (
                <a className="dataset-link" href={dataset.publisher_url} target="_blank" rel="noreferrer">
                  {dataset.publisher}
                </a>
              ) : (
                dataset.publisher
              )}
            </dd>
          </div>
        )}
        {text('operation') && (
          <div>
            <dt>{copy.dataset.operation}</dt>
            <dd>{text('operation')}</dd>
          </div>
        )}
        {tables.length > 0 && (
          <div>
            <dt>{copy.dataset.tables(tables.length)}</dt>
            <dd className="dataset-tables">
              {tables.map((table) =>
                ine && typeof table === 'number' ? (
                  <a key={table} className="dataset-link" href={`https://www.ine.es/jaxiT3/Tabla.htm?t=${table}`} target="_blank" rel="noreferrer">
                    {table}
                  </a>
                ) : (
                  <span key={String(table)}>{table}</span>
                ),
              )}
            </dd>
          </div>
        )}
        {from.length > 0 && (
          <div>
            <dt>{copy.dataset.derivedFrom}</dt>
            <dd className="dataset-from">
              {from.map((id) =>
                titles.has(id) ? (
                  <a key={id} className="dataset-link" href={datasetHref(id)}>
                    {titles.get(id)}
                  </a>
                ) : (
                  <span key={id}>{id}</span>
                ),
              )}
            </dd>
          </div>
        )}
      </dl>
      {links.map((key) => (
        <a key={key} className="dataset-link is-block" href={text(key)} target="_blank" rel="noreferrer">
          {copy.dataset.sourceLinks[key]}
        </a>
      ))}
    </section>
  )
}

/** When the pipeline made it and downloaded its source, and how it checks against what's published. */
function Run({ catalog, run }: { catalog: Catalog; run: NonNullable<DatasetDetail['run']> }) {
  const levelLabels = new Map(catalog.levels.map((level) => [level.id, level.label]))
  return (
    <section className="dataset-card">
      <h2>{copy.dataset.run}</h2>
      <dl className="dataset-pairs">
        {run.generated_at && (
          <div>
            <dt>{copy.dataset.generated}</dt>
            <dd>{formatDate(run.generated_at)}</dd>
          </div>
        )}
        {run.retrieved_at && (
          <div>
            <dt>{copy.dataset.retrieved}</dt>
            <dd>{formatDate(run.retrieved_at)}</dd>
          </div>
        )}
      </dl>
      {run.checks && (
        <>
          <h3>{copy.dataset.checks}</h3>
          <ul className="dataset-list">
            {run.checks.map((check) => (
              <li key={check.level} className={check.mismatches ? 'is-warning' : undefined}>
                {copy.dataset.check(levelLabels.get(check.level as DataLevel) ?? check.level, check.compared, check.mismatches)}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
