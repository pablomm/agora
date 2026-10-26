import { useEffect, useId, useRef, useState } from 'react'
import { copy } from '../app/copy'
import { api, type Place } from '../data/api'

/** Wait after the last keystroke before searching. */
const DEBOUNCE_MS = 200

/**
 * Search for an autonomous community, province or municipality by name; picking one goes there.
 * Narrow ("Buscar…") until it's clicked to type, then wider; it narrows again on blur.
 */
export function SearchBox({ onPick }: { onPick: (place: Place) => void }) {
  const [query, setQuery] = useState('')
  // Results belong to the query they answer: a newer query hides them until its own arrive.
  const [found, setFound] = useState<{ query: string; places: Place[] }>()
  const text = query.trim()
  const results = text.length >= 2 && found?.query === text ? found.places : undefined
  const [active, setActive] = useState(0)
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const listId = useId()
  const root = useRef<HTMLFormElement>(null)

  useEffect(() => {
    if (text.length < 2) return
    let current = true
    const timer = setTimeout(() => {
      api.search(text).then(
        (places) => {
          if (!current) return
          setFound({ query: text, places })
          setActive(0)
        },
        () => current && setFound({ query: text, places: [] }),
      )
    }, DEBOUNCE_MS)
    return () => {
      current = false
      clearTimeout(timer)
    }
  }, [text])

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [])

  const pick = (place: Place) => {
    onPick(place)
    setQuery(place.name)
    setOpen(false)
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape' && !(open && results?.length)) event.currentTarget.blur()
    if (!results?.length) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      setActive((index) => (index + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      pick(results[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const showList = open && results !== undefined
  return (
    <form ref={root} className={expanded ? 'search is-expanded' : 'search'} role="search" onSubmit={(event) => event.preventDefault()}>
      <svg className="search-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="m15 15 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <input
        type="search"
        aria-label={copy.search.label}
        placeholder={expanded ? copy.search.placeholder : copy.search.folded}
        autoComplete="off"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && results.length ? `${listId}-${active}` : undefined}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setOpen(true)
        }}
        onFocus={() => {
          setOpen(true)
          setExpanded(true)
        }}
        onBlur={() => setExpanded(false)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul id={listId} className="search-results" role="listbox">
          {results.length === 0 && <li className="search-note">{copy.search.noResults}</li>}
          {results.map((place, index) => (
            <li
              key={place.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              className={index === active ? 'is-active' : undefined}
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => pick(place)}
              onPointerEnter={() => setActive(index)}
            >
              <strong>{place.name}</strong>
              <small>
                {copy.search.levels[place.level] ?? place.level}
                {place.parent_name && place.level !== 'autonomous_community' ? ` · ${place.parent_name}` : ''}
              </small>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
