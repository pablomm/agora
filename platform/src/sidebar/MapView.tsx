import { useMemo, useState } from 'react'
import { copy } from '../app/copy'
import { fold, isCount } from '../app/format'
import type { Catalog, Choices, Facet, Variable } from '../data/api'
import { OptionControls, Segmented } from './OptionControls'
import { PeriodControl } from './PeriodControl'

interface Props {
  catalog: Catalog | undefined
  catalogFailed: boolean
  variableId: string | undefined
  onVariable: (id: string | undefined) => void
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
export function MapView({ catalog, catalogFailed, variableId, onVariable, years, period, onPeriod, choices, onChoices, facets, facetId, onFacet }: Props) {
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
  const topics = useMemo(() => {
    if (!catalog) return []
    const words = fold(query).split(/\s+/).filter(Boolean)
    const labels = new Map(catalog.topics.map((topic) => [topic.id, topic.label]))
    const matches = (variable: Variable) => {
      const text = fold(`${variable.label} ${variable.description ?? ''} ${labels.get(variable.topic ?? '') ?? ''}`)
      return words.every((word) => text.includes(word))
    }
    const groups = new Map<string, Variable[]>()
    for (const variable of catalog.variables.filter(matches)) {
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
  }, [catalog, query])

  if (catalogFailed) return <p className="sidebar-empty layers-message">{copy.mapView.unavailableApi}</p>
  if (!catalog) return <p className="sidebar-empty layers-message">{copy.mapView.loading}</p>
  const active = catalog.variables.find((variable) => variable.id === variableId)

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
            <OptionControls options={active.options} choices={choices} onChange={onChoices} />
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
                  aria-pressed={variable.id === variableId}
                  title={variable.description ?? undefined}
                  onClick={() => onVariable(variable.id === variableId ? undefined : variable.id)}
                >
                  <span className="layer-row-label">{variable.label}</span>
                  <span className="layer-row-unit">{isCount(variable.unit) ? 'nº' : variable.unit === '%' ? '%' : ''}</span>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
