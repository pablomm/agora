# Agora pipelines

Scripts that download public data, normalise it and produce the files the platform and the
catalogue are built from. One folder per pipeline under `pipelines/`, each with one or more plain
Python scripts; helpers they share live in `common/`.

## Setup

Python 3.13 in a virtualenv:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .   # installs `common`, so any script can import it
```

The tile builds also need [tippecanoe](https://github.com/felt/tippecanoe): `brew install tippecanoe`.

## Running

Each pipeline is a script, run from anywhere with the virtualenv active:

```sh
python pipelines/provinces/provinces.py
```

## Layout

```
common/                 # shared helpers, installed in the virtualenv
  paths.py              # where data is downloaded to and written
  download.py           # safe downloads and checksums
  ign.py                # IGN's WFS INSPIRE administrative units: request and parsing
  metadata.py           # run details written next to each output
pipelines/
  <pipeline>/
    <script>.py         # download → parse and validate → write; one or more per pipeline
    catalog.json        # what it adds to the catalogue (entity types, relations, datasets)
    README.md           # source, license, validity, identifiers and output
data/                   # not in git; reproducible from the pipelines
  raw/<pipeline>/<retrieval date>/   # downloads, kept as is
  processed/<pipeline>/              # normalised output + <name>.meta.json run details
```

Set `AGORA_DATA_DIR` to keep data somewhere else.

## Conventions

- **Identifiers** are stable and readable, built from the official code where one exists:
  `es:ine:ccaa:13`, `es:ine:prov:28`, `es:ine:mun:28079`, `es:ine:dist:2807901`, `es:ine:sec:2807901001`.
- **Raw downloads are never edited.** Sources that aren't downloaded by a pipeline are put in
  `data/raw/<pipeline>/<date>/` by hand (`postal_codes`) or by an import script from a local
  archive (`cadastre`); back up what's only there.
- **Every run is traceable**: it records its retrieval date, request and the raw
  file's checksum, so an output can be traced back to exactly what was downloaded.
- **Validity**: each dataset states whether it's a current snapshot (valid as of retrieval) or a
  dated edition, in its `catalog.json` and README.
- **Geometry**: EPSG:4326, at the source's resolution. Simplification happens when building tiles.
- **Shared code goes to `common/` once a second pipeline needs it**, not before.
- **Fail loudly**: a pipeline stops on unexpected codes, counts or geometry instead of writing
  partial output.
- Code, comments and docs in English.

## Pipelines

| Pipeline | Entities | Source |
|---|---|---|
| [autonomous_communities](pipelines/autonomous_communities/README.md) | 17 autonomous communities + Ceuta and Melilla | IGN, WFS INSPIRE unidades administrativas |
| [cadastre](pipelines/cadastre/README.md) | 13,209,772 urban parcels and 183,133 cadastral polygons (all municipalities), 1,323,594 cadastral zones (2023) | Catastro INSPIRE and the foral cadastres of Navarra and the Basque Country, imported from local archives |
| [census_sections](pipelines/census_sections/README.md) | 36,669 census sections + 10,452 census districts (2026) | INE, cartografía digitalizada de secciones censales |
| [municipalities](pipelines/municipalities/README.md) | 8,132 municipalities + 81 shared territories | IGN, WFS INSPIRE unidades administrativas |
| [population](pipelines/population/README.md) | Population: official figures by municipality (1996–2025), census by sex and age (sections, 2021–2025) and by sex, age and nationality (municipalities), aggregated up | INE |
| [postal_codes](pipelines/postal_codes/README.md) | 10,874 postal code areas (January 2024) | GeoParquet from an earlier project (placed by hand in `data/raw/`) |
| [provinces](pipelines/provinces/README.md) | 52 provinces | IGN, WFS INSPIRE unidades administrativas |
| [tiles](pipelines/tiles/README.md) | Vector tiles of the boundaries above | The pipelines above |
