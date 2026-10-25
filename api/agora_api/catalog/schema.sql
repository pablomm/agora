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

CREATE TABLE topics (id TEXT PRIMARY KEY, label_es TEXT NOT NULL, label_en TEXT NOT NULL);

CREATE TABLE datasets (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  pipeline TEXT NOT NULL,
  publisher TEXT,
  license TEXT,                 -- JSON: id, url, attribution
  source TEXT,                  -- JSON, as in the pipeline's catalog.json
  dimensions TEXT NOT NULL,     -- JSON list of dimension ids
  base_level TEXT,
  path_template TEXT NOT NULL   -- processed/…/{level}.parquet
);

CREATE TABLE dimensions (
  id TEXT PRIMARY KEY,
  label_es TEXT NOT NULL,
  label_en TEXT NOT NULL
);

CREATE TABLE dimension_values (
  dimension_id TEXT NOT NULL REFERENCES dimensions(id),
  code TEXT NOT NULL,
  label TEXT NOT NULL,
  position INTEGER NOT NULL,
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
  options TEXT                  -- JSON: dimensions the user picks ({dimension, values, default, range?}); facets say "$dimension"
);

CREATE TABLE variable_facets (
  variable_id TEXT NOT NULL REFERENCES variables(id),
  id TEXT NOT NULL,             -- official, census…
  label_es TEXT NOT NULL,
  label_en TEXT NOT NULL,
  dataset_id TEXT NOT NULL REFERENCES datasets(id),
  numerator TEXT NOT NULL,      -- JSON filter: dimension → code or list of codes (summed)
  denominator TEXT,             -- JSON filter, for ratios
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
