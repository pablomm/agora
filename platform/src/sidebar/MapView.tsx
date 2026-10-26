import { useMemo, useState } from 'react'
import { copy } from '../app/copy'
import { fold, isCount } from '../app/format'
import { facetDimensions, type Catalog, type Choices, type Facet, type Variable } from '../data/api'
import { OptionControls, Segmented } from './OptionControls'
import { PeriodControl } from './PeriodControl'

interface Props {
  catalog: Catalog | undefined
  catalogFailed: boolean
  variableId: string | undefined
  onVariable: (id: string | undefined) => void
  /** Shows another measure of the layer (its number or its share), keeping what's picked. */
  onMeasure: (id: string) => void
  /** Years the chosen variable has at the map's level, newest first. */
  years: number[]
  /** The year chosen (undefined: the latest). */
  period: number | undefined
  onPeriod: (year: number | undefined) => void
  /** The chosen variable's options picked so far. */
  choices: Choices
  onChoices: (choices: Choices) => void
  /** The sources the chosen variable has at the map's level, and the one in use. */
  facets: Facet[]
  facetId: string | undefined
  onFacet: (id: string) => void
  /** Whether the map shows each unit's change against the year before, not its value. */
  change: boolean
  onChange: (change: boolean) => void
}

const COLLAPSED_KEY = 'agora:collapsed-topics'

function loadCollapsed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(COLLAPSED_KEY) ?? '[]') as string[])
  } catch {
    return new Set()
  }
}

/**
 * The map tab's panel: a search over the catalogue's variables, the one painted on the map (with
 * its year), and the list of all of them by topic, which scrolls on its own.
 */
export function MapView({ catalog, catalogFailed, variableId, onVariable, onMeasure, years, period, onPeriod, choices, onChoices, facets, facetId, onFacet, change, onChange }: Props) {
  const [query, setQuery] = useState('')
  // Collapsed topics, remembered in this browser. A search shows every match, collapsed or not.
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const searching = query.trim() !== ''
  const toggle = (id: string) => {
    const next = new Set(collapsed)
    if (!next.delete(id)) next.add(id)
    setCollapsed(next)
    try {
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
    } catch {
      // Storage unavailable (private mode…): the choice lasts until the page is reloaded.
    }
  }
  // A layer is a variable with its other measures (its share): one row, a measure switch in the card.
  const measures = useMemo(() => {
    const out = new Map<string, Variable[]>()
    for (const variable of catalog?.variables ?? []) {
      const layer = variable.measure_of ?? variable.id
      out.set(layer, [...(out.get(layer) ?? []), variable])
    }
    // The number first, then its share.
    for (const list of out.values()) list.sort((a, b) => Number(Boolean(a.measure_of)) - Number(Boolean(b.measure_of)))
    return out
  }, [catalog])
  const topics = useMemo(() => {
    if (!catalog) return []
    const words = fold(query).split(/\s+/).filter(Boolean)
    const labels = new Map(catalog.topics.map((topic) => [topic.id, topic.label]))
    const matches = (variable: Variable) => {
      const text = fold(
        (measures.get(variable.id) ?? [variable]).map((item) => `${item.label} ${item.description ?? ''}`).join(' ') + ` ${labels.get(variable.topic ?? '') ?? ''}`,
      )
      return words.every((word) => text.includes(word))
    }
    const groups = new Map<string, Variable[]>()
    for (const variable of catalog.variables.filter((item) => !item.measure_of && matches(item))) {
      const key = variable.topic ?? ''
      groups.set(key, [...(groups.get(key) ?? []), variable])
    }
    // In the catalogue's topic order, then any without a topic.
    const order = [...catalog.topics.map((topic) => topic.id), '']
    return [...groups]
      .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
      .map(([id, variables]) => ({
        id,
        label: labels.get(id) ?? copy.mapView.otherTopic,
        variables,
      }))
  }, [catalog, measures, query])

  if (catalogFailed) return <p className="sidebar-empty layers-message">{copy.mapView.unavailableApi}</p>
  if (!catalog) return <p className="sidebar-empty layers-message">{copy.mapView.loading}</p>
  const active = catalog.variables.find((variable) => variable.id === variableId)
  const layerId = active ? (active.measure_of ?? active.id) : undefined
  const activeMeasures = layerId ? (measures.get(layerId) ?? []) : []
  // Only the options the source in use applies (no age for the foreign population by census section).
  const facet = facets.find((item) => item.id === facetId)
  const options = active && facet ? active.options.filter((option) => facetDimensions(facet).has(option.dimension)) : (active?.options ?? [])

  return (
    <div className="layers">
      <div className="layers-search">
        <svg className="search-icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="m15 15 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          type="search"
          aria-label={copy.mapView.search}
          placeholder={copy.mapView.search}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <section className="layers-active" aria-label={copy.mapView.active}>
        {active ? (
          <div className="layer-card">
            <div className="layer-card-header">
              <strong>{active.label}</strong>
              <button type="button" className="icon-button" aria-label={copy.mapView.remove} title={copy.mapView.remove} onClick={() => onVariable(undefined)}>
                <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                  <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            {active.description && <p className="layer-card-description">{active.description}</p>}
            {activeMeasures.length > 1 && (
              <Segmented
                label={copy.mapView.measure}
                items={activeMeasures.map((item) => ({ id: item.id, label: isCount(item.unit) ? copy.mapView.count : item.unit }))}
                value={active.id}
                onChange={onMeasure}
              />
            )}
            <OptionControls options={options} choices={choices} onChange={onChoices} />
            <Segmented
              label={copy.mapView.view}
              items={[
                { id: 'value', label: copy.mapView.value },
                { id: 'change', label: copy.mapView.yearChange },
              ]}
              value={change ? 'change' : 'value'}
              onChange={(id) => onChange(id === 'change')}
            />
            {facets.length > 1 && facetId && <Segmented label={copy.mapView.source} items={facets} value={facetId} onChange={onFacet} />}
            <PeriodControl periods={years} value={period} onChange={(value) => onPeriod(value as number | undefined)} />
          </div>
        ) : (
          <p className="layers-none">{copy.mapView.none}</p>
        )}
      </section>

      <div className="layers-list" role="list" aria-label={copy.mapView.layers}>
        {topics.length === 0 && <p className="layers-none">{copy.mapView.noMatches}</p>}
        {topics.map((topic) => (
          <section key={topic.id} aria-label={topic.label}>
            <h3 className="layers-topic">
              <button
                type="button"
                aria-expanded={searching || !collapsed.has(topic.id)}
                aria-controls={`layers-${topic.id || 'other'}`}
                disabled={searching}
                onClick={() => toggle(topic.id)}
              >
                <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
                  <path d="m9 6 6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {topic.label}
                <span className="layers-topic-count">{topic.variables.length}</span>
              </button>
            </h3>
            <div id={`layers-${topic.id || 'other'}`} hidden={!searching && collapsed.has(topic.id)}>
              {topic.variables.map((variable) => (
                <button
                  key={variable.id}
                  type="button"
                  role="listitem"
                  className="layer-row"
                  aria-pressed={variable.id === layerId}
                  title={variable.description ?? undefined}
                  onClick={() => onVariable(variable.id === layerId ? undefined : variable.id)}
                >
                  <span className="layer-row-label">{variable.label}</span>
                  <span className="layer-row-unit">
                    {(measures.get(variable.id) ?? [variable])
                      .map((item) => (isCount(item.unit) ? 'nº' : item.unit === '%' ? '%' : ''))
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
