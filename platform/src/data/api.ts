import { config } from '../app/config'

/** A statistical level of the API (census_section … country). */
export type DataLevel = 'census_section' | 'census_district' | 'municipality' | 'province' | 'autonomous_community' | 'country'

export interface License {
  id?: string
  url?: string
  attribution?: string
}

export interface Facet {
  id: string
  label: string
  dataset: string
  dataset_title: string
  license: License | null
  frequency: 'yearly' | 'monthly'
  /** Periods with data (years, or months as YYYYMM), by level. */
  coverage: Partial<Record<DataLevel, number[]>>
  /** What it sums: dimension → code, codes, or "$dimension" (the option picked). */
  numerator: Record<string, unknown>
  /** What it's divided by, if a share: like `numerator`, or another dataset's `filter`. */
  denominator: Record<string, unknown> | null
}

/** The options a source applies: one without a dimension (no age by census section) ignores its option. */
export function facetDimensions(facet: Facet): Set<string> {
  const denominator = facet.denominator ?? {}
  const filters = [facet.numerator, ('dataset' in denominator ? denominator.filter : denominator) as Record<string, unknown>]
  return new Set(
    filters.flatMap((filter) => Object.values(filter ?? {})).flatMap((code) => (typeof code === 'string' && code.startsWith('$') ? [code.slice(1)] : [])),
  )
}

/**
 * A dimension the user picks for a variable: one value, or (`range`) a run of ordered values,
 * summed. One value is picked side by side (`segmented`) or from a dropdown (`select`); null:
 * side by side if the values fit, a dropdown if not.
 */
export interface VariableOption {
  dimension: string
  label: string
  range: boolean
  control: 'segmented' | 'select' | null
  /** In order; `parent` nests a value under another (France under the EU, under Europe). */
  values: { code: string; label: string; parent: string | null }[]
  default: string | string[]
}

/**
 * The options picked, as the API takes them: dimension → code, or "first..last" for ranges.
 * Options left out take the variable's default.
 */
export type Choices = Record<string, string>

/** How the API names a choice it applied: the codes, and a label (Mujeres, De 0 a 14 años). */
export type AppliedOptions = Record<string, { codes: string[]; label: string }>

export interface Variable {
  id: string
  topic: string | null
  label: string
  description: string | null
  unit: string
  kind: 'count' | 'ratio'
  default_facet: Partial<Record<DataLevel, string>>
  facets: Facet[]
  options: VariableOption[]
  /** The variable this one is another measure of (its share): both show as one layer. */
  measure_of: string | null
  /** Colored by magnitude, or above and below zero (a gap between two groups). */
  palette: 'sequential' | 'diverging'
}

export interface Dimension {
  id: string
  label: string
  values: { code: string; label: string }[]
}

/** What a dataset is tagged with: in its catalog.json, or found when the catalogue is built. */
export type DatasetTag = 'imputed' | 'derived' | 'experimental' | 'single_edition' | 'no_license' | (string & {})

/**
 * Statistics: values by unit and period, which variables are computed from. Geometries:
 * boundaries, cadastre, postal codes. Reference: classifications, the territorial units.
 */
export type DatasetKind = 'statistics' | 'geometry' | 'reference'

/** One of a dataset's files: a level (statistics), an edition or province (geometries), or its one file. */
export interface DatasetFile {
  name: string
  label: string
  rows: number
  /** Its size, when the dataset has all of the file (not a classification's share of the items). */
  bytes: number | null
}

/** A table: statistics at one or more levels (one file per level), a geometry or a reference table. */
export interface Dataset {
  id: string
  title: string
  kind: DatasetKind
  pipeline: string
  publisher: string | null
  license: License | null
  /** As the pipeline's catalog.json describes it: kind, operation, tables, method… */
  source: { kind?: string; operation?: string; tables?: unknown; method?: string; url?: string } | null
  dimensions: string[]
  base_level: DataLevel | null
  /** Statistics only. */
  frequency: 'yearly' | 'monthly' | null
  /** Geometries and reference tables: what each row is (municipality, cadastral_parcel…). */
  entity_type: string | null
  /** Geometries and reference tables: current, a snapshot or an edition, as of when. */
  validity: { kind?: 'current' | 'snapshot' | 'edition' | (string & {}); as_of?: string | null } | null
  /** False when its license isn't known: listed, but its files aren't served. */
  downloadable: boolean
  files: DatasetFile[]
  tags: DatasetTag[]
  /** Periods with data (years, or months as YYYYMM), by level. */
  coverage: Partial<Record<DataLevel, number[]>>
  /** The most units a level has data for in any period. */
  units: Partial<Record<DataLevel, number>>
}

export interface Catalog {
  /** `units`: how many the level has in the current cartography. */
  levels: { id: DataLevel; rank: number; label: string; units: number }[]
  topics: { id: string; label: string }[]
  variables: Variable[]
  datasets: Dataset[]
  dimensions: Dimension[]
}

export interface Observations {
  variable: string
  /** The variable's name with the options applied (Población · Mujeres). */
  label: string
  options: AppliedOptions
  unit: string
  /** Set when the values are changes against the year before: from which period, as % or a difference. */
  change: { from: number; as: 'percent' | 'difference' } | null
  level: DataLevel
  period: number
  facet: Omit<Facet, 'coverage'>
  values: Record<string, number>
  stats: { count: number; min: number | null; max: number | null; quantiles: number[] }
}

export interface Series {
  entity_id: string
  variable: string
  label: string
  options: AppliedOptions
  unit: string
  default_facet: string | null
  facets: (Omit<Facet, 'coverage'> & { values: { period: number; value: number }[] })[]
}

export interface Breakdown {
  entity_id: string
  dataset: string
  dataset_title: string
  license: License | null
  period: number
  periods: number[]
  dimensions: Dimension[]
  rows: (Record<string, string> & { value: number })[]
}

export interface Place {
  id: string
  level: DataLevel
  code: string
  name: string
  label: string
  parent_id: string | null
  parent_name?: string | null
  west: number | null
  south: number | null
  east: number | null
  north: number | null
}

const cache = new Map<string, Promise<unknown>>()

/** GET from the API; the same request is made once (answers don't change while the app is open). */
function get<T>(path: string, params: Record<string, string | number | string[] | undefined> = {}): Promise<T> {
  const url = new URL(path, config.api.url)
  for (const [key, value] of Object.entries(params)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) url.searchParams.append(key, String(item))
  }
  const key = url.toString()
  let request = cache.get(key) as Promise<T> | undefined
  if (!request) {
    request = fetch(key).then(async (response) => {
      if (!response.ok) throw new Error(`${response.status} ${(await response.json().catch(() => ({}))).detail ?? response.statusText}`)
      return response.json() as Promise<T>
    })
    // A failed request can be tried again.
    request.catch(() => cache.delete(key))
    cache.set(key, request)
  }
  return request
}

export const api = {
  catalog: () => get<Catalog>('/catalog'),
  observations: (variable: string, level: DataLevel, period?: number, facet?: string, choices: Choices = {}, change = false) =>
    get<Observations>('/observations', { variable, level, period, facet, option: optionParams(choices), change: change ? 'true' : undefined }),
  series: (entityId: string, variable: string, choices: Choices = {}) =>
    get<Series>(`/entities/${encodeURIComponent(entityId)}/series`, { variable, option: optionParams(choices) }),
  breakdown: (entityId: string, dataset: string, period?: number) =>
    get<Breakdown>(`/entities/${encodeURIComponent(entityId)}/breakdown`, { dataset, period }),
  search: (query: string) => get<Place[]>('/search', { q: query, limit: 8 }),
}

/** Choices as query parameters (option=sex:female), sorted so the same choice is the same request. */
const optionParams = (choices: Choices) =>
  Object.keys(choices)
    .sort()
    .map((dimension) => `${dimension}:${choices[dimension]}`)

/** The facets (sources) a variable has at a level. */
export const facetsAt = (variable: Variable, level: DataLevel) => variable.facets.filter((facet) => facet.coverage[level]?.length)

/** The facet a variable uses at a level: the one chosen if it covers the level, the level's default, or the first there. */
export function facetFor(variable: Variable, level: DataLevel, chosen?: string): Facet | undefined {
  const available = facetsAt(variable, level)
  return available.find((facet) => facet.id === chosen) ?? available.find((facet) => facet.id === variable.default_facet[level]) ?? available[0]
}

/**
 * An option's value as the API takes it (a range as "first..last"): the one chosen if the option has
 * it (a choice carried over from another measure of the layer may not be), or the default.
 */
export function optionValue(option: VariableOption, choices: Choices): string {
  const chosen = choices[option.dimension]
  const codes = option.values.map((value) => value.code)
  if (chosen !== undefined && chosen.split('..').every((code) => codes.includes(code))) return chosen
  return Array.isArray(option.default) ? `${option.default[0]}..${option.default[option.default.length - 1]}` : option.default
}

/** The same period a year before (the same month, for monthly data). */
export const yearBefore = (period: number) => (period > 9999 ? period - 100 : period - 1)

/**
 * The period to show at a level: the one chosen if that level has it; for a month chosen on yearly
 * data, its year (and for a year on monthly data, its last month); otherwise the latest.
 */
export function periodFor(facet: Facet, level: DataLevel, chosen: number | undefined): number | undefined {
  return matchPeriod(facet.coverage[level] ?? [], chosen)
}

/** Of some periods, the one matching `chosen` (see `periodFor`). */
export function matchPeriod(periods: number[], chosen: number | undefined): number | undefined {
  if (!periods.length) return undefined
  if (chosen !== undefined) {
    if (periods.includes(chosen)) return chosen
    const year = chosen > 9999 ? Math.floor(chosen / 100) : chosen
    const sameYear = periods.filter((period) => (period > 9999 ? Math.floor(period / 100) : period) === year)
    if (sameYear.length) return Math.max(...sameYear)
  }
  return Math.max(...periods)
}
