import { copy } from '../app/copy'
import type { Place } from '../data/api'
import { SearchBox } from './SearchBox'

/** Name and place search. */
export function Header({ onPlace }: { onPlace: (place: Place) => void }) {
  return (
    <header className="floating-header">
      <h1>
        <svg className="header-logo" viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
          <rect width="32" height="32" rx="8" fill="var(--accent)" />
          <path d="M8 22V14M13 22V9M18 22v-6M23 22V11" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
        </svg>
        <span className="header-name">{copy.appName}</span>
      </h1>
      <SearchBox onPick={onPlace} />
    </header>
  )
}
