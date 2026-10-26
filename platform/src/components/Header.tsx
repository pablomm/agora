import { copy } from '../app/copy'
import type { Place } from '../data/api'
import { SearchBox } from './SearchBox'

/** Name and place search. */
export function Header({ onPlace }: { onPlace: (place: Place) => void }) {
  return (
    <header className="floating-header">
      <h1>
        <img className="header-logo" src="/favicon.svg" width="26" height="26" alt="" />
        <span className="header-name">{copy.appName}</span>
      </h1>
      <SearchBox onPick={onPlace} />
    </header>
  )
}
