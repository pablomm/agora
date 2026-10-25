import { copy } from '../app/copy'

/** Name and city search. The search doesn't look anything up yet. */
export function Header() {
  return (
    <header className="floating-header">
      <h1>
        <svg className="header-logo" viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
          <rect width="32" height="32" rx="8" fill="var(--accent)" />
          <path d="M8 22V14M13 22V9M18 22v-6M23 22V11" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
        </svg>
        <span className="header-name">{copy.appName}</span>
      </h1>
      <form className="search" role="search" onSubmit={(event) => event.preventDefault()}>
        <svg className="search-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="m15 15 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input type="search" aria-label={copy.search.label} placeholder={copy.search.placeholder} autoComplete="off" />
      </form>
    </header>
  )
}
