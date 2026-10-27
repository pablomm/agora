import { copy } from '../app/copy'
import type { Catalog, LicenseEntry } from '../data/api'
import { datasetHref } from './entries'

interface Props {
  catalog: Catalog
  license: LicenseEntry
}

/**
 * A license's page: what it is, what it allows, requires and limits, its official texts, the
 * sources that use it and every dataset under it.
 */
export function LicensePage({ catalog, license }: Props) {
  const datasets = catalog.datasets.filter((dataset) => license.datasets.includes(dataset.id))
  const publishers = [...new Set(datasets.map((dataset) => dataset.publisher).filter((publisher): publisher is string => Boolean(publisher)))].sort((a, b) =>
    a.localeCompare(b, 'es'),
  )
  const groups: [string, string[], string][] = [
    [copy.license.permissions, license.permissions.es, 'is-permission'],
    [copy.license.conditions, license.conditions.es, 'is-condition'],
    [copy.license.limitations, license.limitations.es, 'is-limitation'],
  ]
  return (
    <div className="catalog-content dataset-page">
      <nav className="dataset-breadcrumb">
        <a href="#">{`← ${copy.license.back}`}</a>
      </nav>
      <header className="dataset-header">
        <span className="catalog-card-topic">{`${copy.license.kind} · ${license.short}`}</span>
        <h1>{license.title_es}</h1>
        <div className="dataset-header-meta">
          <span className={`chip is-tag ${license.open ? 'is-open' : 'is-restricted'}`}>{license.open ? copy.dataset.open : copy.dataset.restricted}</span>
          <code>{license.id}</code>
        </div>
        <p className="dataset-lead">{license.summary.es}</p>
        <div className="dataset-actions">
          {/* A license with one document (the Catastro's PDF) links it as its legal text. */}
          {license.url && (
            <a className="dataset-link" href={license.url} target="_blank" rel="noreferrer">
              {license.legal_url === license.url ? copy.license.legal : copy.license.text}
            </a>
          )}
          {license.legal_url && license.legal_url !== license.url && (
            <a className="dataset-link" href={license.legal_url} target="_blank" rel="noreferrer">
              {copy.license.legal}
            </a>
          )}
        </div>
      </header>

      <div className="license-terms">
        {groups.map(([title, items, kind]) => (
          <section key={title} className={`dataset-card ${kind}`}>
            <h2>{title}</h2>
            <ul className="dataset-list">
              {items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {publishers.length > 0 && (
        <section className="dataset-section">
          <h2>{copy.license.publishers}</h2>
          <ul className="dataset-keywords">
            {publishers.map((publisher) => (
              <li key={publisher}>{publisher}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="dataset-section">
        <h2>{copy.license.datasets(datasets.length)}</h2>
        <ul className="dataset-tiles">
          {datasets.map((dataset) => (
            <li key={dataset.id}>
              <a className="dataset-tile" href={datasetHref(dataset.id)}>
                <span className="dataset-tile-kicker">{copy.catalog.kinds[dataset.kind]}</span>
                <strong>{dataset.title}</strong>
                <span className="dataset-tile-meta">{[...new Set([dataset.publisher, dataset.license?.attribution].filter(Boolean))].join(' · ')}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
