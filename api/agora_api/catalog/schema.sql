-- Agora's catalogue: what data exists, about what, and where it is. Values stay in Parquet.

CREATE TABLE levels (
  id TEXT PRIMARY KEY,          -- census_section, municipality, …
  rank INTEGER NOT NULL,        -- 0 = most detailed
  label_es TEXT NOT NULL,
  label_en TEXT NOT NULL
);

CREATE TABLE entities (
  id TEXT PRIMARY KEY,          -- es:ine:mun:28079
  level TEXT NOT NULL REFERENCES levels(id),
  code TEXT NOT NULL,           -- INE code (es for Spain)
  name TEXT NOT NULL,           -- Madrid; for census units, their number (Sección 001)
  label TEXT NOT NULL,          -- what to show: Distrito 05 · Sección 001 · Madrid
  parent_id TEXT,
  searchable INTEGER NOT NULL DEFAULT 0,
  -- Bounding box (EPSG:4326), to fit the map to the unit.
  west REAL, south REAL, east REAL, north REAL
);
CREATE INDEX entities_parent ON entities(parent_id);
CREATE INDEX entities_level ON entities(level);

-- Name search with accents folded (getafe, alacant, a coruna…).
CREATE VIRTUAL TABLE entities_fts USING fts5(name, label, content='entities', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');

CREATE TABLE topics (
  id TEXT PRIMARY KEY,
  label_es TEXT NOT NULL,
  label_en TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0  -- topics show by position, then id (a one-off census after the series)
);

-- Every table Agora has: statistics (values by unit and period, which variables are computed from),
-- geometries (boundaries, cadastre…) and reference tables (classifications, territorial units).
CREATE TABLE datasets (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  pipeline TEXT NOT NULL,
  publisher TEXT,
  license TEXT,                 -- JSON: id, url, attribution
  source TEXT,                  -- JSON, as in the pipeline's catalog.json
  dimensions TEXT NOT NULL,     -- JSON list of dimension ids (statistics only)
  base_level TEXT,
  frequency TEXT,               -- statistics: yearly (period 2025) | monthly (period 202509)
  path_template TEXT NOT NULL,  -- processed/…/{level}.parquet, or the output's path as its catalog.json gives it
  tags TEXT NOT NULL DEFAULT '[]',  -- JSON list: the catalog.json's, and imputed, derived, experimental, single_edition, no_license, not_downloadable found when building
  kind TEXT NOT NULL,           -- statistics | geometry | reference
  entity_type TEXT,             -- geometry and reference: what each row is (municipality, cadastral_parcel, classification_item…)
  validity TEXT,                -- JSON, as in the catalog.json: kind (current, snapshot, edition), as_of, description
  fields TEXT,                  -- JSON: [{name, type, description}], as in the catalog.json
  downloadable INTEGER NOT NULL, -- 0 when its license isn't known or doesn't allow redistributing it: listed, but its files aren't served
  publisher_url TEXT,
  measure TEXT,                 -- statistics: JSON {id, unit, aggregation}, what `value` is
  run TEXT,                     -- JSON, from the output's meta.json: generated_at, retrieved_at, source_url, tables, checks
  tiles TEXT,                   -- geometries: the vector tile layer that draws them
  extent TEXT,                  -- geometries: JSON [west, south, east, north] (EPSG:4326)
  focus TEXT,                   -- geometries: JSON bbox of the municipality with most rows, to show layers only seen up close
  description TEXT,             -- JSON {es, en}: what it measures, what it's for and how to read it
  processing TEXT,              -- JSON {es, en}: how it was made (sources joined, imputation, checks)
  keywords TEXT,                -- JSON {es: [...], en: [...]}
  topics TEXT NOT NULL DEFAULT '[]'  -- JSON list of topic ids (statistics also take their variables')
);

-- The licenses datasets are under (pipelines/licenses.json); a dataset's license names one by id.
CREATE TABLE licenses (
  id TEXT PRIMARY KEY,          -- CC-BY-4.0, DGC-INSPIRE-2016
  short TEXT NOT NULL,
  title_es TEXT NOT NULL,
  title_en TEXT NOT NULL,
  url TEXT,
  legal_url TEXT,
  open INTEGER NOT NULL,        -- 1 for an open license (reuse and redistribution allowed)
  summary TEXT NOT NULL,        -- JSON {es, en}
  permissions TEXT NOT NULL,    -- JSON {es: [...], en: [...]}
  conditions TEXT NOT NULL,     -- JSON {es: [...], en: [...]}
  limitations TEXT NOT NULL     -- JSON {es: [...], en: [...]}
);

-- The files a dataset's rows are in: one per level (statistics), edition or province (geometries),
-- or one; `filter` keeps only its rows of a file it shares with others ({column: value}).
CREATE TABLE dataset_files (
  dataset_id TEXT NOT NULL REFERENCES datasets(id),
  name TEXT NOT NULL,           -- census_section, 2026, 28, items…: the download's file name
  label TEXT NOT NULL,
  path TEXT NOT NULL,           -- processed/… (the pipelines' outputs), or next to the catalogue
  filter TEXT,                  -- JSON {column: value}, or null for every row
  rows INTEGER NOT NULL,
  bytes INTEGER,                -- the file's size, when the dataset has all of it
  position INTEGER NOT NULL,
  sha256 TEXT,                  -- the file's checksum, when the dataset has all of it
  modified INTEGER,             -- the file's modification time (ns), to reuse its checksum in the next build
  PRIMARY KEY (dataset_id, name)
);

CREATE TABLE dimensions (
  id TEXT PRIMARY KEY,
  label_es TEXT NOT NULL,
  label_en TEXT NOT NULL,
  classification TEXT,          -- its values are this classification's codes (cno11: 1–9)
  groups_of TEXT                -- its values group this classification's codes (see classification_correspondences)
);

CREATE TABLE dimension_values (
  dimension_id TEXT NOT NULL REFERENCES dimensions(id),
  code TEXT NOT NULL,
  label TEXT NOT NULL,
  position INTEGER NOT NULL,
  parent TEXT,                  -- the value this one is part of (France → EU → Europe), for showing them nested
  PRIMARY KEY (dimension_id, code)
);

CREATE TABLE variables (
  id TEXT PRIMARY KEY,
  topic_id TEXT REFERENCES topics(id),
  label_es TEXT NOT NULL,
  label_en TEXT NOT NULL,
  description_es TEXT,
  description_en TEXT,
  unit TEXT NOT NULL,
  kind TEXT NOT NULL,           -- count | ratio
  scale REAL NOT NULL DEFAULT 1,
  default_facet TEXT,           -- JSON: level → facet id
  options TEXT,                 -- JSON: dimensions the user picks ({dimension, values, default, range?, control?}); facets say "$dimension"
  measure_of TEXT,              -- another measure (a share) of this variable: the web shows both as one layer
  palette TEXT NOT NULL DEFAULT 'sequential'  -- sequential (magnitude) | diverging (above or below zero)
);

CREATE TABLE variable_facets (
  variable_id TEXT NOT NULL REFERENCES variables(id),
  id TEXT NOT NULL,             -- official, census…
  label_es TEXT NOT NULL,
  label_en TEXT NOT NULL,
  dataset_id TEXT NOT NULL REFERENCES datasets(id),
  numerator TEXT NOT NULL,      -- JSON filter: dimension → code or list of codes (summed)
  denominator TEXT,             -- JSON filter, for ratios; or {dataset, filter} from another (yearly) dataset
  position INTEGER NOT NULL,
  PRIMARY KEY (variable_id, id)
);

-- What's actually on disk: each dataset's levels and periods.
CREATE TABLE coverage (
  dataset_id TEXT NOT NULL REFERENCES datasets(id),
  level TEXT NOT NULL REFERENCES levels(id),
  period INTEGER NOT NULL,
  rows INTEGER NOT NULL,
  entities INTEGER NOT NULL,
  PRIMARY KEY (dataset_id, level, period)
);

CREATE TABLE build (key TEXT PRIMARY KEY, value TEXT);

-- Statistical classifications (not geographic): occupations, activities, education, products.
CREATE TABLE classifications (
  id TEXT PRIMARY KEY,          -- cnae2025, cno11, cned2014_a, …
  title_es TEXT NOT NULL,
  title_en TEXT NOT NULL,
  version TEXT,
  levels TEXT NOT NULL,         -- JSON: the level names, from the top
  publisher TEXT,               -- JSON
  license TEXT,                 -- JSON
  source_url TEXT
);

CREATE TABLE classification_items (
  classification_id TEXT NOT NULL REFERENCES classifications(id),
  code TEXT NOT NULL,
  label TEXT NOT NULL,
  level INTEGER NOT NULL,       -- 1 = the top
  level_name TEXT NOT NULL,
  parent TEXT,                  -- the code of the item it belongs to
  position INTEGER NOT NULL,    -- the publisher's order
  PRIMARY KEY (classification_id, code)
);

-- Correspondences between classifications (or from the platform's own codes, like education_level):
-- one row per pair, as the publisher gives them (an item can match several).
CREATE TABLE classification_correspondences (
  from_classification TEXT NOT NULL,
  from_code TEXT NOT NULL,
  to_classification TEXT NOT NULL,
  to_code TEXT NOT NULL,
  to_label TEXT,                -- for classifications not in the catalogue (CIUO-08, CINE-2011)
  note TEXT
);
CREATE INDEX classification_correspondences_from ON classification_correspondences (from_classification, from_code);
CREATE INDEX classification_correspondences_to ON classification_correspondences (to_classification, to_code);
