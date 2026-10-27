import { useMemo, useState } from 'react'
import { copy } from '../app/copy'
import type { Catalog } from '../data/api'
import { facetCounts, hasFilters, NO_FILTERS, type CatalogEntry, type CatalogFilters as Filters, type FilterGroup } from './entries'

interface Props {
  catalog: Catalog | undefined
  catalogFailed: boolean
  /** The entries of the tab shown. */
  entries: CatalogEntry[]
  filters: Filters
  onChange: (filters: Filters) => void
}

/** The breakdowns (a long list) show this many until expanded; other groups show all. */
const SHOWN = 8

/**
 * The catalogue tab's panel: filters by kind (datasets), topic, level, source, frequency,
 * characteristics, breakdown and years, each value with how many entries it would give.
 */
export function CatalogFilters({ catalog, catalogFailed, entries, filters, onChange }: Props) {
  const years = useMemo(() => {
    const all = entries.flatMap((entry) => entry.years ?? [])
    if (!all.length) return []
    const first = Math.min(...all)
    const last = Math.max(...all)
    return Array.from({ length: last - first + 1 }, (_, index) => last - index)
  }, [entries])

  if (catalogFailed) return <p className="sidebar-empty layers-message">{copy.mapView.unavailableApi}</p>
  if (!catalog) return <p className="sidebar-empty layers-message">{copy.mapView.loading}</p>

  const groups: { id: FilterGroup; label: string; hint?: string; values: { id: string; label: string; hint?: string }[] }[] = [
    // Only datasets come in kinds (variables are all statistics).
    ...(filters.tab === 'datasets'
      ? [
          {
            id: 'kinds' as const,
            label: copy.catalog.filters.kinds,
            values: Object.keys(copy.catalog.kinds).map((id) => ({ id, label: copy.catalog.kinds[id], hint: copy.catalog.kindHints[id] })),
          },
        ]
      : []),
    { id: 'topics', label: copy.catalog.filters.topics, values: catalog.topics.map((topic) => ({ id: topic.id, label: topic.label })) },
    {
      id: 'levels',
      label: copy.catalog.filters.levels,
      hint: copy.catalog.filters.levelsHint,
      values: catalog.levels.map((level) => ({ id: level.id, label: level.label })),
    },
    {
      id: 'publishers',
      label: copy.catalog.filters.publishers,
      values: [...new Set(entries.flatMap((entry) => entry.publishers))].sort().map((publisher) => ({ id: publisher, label: publisher })),
    },
    { id: 'frequencies', label: copy.catalog.filters.frequencies, values: ['yearly', 'monthly'].map((id) => ({ id, label: copy.catalog.frequencies[id] })) },
    {
      id: 'tags',
      label: copy.catalog.filters.tags,
      values: Object.keys(copy.catalog.tags).map((id) => ({ id, label: copy.catalog.tags[id], hint: copy.catalog.tagHints[id] })),
    },
    {
      id: 'dimensions',
      label: copy.catalog.filters.dimensions,
      values: [...new Set(entries.flatMap((entry) => entry.dimensions))].map((label) => ({ id: label, label })),
    },
  ]

  return (
    <div className="catalog-filters">
      <div className="catalog-filters-header">
        <span>{copy.catalog.filters.label}</span>
        {hasFilters(filters) && (
          <button type="button" className="text-button" onClick={() => onChange({ ...NO_FILTERS, tab: filters.tab })}>
            {copy.catalog.clear}
          </button>
        )}
      </div>
      <div className="catalog-filters-body">
        {groups.map((group) => (
          <FilterSection key={group.id} group={group} counts={facetCounts(entries, filters, group.id)} filters={filters} onChange={onChange} />
        ))}
        {years.length > 1 && (
          <fieldset className="filter-group">
            <legend>{copy.catalog.filters.years}</legend>
            <div className="filter-years">
              {(['from', 'to'] as const).map((bound) => (
                <label key={bound} className="option-control">
                  <span className="option-label">{copy.catalog.filters[bound]}</span>
                  <select
                    value={filters[bound] ?? ''}
                    onChange={(event) => onChange({ ...filters, [bound]: event.target.value ? Number(event.target.value) : undefined })}
                  >
                    <option value="">{copy.catalog.filters.any}</option>
                    {years.map((year) => (
                      <option key={year} value={year}>
                        {year}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </fieldset>
        )}
      </div>
    </div>
  )
}

function FilterSection({
  group,
  counts,
  filters,
  onChange,
}: {
  group: { id: FilterGroup; label: string; hint?: string; values: { id: string; label: string; hint?: string }[] }
  counts: Map<string, number>
  filters: Filters
  onChange: (filters: Filters) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const chosen: string[] = filters[group.id]
  // Values with no entries are left out, unless chosen; long groups (breakdowns) go by count.
  const values = group.values.filter((value) => counts.get(value.id) || chosen.includes(value.id))
  const long = group.id === 'dimensions'
  if (long) values.sort((a, b) => (counts.get(b.id) ?? 0) - (counts.get(a.id) ?? 0) || a.label.localeCompare(b.label, 'es'))
  if (!values.length) return null
  const shown = expanded || !long ? values : values.slice(0, SHOWN).concat(values.slice(SHOWN).filter((value) => chosen.includes(value.id)))
  const toggle = (id: string) => onChange({ ...filters, [group.id]: chosen.includes(id) ? chosen.filter((item) => item !== id) : [...chosen, id] })
  return (
    <fieldset className="filter-group">
      <legend title={group.hint}>{group.label}</legend>
      {shown.map((value) => (
        <label key={value.id} className="filter-option" title={value.hint}>
          <input type="checkbox" checked={chosen.includes(value.id)} onChange={() => toggle(value.id)} />
          <span className="filter-option-label">{value.label}</span>
          <span className="filter-option-count">{counts.get(value.id) ?? 0}</span>
        </label>
      ))}
      {long && values.length > SHOWN && (
        <button type="button" className="text-button filter-more" onClick={() => setExpanded(!expanded)}>
          {expanded ? copy.catalog.filters.less : copy.catalog.filters.more(values.length - SHOWN)}
        </button>
      )}
    </fieldset>
  )
}
