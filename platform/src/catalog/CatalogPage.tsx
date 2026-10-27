import { useState } from 'react'
import { copy } from '../app/copy'
import { formatBytes, formatPeriod } from '../app/format'
import type { Catalog, DataLevel, Dataset } from '../data/api'
import { Segmented } from '../sidebar/OptionControls'
import { DatasetPage } from './DatasetPage'
import { LicensePage } from './LicensePage'
import { datasetHref, filterEntries, hasFilters, type CatalogRoute, NO_FILTERS, type CatalogEntry, type CatalogFilters, type CatalogTab, type FilterGroup, type SortOrder } from './entries'

interface Props {
  catalog: Catalog | undefined
  catalogFailed: boolean
  entries: Record<CatalogTab, CatalogEntry[]> | undefined
  filters: CatalogFilters
  onChange: (filters: CatalogFilters) => void
  /** Paints a variable on the map (and goes there). */
  onShowOnMap: (variableId: string) => void
  /** The page open in place of the list: a dataset's (#dataset/{id}) or a license's (#license/{id}). */
  route?: CatalogRoute
}

/**
 * The data catalogue, in place of the map: a search over datasets or variables (one tab each),
 * the filters chosen in the sidebar as removable chips, and a card per entry.
 */
export function CatalogPage({ catalog, catalogFailed, entries, filters, onChange, onShowOnMap, route }: Props) {
  const [sort, setSort] = useState<SortOrder>('relevance')
  if (catalogFailed) return <div className="catalog-page"><p className="catalog-message">{copy.mapView.unavailableApi}</p></div>
  if (!catalog || !entries) return <div className="catalog-page"><p className="catalog-message">{copy.mapView.loading}</p></div>
  if (route?.kind === 'license') {
    const license = catalog.licenses.find((item) => item.id === route.id)
    return (
      <div className="catalog-page">
        {license ? (
          <LicensePage key={license.id} catalog={catalog} license={license} />
        ) : (
          <div className="catalog-content">
            <a href="#">{`← ${copy.license.back}`}</a>
            <p className="catalog-message">{copy.license.notFound(route.id)}</p>
          </div>
        )}
      </div>
    )
  }
  if (route?.kind === 'dataset') {
    const dataset = catalog.datasets.find((item) => item.id === route.id)
    return (
      <div className="catalog-page" key={route.id}>
        {dataset ? (
          <DatasetPage
            key={dataset.id}
            catalog={catalog}
            dataset={dataset}
            entry={entries.datasets.find((entry) => entry.id === dataset.id)}
            onShowOnMap={onShowOnMap}
          />
        ) : (
          <div className="catalog-content">
            <a href="#">{`← ${copy.dataset.back}`}</a>
            <p className="catalog-message">{copy.dataset.notFound(route.id)}</p>
          </div>
        )}
      </div>
    )
  }

  const results = filterEntries(entries[filters.tab], filters, sort)
  const publishers = new Set(catalog.datasets.map((dataset) => dataset.publisher).filter(Boolean))
  const labels = filterLabels(catalog)

  return (
    <div className="catalog-page">
      <div className="catalog-content">
        <header className="catalog-header">
          <h1>{copy.catalog.title}</h1>
          <p>{copy.catalog.summary(catalog.datasets.length, catalog.variables.length, publishers.size)}</p>
        </header>

        <div className="catalog-search">
          <svg className="search-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="m15 15 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            aria-label={copy.catalog.search}
            placeholder={copy.catalog.search}
            value={filters.query}
            onChange={(event) => onChange({ ...filters, query: event.target.value })}
          />
        </div>

        <div className="catalog-tabs">
          <Segmented
            label={copy.catalog.tabsLabel}
            items={(['datasets', 'variables'] as CatalogTab[]).map((tab) => ({ id: tab, label: `${copy.catalog.tabs[tab]} · ${entries[tab].length}` }))}
            value={filters.tab}
            onChange={(tab) => onChange({ ...filters, tab: tab as CatalogTab })}
          />
          <p className="catalog-tab-hint">{copy.catalog.tabHints[filters.tab]}</p>
        </div>

        <div className="catalog-toolbar">
          <span className="catalog-count" aria-live="polite">
            {copy.catalog.results(results.length)}
          </span>
          <ul className="catalog-chips" aria-label={copy.catalog.filters.label}>
            {(Object.keys(labels) as FilterGroup[]).flatMap((group) =>
              filters[group].map((value) => {
                const label = labels[group].get(value) ?? value
                return (
                  <li key={`${group}:${value}`}>
                    <button
                      type="button"
                      className="chip is-removable"
                      aria-label={copy.catalog.removeFilter(label)}
                      onClick={() => onChange({ ...filters, [group]: filters[group].filter((item) => item !== value) })}
                    >
                      {label}
                      <svg viewBox="0 0 24 24" width="10" height="10" aria-hidden="true">
                        <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
                      </svg>
                    </button>
                  </li>
                )
              }),
            )}
            {(filters.from !== undefined || filters.to !== undefined) && (
              <li>
                <button
                  type="button"
                  className="chip is-removable"
                  aria-label={copy.catalog.removeFilter(copy.catalog.filters.years)}
                  onClick={() => onChange({ ...filters, from: undefined, to: undefined })}
                >
                  {`${filters.from ?? '…'} – ${filters.to ?? '…'}`}
                  <svg viewBox="0 0 24 24" width="10" height="10" aria-hidden="true">
                    <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
                  </svg>
                </button>
              </li>
            )}
          </ul>
          {hasFilters(filters) && (
            <button type="button" className="text-button" onClick={() => onChange({ ...NO_FILTERS, tab: filters.tab })}>
              {copy.catalog.clear}
            </button>
          )}
          <label className="catalog-sort">
            <span>{copy.catalog.sort}</span>
            <select value={sort} onChange={(event) => setSort(event.target.value as SortOrder)}>
              {(Object.keys(copy.catalog.sorts) as SortOrder[]).map((id) => (
                <option key={id} value={id}>
                  {copy.catalog.sorts[id]}
                </option>
              ))}
            </select>
          </label>
        </div>

        {results.length === 0 ? (
          <p className="catalog-message">{copy.catalog.noResults}</p>
        ) : (
          <ul className="catalog-results">
            {results.map((entry) => (
              <li key={entry.id}>
                <EntryCard entry={entry} catalog={catalog} onShowOnMap={onShowOnMap} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** How each filter's values are named, for the chips. */
function filterLabels(catalog: Catalog): Record<FilterGroup, Map<string, string>> {
  return {
    kinds: new Map(Object.entries(copy.catalog.kinds)),
    topics: new Map(catalog.topics.map((topic) => [topic.id, topic.label])),
    levels: new Map(catalog.levels.map((level) => [level.id, level.label])),
    publishers: new Map(),
    frequencies: new Map(Object.entries(copy.catalog.frequencies)),
    tags: new Map(Object.entries(copy.catalog.tags)),
    dimensions: new Map(),
  }
}

function EntryCard({ entry, catalog, onShowOnMap }: { entry: CatalogEntry; catalog: Catalog; onShowOnMap: (variableId: string) => void }) {
  const topicLabels = new Map(catalog.topics.map((topic) => [topic.id, topic.label]))
  const variables = new Map(catalog.variables.map((variable) => [variable.id, variable]))
  const datasets = new Map(catalog.datasets.map((dataset) => [dataset.id, dataset]))
  const dataset = entry.kind === 'datasets' ? datasets.get(entry.id) : undefined
  const statistics = entry.datasetKind === 'statistics'
  const topics = entry.topics.map((topic) => topicLabels.get(topic) ?? topic).join(' · ')

  return (
    <article className="catalog-card">
      <div className="catalog-card-top">
        <span className="catalog-card-topic">{statistics ? topics || copy.catalog.noTopic : copy.catalog.kinds[entry.datasetKind]}</span>
        <span className="catalog-card-publisher">{entry.publishers.join(' · ')}</span>
      </div>
      <h3>{entry.kind === 'datasets' ? <a href={datasetHref(entry.id)}>{entry.title}</a> : entry.title}</h3>
      {entry.description && <p className={entry.kind === 'datasets' ? 'catalog-card-description is-clamped' : 'catalog-card-description'}>{entry.description}</p>}
      {entry.levels.length > 0 && <CoverageStrip entry={entry} catalog={catalog} />}
      {statistics || !dataset ? <PeriodMeta entry={entry} catalog={catalog} /> : <ExtentMeta dataset={dataset} />}
      {entry.dimensions.length > 0 && (
        <p className="catalog-card-meta">{`${copy.catalog.by} ${entry.dimensions.map((label) => label.toLowerCase()).join(', ')}`}</p>
      )}
      {entry.tags.length > 0 && (
        <ul className="catalog-card-tags">
          {entry.tags.map((tag) => (
            <li key={tag} className={`chip is-tag is-${tag}`} title={copy.catalog.tagHints[tag]}>
              {copy.catalog.tags[tag] ?? tag}
            </li>
          ))}
        </ul>
      )}
      <div className="catalog-card-footer">
        {dataset && !statistics ? (
          <span className="catalog-card-related">{dataset.downloadable ? null : copy.catalog.notDownloadable}</span>
        ) : entry.kind === 'datasets' ? (
          <span className="catalog-card-related">
            {entry.related.length ? (
              <>
                {copy.catalog.variables(entry.related.length)}:{' '}
                {entry.related.map((id, index) => (
                  <span key={id}>
                    {index > 0 && ', '}
                    <button type="button" className="link-button" title={copy.catalog.showOnMap} onClick={() => onShowOnMap(id)}>
                      {variables.get(id)?.label ?? id}
                    </button>
                  </span>
                ))}
              </>
            ) : (
              copy.catalog.noVariables
            )}
          </span>
        ) : (
          <>
            <span className="catalog-card-related">
              {entry.related.map((id, index) => (
                <span key={id}>
                  {index > 0 && ' · '}
                  <a href={datasetHref(id)}>{datasets.get(id)?.title ?? id}</a>
                </span>
              ))}
            </span>
            <button type="button" className="catalog-card-action" onClick={() => onShowOnMap(entry.id)}>
              {copy.catalog.showOnMap}
            </button>
          </>
        )}
        <code className="catalog-card-id">{entry.id}</code>
      </div>
    </article>
  )
}

/** When statistics have data: their years or months, and how often. */
function PeriodMeta({ entry, catalog }: { entry: CatalogEntry; catalog: Catalog }) {
  const [first, last] = entry.years ?? [entry.latest, entry.latest]
  const period =
    entry.frequency === 'monthly'
      ? copy.catalog.periods(formatPeriod(firstPeriod(entry, catalog)), formatPeriod(entry.latest), entry.periods, true)
      : copy.catalog.periods(String(first), String(last), entry.periods, false)
  const frequency =
    entry.frequency === 'mixed' ? `${copy.catalog.frequencies.yearly} · ${copy.catalog.frequencies.monthly}` : entry.frequency ? copy.catalog.frequencies[entry.frequency] : null
  return (
    <p className="catalog-card-meta">
      <span>{period}</span>
      {frequency && <span>{frequency}</span>}
      {entry.kind === 'variables' && <span>{`${copy.catalog.unit}: ${entry.detail}`}</span>}
    </p>
  )
}

/** What a geometry or reference table is: as of when, how many rows, in how many files of what size. */
function ExtentMeta({ dataset }: { dataset: Dataset }) {
  const rows = dataset.files.reduce((sum, file) => sum + file.rows, 0)
  const sizes = dataset.files.map((file) => file.bytes)
  const bytes = sizes.every((size): size is number => size !== null) ? sizes.reduce((sum, size) => sum + size, 0) : null
  return (
    <p className="catalog-card-meta">
      <span>{copy.catalog.validity(dataset.validity?.kind, dataset.validity?.as_of === 'retrieval' ? null : dataset.validity?.as_of)}</span>
      <span>{copy.catalog.rows(rows)}</span>
      <span>{copy.catalog.files(dataset.files.length, bytes === null ? null : formatBytes(bytes))}</span>
    </p>
  )
}

/** The first period of a monthly entry (its years are years; its first month is in its datasets). */
function firstPeriod(entry: CatalogEntry, catalog: Catalog): number {
  const ids = entry.kind === 'datasets' ? [entry.id] : entry.related
  const periods = catalog.datasets.filter((dataset) => ids.includes(dataset.id)).flatMap((dataset) => Object.values(dataset.coverage).flat())
  return Math.min(...periods)
}

/** Which levels the entry has data at, from census sections to Spain: full, partial or none. */
function CoverageStrip({ entry, catalog }: { entry: CatalogEntry; catalog: Catalog }) {
  const units = (level: DataLevel) => {
    const ids = entry.kind === 'datasets' ? [entry.id] : entry.related
    return Math.max(0, ...catalog.datasets.filter((dataset) => ids.includes(dataset.id)).map((dataset) => dataset.units[level] ?? 0))
  }
  return (
    <ol className="coverage-strip" aria-label={copy.catalog.coverage}>
      {catalog.levels.map((level) => {
        const state = !entry.levels.includes(level.id) ? 'none' : entry.partialLevels.includes(level.id) ? 'partial' : 'full'
        const note = state === 'none' ? copy.catalog.noData : `${copy.catalog.units(units(level.id))}${state === 'partial' ? ` (${copy.catalog.partial})` : ''}`
        return (
          <li key={level.id} className={`is-${state}`} title={`${level.label}: ${note}`}>
            <span className="coverage-bar" aria-hidden="true" />
            <span className="coverage-label">{copy.catalog.levelShort[level.id]}</span>
            <span className="visually-hidden">{`${level.label}: ${note}`}</span>
          </li>
        )
      })}
    </ol>
  )
}
