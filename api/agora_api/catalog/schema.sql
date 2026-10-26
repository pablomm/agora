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
  frequency TEXT NOT NULL,      -- yearly (period 2025) | monthly (period 202509)
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
