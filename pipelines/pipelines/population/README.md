# Population

Population of Spain from INE, by territory and year, downloaded only at each source's most
detailed level and aggregated up the territorial hierarchy (`common/rollup.py`).

```sh
python pipelines/population/official_figures.py   # ~1 min
python pipelines/population/census_annual.py      # ~10 min (54 downloads, one of 690 MB)
```

Needs the provinces pipeline (provinces → autonomous communities).

## Datasets

| Dataset | Source | Base level | Levels | Periods | Dimensions |
|---|---|---|---|---|---|
| `population_official` | Cifras oficiales de población (Revisión del Padrón Municipal), table 29005 | municipality | municipality → province → autonomous community → Spain | 1996–2025 (no 1997: empty in INE's table) | sex |
| `population_sex_age` | Censo de Población anual, tables "Población por sexo y edad (grupos quinquenales)" by province, municipality and section (53 tables, listed in `census_annual.py`) | census section | section → district → municipality → province → autonomous community → Spain | 2021–2025 | sex, five-year age group |
| `population_sex_age_nationality` | Censo de Población anual, table 68535 | municipality | municipality → province → autonomous community → Spain | 2021–2025 | sex, five-year age group, nationality (Spanish/foreign) |

- **Official figures** are each municipality's legal population on 1 January (the Padrón). The
  long series for municipalities, without age or nationality.
- **Annual Population Census** (since 2021) counts the resident population from administrative
  registers. It's not the same measure as the Padrón: don't join both into one series; they're
  separate sources of "population" (`source` in the catalogue).
- INE doesn't cross age and nationality below municipalities, so the third dataset starts there.
- Census districts aren't published: they're aggregated from sections (the district code is the
  section's first seven digits).
- Census sections change every year: a section's figures for a year go with that year's
  cartography (`es:ine:sec:{code}` can be a different area in another year).

## Output

`data/processed/population/{dataset}/{level}.parquet`, one file per level, all with:

| Column | |
|---|---|
| `entity_id` | Catalogue id: `es:ine:sec:…`, `es:ine:dist:…`, `es:ine:mun:…`, `es:ine:prov:…`, `es:ine:ccaa:…`, `es:country:es` |
| `code` | INE code of the unit (`es` for Spain) |
| `period` | Year (figures as of 1 January) |
| `sex` | `total`, `male`, `female` |
| `age` | `total`, `Y0T4`, `Y5T9` … `Y95T99`, `Y_GE100` (census datasets) |
| `nationality` | `total`, `spanish`, `foreign` (`population_sex_age_nationality`) |
| `value` | Persons |
| `origin` | `published` (the base level, as INE publishes it) or `aggregated` (summed from the level below) |

Totals are rows like any other (`sex = total`, `age = total`…), as INE publishes them, so a level's
total and the sum of its parts can be compared. `meta.json` next to each dataset records the
source tables, periods, rows per level and the checks below.

## Checks

Every aggregated level that INE also publishes is compared with INE's figures; any difference
stops the run, except the ones listed in the pipeline as known (with why):

- `population_official`: provinces aggregated from municipalities against table 2852 (downloaded
  only for this). Known: Almería 1996, where INE's province total is 76 people more than the sum of
  its municipalities.
- `population_sex_age`: municipalities and provinces aggregated from sections against the
  municipal and provincial rows of the same tables.
- `population_sex_age_nationality`: provinces aggregated from municipalities against the provincial
  rows of the same table.

Results of the first run (2026-10-25): all exact. `population_sex_age` matched 2,683,362
published municipal values and 17,160 provincial ones; `population_sex_age_nationality`, 51,480
provincial ones; `population_official`, 3,900 provincial ones (plus Almería 1996, known).

**Empty cells** are units that didn't exist that year, not hidden figures: every cell of a
section-year is empty when it is (181 section-years in one of the provincial tables, fewer each year
towards 2025), and the 594 empty municipal cells are Usansolo before it split from Galdakao. They're
left out, so a unit only has rows for the years it existed.

| Dataset | Rows by level |
|---|---|
| `population_official` | municipality 706,128 · province 4,524 · autonomous community 1,653 · Spain 87 |
| `population_sex_age` | section 12,025,728 · district 3,454,044 · municipality 2,683,362 · province 17,160 · autonomous community 6,270 · Spain 330 |
| `population_sex_age_nationality` | municipality 8,050,086 · province 51,480 · autonomous community 18,810 · Spain 990 |

## Code lists

`common/codelists.py`: sex, five-year age groups and Spanish/foreign nationality, as stable English
codes for INE's Spanish labels. An unknown label stops the run.

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
