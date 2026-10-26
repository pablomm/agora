import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { copy } from '../app/copy'
import { fold } from '../app/format'

export interface SelectItem {
  id: string
  label: string
  /** The item this one is part of: shown nested under it. */
  parent?: string | null
}

/**
 * A dropdown with a search box, for long lists (nationalities): the button shows the value picked;
 * opened, typing filters the list (accents and case aside), arrows move, Enter picks, Esc closes.
 * Nested items are indented under their parent; while searching, only the matches show.
 */
export function SearchSelect({ label, items, value, onChange }: { label: string; items: SelectItem[]; value: string; onChange: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const listId = useId()

  const depth = useMemo(() => {
    const parents = new Map(items.map((item) => [item.id, item.parent ?? null]))
    const of = (id: string): number => {
      const parent = parents.get(id)
      return parent && parents.has(parent) ? 1 + of(parent) : 0
    }
    return new Map(items.map((item) => [item.id, of(item.id)]))
  }, [items])
  const groups = useMemo(() => new Set(items.map((item) => item.parent).filter(Boolean)), [items])
  const shown = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean)
    return words.length ? items.filter((item) => words.every((word) => fold(item.label).includes(word))) : items
  }, [items, query])
  const current = items.find((item) => item.id === value)

  // Opening starts from the value picked, scrolled into view.
  useEffect(() => {
    if (!open) return
    setQuery('')
    setActive(Math.max(0, items.findIndex((item) => item.id === value)))
  }, [open, items, value])
  useEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView({ block: 'nearest' })
  }, [open, active, shown])
  // A click anywhere else closes it.
  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [open])

  const pick = (id: string) => {
    onChange(id)
    setOpen(false)
  }
  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((index) => Math.min(shown.length - 1, Math.max(0, index + step)))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (shown[active]) pick(shown[active].id)
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="search-select" ref={root}>
      <button type="button" className="search-select-button" aria-haspopup="listbox" aria-expanded={open} aria-label={label} onClick={() => setOpen(!open)}>
        <span>{current?.label ?? value}</span>
        <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
          <path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="search-select-popover">
          <input
            type="search"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={shown[active] ? `${listId}-${shown[active].id}` : undefined}
            aria-label={copy.mapView.searchValues(label)}
            placeholder={copy.mapView.searchValues(label)}
            autoFocus
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setActive(0)
            }}
            onKeyDown={onKey}
          />
          <ul id={listId} role="listbox" aria-label={label} ref={list}>
            {shown.length === 0 && <li className="search-select-empty">{copy.mapView.noValues}</li>}
            {shown.map((item, index) => (
              <li
                key={item.id}
                id={`${listId}-${item.id}`}
                role="option"
                aria-selected={item.id === value}
                className={[index === active && 'is-active', groups.has(item.id) && 'is-group'].filter(Boolean).join(' ')}
                style={{ paddingLeft: 8 + (query ? 0 : depth.get(item.id)! * 12) }}
                onPointerEnter={() => setActive(index)}
                onClick={() => pick(item.id)}
              >
                {item.label}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
