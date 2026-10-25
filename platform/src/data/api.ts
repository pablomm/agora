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
}

/** A dimension the user picks for a variable: one value, or (`range`) a run of ordered values, summed. */
export interface VariableOption {
  dimension: string
  label: string
  range: boolean
  values: { code: string; label: string }[]
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
}

export interface Dimension {
  id: string
  label: string
  values: { code: string; label: string }[]
}

export interface Catalog {
  levels: { id: DataLevel; rank: number; label: string }[]
  topics: { id: string; label: string }[]
  variables: Variable[]
  dimensions: Dimension[]
}

export interface Observations {
  variable: string
  /** The variable's name with the options applied (Población · Mujeres). */
  label: string
  options: AppliedOptions
  unit: string
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
  observations: (variable: string, level: DataLevel, period?: number, facet?: string, choices: Choices = {}) =>
    get<Observations>('/observations', { variable, level, period, facet, option: optionParams(choices) }),
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

/** An option's value as the API takes it (a range as "first..last"). */
export function optionValue(option: VariableOption, choices: Choices): string {
  if (choices[option.dimension] !== undefined) return choices[option.dimension]
  return Array.isArray(option.default) ? `${option.default[0]}..${option.default[option.default.length - 1]}` : option.default
}

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
