# Population

Population of Spain from INE, by territory and year, downloaded only at each source's most
detailed level and aggregated up the territorial hierarchy (`common/rollup.py`).

```sh
python pipelines/population/official_figures.py   # ~1 min
python pipelines/population/census_annual.py      # ~10 min (54 downloads, one of 690 MB)
python pipelines/population/census_origin.py      # ~4 min, plus ~3.5 GB of downloads (108 tables)
```

Needs the provinces pipeline (provinces → autonomous communities).

## Datasets

| Dataset | Source | Base level | Levels | Periods | Dimensions |
|---|---|---|---|---|---|
| `population_official` | Cifras oficiales de población (Revisión del Padrón Municipal), table 29005 | municipality | municipality → province → autonomous community → Spain | 1996–2025 (no 1997: empty in INE's table) | sex |
| `population_sex_age` | Censo de Población anual, tables "Población por sexo y edad (grupos quinquenales)" by province, municipality and section (53 tables, listed in `census_annual.py`) | census section | section → district → municipality → province → autonomous community → Spain | 2021–2025 | sex, five-year age group |
| `population_sex_age_nationality` | Censo de Población anual, table 68535 | municipality | municipality → province → autonomous community → Spain | 2021–2025 | sex, five-year age group, nationality (Spanish/foreign) |
| `population_nationality` | Censo de Población anual, "Población por sexo y país de nacionalidad (principales países)", one table per province (52, listed in `census_origin.py`) | census section | section → district → municipality → province → autonomous community → Spain | 2021–2025 | sex, nationality (`nationality_main`: 18 countries and rests, continents) |
| `population_nationality_detail` | Censo de Población anual, tables 66323 (main nationalities) and 68537 (country groups, only to check) | municipality | municipality → province → autonomous community → Spain | 2021–2025 | sex, nationality (`nationality_detail`: 52 countries and rests, INE's country groups, continents) |
| `population_birth_country` | Censo de Población anual, "Población por sexo y país de nacimiento (principales países)", one table per province (52) | census section | section → … → Spain | 2021–2025 | sex, country of birth (`birth_country_main`) |
| `population_birth_country_detail` | Censo de Población anual, tables 66322 (main countries) and 68538 (country groups, only to check) | municipality | municipality → … → Spain | 2021–2025 | sex, country of birth (`birth_country_detail`) |

- **Official figures** are each municipality's legal population on 1 January (the Padrón). The
  long series for municipalities, without age or nationality.
- **Annual Population Census** (since 2021) counts the resident population from administrative
  registers. It's not the same measure as the Padrón: don't join both into one series; they're
  separate sources of "population" (`source` in the catalogue).
- INE doesn't cross age and nationality below municipalities, so the third dataset starts there.
- **Nationality and country of birth** come in two lists: about twenty main countries by census
  section, and about sixty by municipality. INE closes each continent or group with its rest ("Otros
  países de África"), so the countries add up to their group exactly. Each dataset nests its list in
  one dimension (country → group → continent → foreign/abroad), with every group as the sum of what
  it holds; the lists are separate dimensions because a rest means something else in each ("Otros
  países de Europa" is Europe but four countries by section, and non-EU Europe but six by
  municipality). Countries are ISO 3166-1 alpha-3 codes (`MAR`, `GBR`) in every list. INE's national
  tables by section (65036, 65035) repeat the provincial ones row by row and aren't used.
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
| `nationality_main`, `nationality_detail` | `total`, `spanish`, `foreign`, continents and groups (`europe`, `eu`, `africa`, `south_america`…), countries (`MAR`…) and rests (`africa_other`…): the nationality datasets |
| `birth_country_main`, `birth_country_detail` | the same with `spain` and `abroad`: the country of birth datasets |
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
- The nationality and country of birth datasets: the total from Spanish plus foreign (born in Spain
  plus abroad) against INE's total, at the base level; the levels above against the same tables'
  rows; and, in the detail datasets, every country group against INE's "grandes grupos" tables.

Results of the first run (2026-10-25; the nationality and birth datasets, 2026-10-26): all exact. `population_sex_age` matched 2,683,362
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
| `population_nationality` | section 14,758,848 · district 4,239,054 · municipality 3,293,217 · province 21,060 · autonomous community 7,695 · Spain 405 |
| `population_nationality_detail` | municipality 8,781,912 · province 56,160 · autonomous community 20,520 · Spain 1,080 |
| `population_birth_country` | section 14,212,224 · district 4,082,052 · municipality 3,171,246 · province 20,280 · autonomous community 7,410 · Spain 390 |
| `population_birth_country_detail` | municipality 8,659,941 · province 55,380 · autonomous community 20,235 · Spain 1,065 |

## Code lists

`common/codelists.py`: sex, five-year age groups, Spanish/foreign nationality, and countries and
country groups (`COUNTRY_MAIN`, `COUNTRY_DETAIL`), as stable English codes for INE's Spanish labels. An unknown label stops the run.

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
