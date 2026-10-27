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
| [businesses](pipelines/businesses/README.md) | Companies by municipality and main activity (2012–2025), hidden values imputed; aggregated up | INE, Directorio Central de Empresas (DIRCE) |
| [census_2021](pipelines/census_2021/README.md) | Dwellings, households and family nuclei by census section (2021): type, tenure, year built, floor area, building, household structure, nuclei, children; dwelling use and electricity use by district | INE, Censos de Población y Viviendas 2021 (published tables and custom tables) |
| [census_sections](pipelines/census_sections/README.md) | 36,669 census sections + 10,452 census districts (2026) | INE, cartografía digitalizada de secciones censales |
| [classifications](pipelines/classifications/README.md) | CNAE-2025, CNAE-2009, CNO-11, CNED-2014 A and F, CPA 2.2, and their correspondences (not geographic) | INE |
| [employment](pipelines/employment/README.md) | Registered unemployment, job seekers and contracts by municipality, monthly (2006–2026), hidden values imputed; population 16+ by relation with activity (2021–2024) and employed by occupation, sector and status (2021–2023) by census section; aggregated up | SEPE open data, INE annual census |
| [housing](pipelines/housing/README.md) | Tourist dwellings, their beds and share of all dwellings, census sections to Spain, twice a year (2020–2026) | INE, experimental statistic on tourist dwellings |
| [income](pipelines/income/README.md) | Household income by census section (2015–2024): mean and median, sources, Gini and P80/P20, population under thresholds; aggregated up | INE, Atlas de Distribución de Renta de los Hogares (ADRH) |
| [income_distribution](pipelines/income_distribution/README.md) | Each unit's income distribution fitted to a Dagum, from census sections to Spain (2015–2024) | The income pipeline |
| [municipalities](pipelines/municipalities/README.md) | 8,132 municipalities + 81 shared territories | IGN, WFS INSPIRE unidades administrativas |
| [population](pipelines/population/README.md) | Population: official figures by municipality (1996–2025); census by sex and age, nationality, country of birth, arrival and education (sections, 2021–2025), and by marital status, previous residence and studies (municipalities); aggregated up | INE |
| [postal_codes](pipelines/postal_codes/README.md) | 10,874 postal code areas (January 2024) | GeoParquet from an earlier project (placed by hand in `data/raw/`) |
| [provinces](pipelines/provinces/README.md) | 52 provinces | IGN, WFS INSPIRE unidades administrativas |
| [tiles](pipelines/tiles/README.md) | Vector tiles of the boundaries above | The pipelines above |

Every dataset, with its variables, levels and years, and the sources planned: [SOURCES.md](../SOURCES.md).
