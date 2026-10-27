import { copy } from '../app/copy'
import { fold } from '../app/format'
import type { Catalog, DataLevel, Dataset, DatasetKind, Variable } from '../data/api'

/** The catalogue lists datasets (tables at one or more levels) or variables (what the map paints). */
export type CatalogTab = 'datasets' | 'variables'

/** Below this share of a level's units, a dataset's coverage of it is partial (municipalities of 500 residents or more). */
const PARTIAL_BELOW = 0.9

/** Tags shown and filtered by: the datasets', and partial coverage, worked out here. */
export const PARTIAL_TAG = 'partial'

/** A dataset or a variable, with what the catalogue searches, filters and shows. */
export interface CatalogEntry {
  kind: CatalogTab
  /** Statistics, a geometry or a reference table (variables are all statistics). */
  datasetKind: DatasetKind
  id: string
  title: string
  description: string | null
  topics: string[]
  /** Levels with data, from the most detailed. */
  levels: DataLevel[]
  /** Of those, the ones only some units have. */
  partialLevels: DataLevel[]
  publishers: string[]
  /** Null for geometries and reference tables (they have editions or a date, not periods). */
  frequency: 'yearly' | 'monthly' | 'mixed' | null
  /** First and last year with data (statistics), or of the editions or date (the rest), if known. */
  years: [number, number] | null
  /** How many periods (years or months) there are, at the level with most. */
  periods: number
  tags: string[]
  /** What it's broken down by, by label (dimensions named alike, like the several "Edad", are one). */
  dimensions: string[]
  /** For a dataset: its variables; for a variable: its datasets. */
  related: string[]
  /** For a variable: its unit; for a dataset: the pipeline it comes from. */
  detail: string
  /** The latest period with data, to sort by. */
  latest: number
  text: string
}

const yearOf = (period: number) => (period > 9999 ? Math.floor(period / 100) : period)

/**
 * What a geometry or reference table covers: the level its rows are, or its files are (the
 * territorial units, a file per level), and the years of its editions or of its date.
 */
function extentOf(dataset: Dataset, catalog: Catalog) {
  const names = new Set([dataset.entity_type, ...dataset.files.map((file) => file.name)])
  const levels = catalog.levels.map((level) => level.id).filter((level) => names.has(level))
  const editions = dataset.files.map((file) => Number(file.name)).filter((year) => year > 1900 && year < 2200)
  const asOf = Number(dataset.validity?.as_of?.slice(0, 4))
  const years = editions.length ? editions : asOf ? [asOf] : []
  return {
    levels,
    partialLevels: [] as DataLevel[],
    years: years.length ? ([Math.min(...years), Math.max(...years)] as [number, number]) : null,
    periods: years.length,
    latest: years.length ? Math.max(...years) : 0,
    frequency: null,
  }
}

/** What a set of statistical datasets covers: levels (partial or not), years, periods, frequency. */
function coverageOf(datasets: Dataset[], catalog: Catalog) {
  const levelUnits = new Map(catalog.levels.map((level) => [level.id, level.units]))
  const levels = catalog.levels.map((level) => level.id).filter((level) => datasets.some((dataset) => dataset.coverage[level]?.length))
  // Partial where no dataset reaches most of the level's units.
  const partialLevels = levels.filter((level) =>
    datasets.every((dataset) => !dataset.coverage[level]?.length || (dataset.units[level] ?? 0) < PARTIAL_BELOW * (levelUnits.get(level) ?? 0)),
  )
  const periods = datasets.flatMap((dataset) => Object.values(dataset.coverage).flat())
  const years = periods.map(yearOf)
  const frequencies = new Set(datasets.map((dataset) => dataset.frequency))
  const perLevel = datasets.flatMap((dataset) => Object.values(dataset.coverage).map((list) => list.length))
  return {
    levels,
    partialLevels,
    years: [Math.min(...years), Math.max(...years)] as [number, number],
    periods: Math.max(0, ...perLevel),
    latest: Math.max(...periods),
    frequency: frequencies.size === 1 ? [...frequencies][0] : ('mixed' as const),
  }
}

/** Every dataset and variable as catalogue entries. */
export function catalogEntries(catalog: Catalog): Record<CatalogTab, CatalogEntry[]> {
  const datasets = new Map(catalog.datasets.map((dataset) => [dataset.id, dataset]))
  const topicLabels = new Map(catalog.topics.map((topic) => [topic.id, topic.label]))
  const dimensionLabels = new Map(catalog.dimensions.map((dimension) => [dimension.id, dimension.label]))
  const variablesOf = new Map<string, Variable[]>()
  for (const variable of catalog.variables) {
    for (const facet of variable.facets) variablesOf.set(facet.dataset, [...(variablesOf.get(facet.dataset) ?? []), variable])
  }
  // A dataset no variable reads (a breakdown behind a derived one) takes its pipeline's topics.
  const pipelineTopics = new Map<string, Set<string>>()
  for (const [id, variables] of variablesOf) {
    const pipeline = datasets.get(id)?.pipeline ?? ''
    const topics = pipelineTopics.get(pipeline) ?? new Set<string>()
    for (const variable of variables) if (variable.topic) topics.add(variable.topic)
    pipelineTopics.set(pipeline, topics)
  }
  const tagsOf = (dataset: Dataset, partial: boolean) => [...dataset.tags, ...(partial ? [PARTIAL_TAG] : [])]
  const searchable = (parts: (string | null | undefined)[]) => fold(parts.filter(Boolean).join(' '))

  const datasetEntries = catalog.datasets.map((dataset): CatalogEntry => {
    const variables = [...new Set(variablesOf.get(dataset.id) ?? [])]
    const topics = [...new Set(variables.map((variable) => variable.topic).filter((topic): topic is string => Boolean(topic)))]
    const coverage = dataset.kind === 'statistics' ? coverageOf([dataset], catalog) : extentOf(dataset, catalog)
    const resolvedTopics = topics.length || dataset.kind !== 'statistics' ? topics : [...(pipelineTopics.get(dataset.pipeline) ?? [])]
    return {
      kind: 'datasets',
      datasetKind: dataset.kind,
      id: dataset.id,
      title: dataset.title,
      description: dataset.source?.method ?? null,
      topics: resolvedTopics,
      publishers: dataset.publisher ? [dataset.publisher] : [],
      tags: tagsOf(dataset, coverage.partialLevels.length > 0),
      dimensions: [...new Set(dataset.dimensions.map((dimension) => dimensionLabels.get(dimension) ?? dimension))],
      related: variables.map((variable) => variable.id),
      detail: dataset.pipeline,
      ...coverage,
      text: searchable([
        dataset.title,
        dataset.id,
        dataset.publisher,
        dataset.source?.operation,
        copy.catalog.kinds[dataset.kind],
        ...resolvedTopics.map((topic) => topicLabels.get(topic)),
        ...dataset.dimensions.map((dimension) => dimensionLabels.get(dimension)),
        ...variables.map((variable) => variable.label),
      ]),
    }
  })

  const variableEntries = catalog.variables.map((variable): CatalogEntry => {
    const sources = [...new Set(variable.facets.map((facet) => facet.dataset))].map((id) => datasets.get(id)).filter((item): item is Dataset => Boolean(item))
    const coverage = coverageOf(sources, catalog)
    const topics = variable.topic ? [variable.topic] : []
    return {
      kind: 'variables',
      datasetKind: 'statistics',
      id: variable.id,
      title: variable.label,
      description: variable.description,
      topics,
      publishers: [...new Set(sources.map((dataset) => dataset.publisher).filter((publisher): publisher is string => Boolean(publisher)))],
      tags: [...new Set(sources.flatMap((dataset) => tagsOf(dataset, coverage.partialLevels.length > 0)))],
      dimensions: [...new Set(variable.options.map((option) => option.label))],
      related: sources.map((dataset) => dataset.id),
      detail: variable.unit,
      ...coverage,
      text: searchable([
        variable.label,
        variable.id,
        variable.description,
        variable.unit,
        ...topics.map((topic) => topicLabels.get(topic)),
        ...variable.options.map((option) => option.label),
        ...sources.flatMap((dataset) => [dataset.title, dataset.publisher]),
      ]),
    }
  })
  return { datasets: datasetEntries, variables: variableEntries }
}

/** What the catalogue is filtered by: values within a group are alternatives, groups all apply. */
export interface CatalogFilters {
  query: string
  tab: CatalogTab
  kinds: string[]
  topics: string[]
  /** Levels the entry must have data at. */
  levels: DataLevel[]
  publishers: string[]
  frequencies: string[]
  tags: string[]
  dimensions: string[]
  /** Years the entry must have data in (any of them). */
  from?: number
  to?: number
}

export type FilterGroup = 'kinds' | 'topics' | 'levels' | 'publishers' | 'frequencies' | 'tags' | 'dimensions'

const FILTER_GROUPS: FilterGroup[] = ['kinds', 'topics', 'levels', 'publishers', 'frequencies', 'tags', 'dimensions']

export const NO_FILTERS: CatalogFilters = { query: '', tab: 'datasets', kinds: [], topics: [], levels: [], publishers: [], frequencies: [], tags: [], dimensions: [] }

/** The values an entry has in a filter group. */
function valuesOf(entry: CatalogEntry, group: FilterGroup): string[] {
  if (group === 'kinds') return [entry.datasetKind]
  if (group === 'frequencies') return entry.frequency === 'mixed' ? ['yearly', 'monthly'] : entry.frequency ? [entry.frequency] : []
  return entry[group]
}

const queryWords = (query: string) => fold(query).split(/\s+/).filter(Boolean)

/** Whether an entry passes every filter, but `skip` (to count what each of its values would give). */
function passes(entry: CatalogEntry, filters: CatalogFilters, words: string[], skip?: FilterGroup): boolean {
  if (!words.every((word) => entry.text.includes(word))) return false
  for (const group of FILTER_GROUPS) {
    if (group === skip || !filters[group].length) continue
    // Levels all apply (data at sections and at municipalities); the rest are alternatives.
    const values = valuesOf(entry, group)
    const chosen: string[] = filters[group]
    const ok = group === 'levels' ? chosen.every((level) => values.includes(level)) : chosen.some((value) => values.includes(value))
    if (!ok) return false
  }
  if ((filters.from !== undefined || filters.to !== undefined) && !entry.years) return false
  if (filters.from !== undefined && entry.years && entry.years[1] < filters.from) return false
  if (filters.to !== undefined && entry.years && entry.years[0] > filters.to) return false
  return true
}

export type SortOrder = 'relevance' | 'name' | 'latest'

/** The entries passing the filters, best first: title matches, then the rest (or by name, or latest data). */
export function filterEntries(entries: CatalogEntry[], filters: CatalogFilters, sort: SortOrder): CatalogEntry[] {
  const words = queryWords(filters.query)
  const found = entries.filter((entry) => passes(entry, filters, words))
  const byName = (a: CatalogEntry, b: CatalogEntry) => a.title.localeCompare(b.title, 'es')
  if (sort === 'name') return found.sort(byName)
  if (sort === 'latest') return found.sort((a, b) => b.latest - a.latest || byName(a, b))
  if (!words.length) return found
  const score = (entry: CatalogEntry) => words.filter((word) => fold(entry.title).includes(word)).length
  return found.sort((a, b) => score(b) - score(a))
}

/**
 * For each value of a group, how many entries the filters would give with it: the group's own
 * choice left out for alternatives, kept for levels (which add up: each one more narrows).
 */
export function facetCounts(entries: CatalogEntry[], filters: CatalogFilters, group: FilterGroup): Map<string, number> {
  const words = queryWords(filters.query)
  const counts = new Map<string, number>()
  for (const entry of entries) {
    if (!passes(entry, filters, words, group === 'levels' ? undefined : group)) continue
    for (const value of valuesOf(entry, group)) counts.set(value, (counts.get(value) ?? 0) + 1)
  }
  return counts
}

/** Whether any filter but the tab is set. */
export const hasFilters = (filters: CatalogFilters) =>
  filters.query.trim() !== '' ||
  FILTER_GROUPS.some((group) => filters[group].length > 0) ||
  filters.from !== undefined ||
  filters.to !== undefined
