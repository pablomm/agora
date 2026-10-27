import type { Catalog, DataLevel, Dataset, Variable } from '../data/api'

/** Why a dataset is shown next to another. */
export type Relation = 'derivedFrom' | 'derivedInto' | 'geometry' | 'sameTopic' | 'classification' | 'classified' | 'gazetteer'

export interface RelatedDataset {
  dataset: Dataset
  relation: Relation
}

/** Variables available at a level, by topic: what a geometry's units have data on. */
export interface LevelData {
  level: DataLevel
  topics: { topic: string | null; variables: Variable[] }[]
  count: number
}

/** Dimensions too common to relate datasets by (nearly every population table has them). */
const COMMON_DIMENSIONS = new Set(['sex', 'age'])

/** At most this many datasets of the same topic. */
const SAME_TOPIC = 6

const sourceFrom = (dataset: Dataset): string[] =>
  ([] as unknown[]).concat((dataset.source as { from?: unknown } | null)?.from ?? []).filter((item): item is string => typeof item === 'string')

/** The topics of a dataset: its own, and its variables'. */
export function datasetTopics(dataset: Dataset, catalog: Catalog): string[] {
  const fromVariables = catalog.variables.filter((variable) => variable.facets.some((facet) => facet.dataset === dataset.id)).map((variable) => variable.topic)
  return [...new Set([...dataset.topics, ...fromVariables].filter((topic): topic is string => Boolean(topic)))]
}

/** The variables computed from a dataset. */
export const variablesOf = (dataset: Dataset, catalog: Catalog) =>
  catalog.variables.filter((variable) => variable.facets.some((facet) => facet.dataset === dataset.id))

/**
 * The datasets worth exploring from one: those it's derived from or that derive from it, the
 * geometries to map it, those of its topic sharing a breakdown, the classifications its breakdowns
 * use or the datasets using a classification, and the territorial units.
 */
export function relatedDatasets(dataset: Dataset, catalog: Catalog): RelatedDataset[] {
  const byId = new Map(catalog.datasets.map((item) => [item.id, item]))
  const out = new Map<string, RelatedDataset>()
  const add = (item: Dataset | undefined, relation: Relation) => {
    if (item && item.id !== dataset.id && !out.has(item.id)) out.set(item.id, { dataset: item, relation })
  }
  for (const id of sourceFrom(dataset)) add(byId.get(id), 'derivedFrom')
  for (const item of catalog.datasets) if (sourceFrom(item).includes(dataset.id)) add(item, 'derivedInto')

  if (dataset.kind === 'statistics') {
    const levels = new Set(Object.keys(dataset.coverage))
    for (const item of catalog.datasets) if (item.kind === 'geometry' && item.entity_type && levels.has(item.entity_type)) add(item, 'geometry')
    // Classifications the breakdowns' codes come from.
    const dimensions = new Map(catalog.dimensions.map((dimension) => [dimension.id, dimension]))
    for (const id of dataset.dimensions) {
      const dimension = dimensions.get(id)
      add(byId.get(dimension?.classification ?? dimension?.groups_of ?? ''), 'classification')
    }
    const topics = new Set(datasetTopics(dataset, catalog))
    const shared = dataset.dimensions.filter((id) => !COMMON_DIMENSIONS.has(id))
    let sameTopic = 0
    for (const item of catalog.datasets) {
      if (sameTopic >= SAME_TOPIC || item.kind !== 'statistics' || out.has(item.id) || item.id === dataset.id) continue
      const inTopic = datasetTopics(item, catalog).some((topic) => topics.has(topic))
      if (inTopic && (shared.length === 0 || item.dimensions.some((id) => shared.includes(id)))) {
        add(item, 'sameTopic')
        sameTopic++
      }
    }
  } else if (dataset.entity_type === 'classification_item') {
    // The datasets whose breakdowns are this classification's codes, or group them.
    const dimensions = catalog.dimensions.filter((dimension) => dimension.classification === dataset.id || dimension.groups_of === dataset.id).map((dimension) => dimension.id)
    for (const item of catalog.datasets) if (item.dimensions.some((id) => dimensions.includes(id))) add(item, 'classified')
    add(byId.get('classification_correspondences'), 'sameTopic')
  } else if (dataset.kind === 'geometry') {
    for (const item of catalog.datasets) if (item.kind === 'geometry' && item.tiles && item.tiles === dataset.tiles) add(item, 'sameTopic')
  }
  if (dataset.id !== 'territorial_units' && dataset.kind !== 'reference') add(byId.get('territorial_units'), 'gazetteer')
  return [...out.values()]
}

/** What a geometry's units (or the territorial units') have data on: the variables at each of its levels, by topic. */
export function levelData(dataset: Dataset, catalog: Catalog): LevelData[] {
  const levels = catalog.levels.map((level) => level.id).filter((level) => level === dataset.entity_type || dataset.files.some((file) => file.name === level))
  if (dataset.kind === 'statistics') return []
  return levels
    .map((level) => {
      const variables = catalog.variables.filter((variable) => !variable.measure_of && variable.facets.some((facet) => facet.coverage[level]?.length))
      const topics = new Map<string | null, Variable[]>()
      for (const variable of variables) topics.set(variable.topic, [...(topics.get(variable.topic) ?? []), variable])
      return { level, topics: [...topics].map(([topic, items]) => ({ topic, variables: items })), count: variables.length }
    })
    .filter((entry) => entry.count > 0)
}
