# Population

Population of Spain from INE, by territory and year, downloaded only at each source's most
detailed level and aggregated up the territorial hierarchy (`common/rollup.py`).

```sh
python pipelines/population/official_figures.py   # ~1 min
python pipelines/population/census_annual.py      # ~10 min (54 downloads, one of 690 MB)
python pipelines/population/census_origin.py      # ~5 min, plus ~5.4 GB of downloads (316 tables)
python pipelines/population/census_municipal.py   # ~1 min (9 tables), after census_origin
python pipelines/population/census_marital.py     # seconds (3 tables), after census_annual
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
| `population_birthplace` | Censo de Población anual, "Población por sexo y relación entre lugar de nacimiento y lugar de residencia", one table per province (52) | census section | section → … → Spain | 2021–2025 | sex, birthplace against residence (`birthplace`) |
| `population_arrival_spain` | Censo de Población anual, "Población por año de llegada a España (agregado) y sexo", one table per province (52) | census section | section → … → Spain | 2021–2025 | sex, arrival in Spain (`arrival_spain`) |
| `population_previous_residence` | Censo de Población anual, table 70382 | municipality (500 residents or more: 4,144) | municipality only | 2021–2025 | sex, age (<16, 16–64, 65+), previous residence |
| `population_arrival_municipality` | Censo de Población anual, table 70371 | municipality (151 provincial capitals and main cities) | municipality only | 2021–2025 | sex, age (8 groups), arrival in the municipality (years before the census) |
| `population_residence_year_ago` | Censo de Población anual, table 79570 | municipality (the same 151) | municipality only | 2021–2025 | sex, age (<16, 16–64, 65+), nationality (Spanish/foreign), residence a year before |
| `population_education` | Censo de Población anual, "Población de 15 y más años por sexo y nivel de estudios (agrupado)", one table per province (52) | census section | section → … → Spain | 2021–2024 | sex, level of education (`education_level`, grouped) |
| `population_education_born` | Censo de Población anual, "… por país de nacimiento (España/extranjero) y nivel de estudios (agrupado)", one table per province (52) | census section | section → … → Spain | 2021–2024 | born in Spain/abroad, level of education (grouped) |
| `population_education_gender_gap` | Derived from `population_education` | every level | section → … → Spain | 2021–2024 | level of education; the value is the share of women with it minus the share of men, in points |
| `population_education_detail` | Censo de Población anual, tables 66621 and 66622 | municipality (500 residents or more) | municipality only | 2021–2024 | sex, birthplace or nationality (`birth_nationality`), level of education (detail, nested in the groups) |
| `population_studying` | Censo de Población anual, tables 66627 and 66628 | municipality (500 residents or more) | municipality only | 2021–2024 | sex, birthplace or nationality, studies in progress |
| `population_education_age` | Censo de Población anual, table 66620 | municipality (500 residents or more) | municipality only | 2021–2024 | sex, age (11 groups), level of education (grouped) |
| `population_marital_status` | Censo de Población anual, tables 76306 (municipalities of 500 residents or more) and 76312 (50 to 500); 76288 (provinces, communities, Spain) to impute and check | municipality | municipality → province → autonomous community → Spain | 2021–2024 | sex, marital status (residents aged 16 and over) |
| `population_marital_status_age` | Censo de Población anual, table 76306 | municipality (500 residents or more) | municipality only | 2021–2024 | sex, age (16–34, 35–54, 55–74, 75+), marital status |
| `population_mean_age` | Derived from `population_sex_age` (no download but table 68527, to check) | every level of `population_sex_age` | section → … → Spain | 2021–2025 | sex; the value is a mean age, in years (not a sum) |

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
- **Birthplace against residence**: same municipality, another municipality of the province,
  another province of the community, another community, abroad; `born_in_spain` is the sum of
  the first four.
- **Migration and mobility.** By census section INE only publishes arrival in Spain, in bands
  (after 2020, 2011–2020, 2001–2010, before 2001, always in Spain): "after 2020" is the last year
  in 2021 and the last five in 2025. INE hides small sections and municipalities whole (2,876
  section-years, 2,856 municipality-years, all under 86 residents): hidden municipalities share
  their province's residual and hidden sections their municipality's, by residents of each sex
  (`common/imputation.py`); imputed totals are 1.4 people off the census population on average.
  Previous residence, arrival in the municipality and residence a year before are published only
  for some municipalities (500 residents or more, or the 151 main cities), so they aren't
  aggregated up. Arrival in the municipality only dates those who came from another Spanish
  municipality (those who came straight from abroad are "since they came to Spain"); its calendar
  years become years before each census (within the last 1, 2, 3, 5 years, always exact).
- **Education** (residents aged 15 and over, 2021–2024). By census section INE publishes four
  groups (primary or less, lower secondary, upper secondary, tertiary), by sex or by birthplace;
  hidden units are imputed like arrival in Spain, weighed by residents aged 15 and over (imputed
  sections are 0.5 people off their census population of that age, on average). Here INE leaves
  hidden municipalities empty rather than ".": an empty municipality with sections that year is
  hidden. In municipalities of 500 residents or more the levels come in detail (no schooling,
  primary, upper secondary general or vocational, higher vocational, four university levels),
  nested in the same groups, which match the sections summed up exactly. Birthplace and
  nationality come from two tables and share one dimension, `birth_nationality`. The gender gap is
  the share of women with a level minus the share of men, at every level.
- **Marital status** (residents aged 16 and over, 2021–2024): single, married, widowed, divorced or
  separated (INE gives them together), not stated. INE publishes no census sections: municipalities
  of 500 residents or more (by sex and age, 16–34, 35–54, 55–74, 75+) and of 50 to 500 (by sex),
  and provinces, communities and Spain. Municipalities under 50 residents (569 a year) take their
  province's residual, by sex and marital status, shared out by their residents aged 16 and over
  (20 and over plus four fifths of 15–19, from `population_sex_age`): each province's residual is
  within 2% of those residents. Usansolo (48916, split from Galdakao) isn't in the municipal tables
  in 2024 but is in its province's total, and is imputed like the rest. By age, only municipalities
  of 500 residents or more, as published (not aggregated up). Crosses with nationality or
  birthplace exist only for provinces and communities, and aren't used.
- **Mean age** counts each five-year group at its midpoint (2.5 for 0–4… 102.5 for 100+), at every
  level from the aggregated groups. Against INE's mean age by province, sex and year (table
  68527, 780 values) it's at most 0.034 years off; the run fails beyond 0.1. Other age indicators
  (ageing, dependency, oldest-old) are ratios of sums of age groups: they're defined in the
  catalogue over `population_sex_age`, with under 15 as young (INE uses under 16, which five-year
  groups can't split, so its ageing index is lower).
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
| `birthplace` | `total`, `born_in_spain`, `same_municipality`, `same_province`, `same_community`, `other_community`, `abroad` |
| `arrival_spain` | `total`, `arrived`, `after_2020`, `2011_2020`, `2001_2010`, `before_2001`, `always_in_spain` |
| `previous_residence` | `total`, `always_here`, `came_from_elsewhere` (= `other_municipality` + `abroad`), `unknown` |
| `arrival_municipality` | `total`, `from_other_municipality`, `within_1_year`, `within_2_years`, `within_3_years`, `within_5_years` (cumulative), `more_than_5_years`, `since_arrival_in_spain`, `since_birth` |
| `education_level` | `total`; `primary_or_less` (`no_schooling`, `primary`), `lower_secondary`, `upper_secondary` (`upper_secondary_general`, `upper_secondary_vocational`), `tertiary` (`vocational_higher`, `university`: `bachelor`, `bachelor_long`, `master`, `doctorate`); by section, only the four groups |
| `born` | `total`, `spain`, `abroad` |
| `birth_nationality` | `total`, `born_spain`, `born_abroad`, `spanish`, `foreign` (two breakdowns of the same total) |
| `studying` | `total`, `studying` (by level: `studying_primary_or_less` … `studying_tertiary`, `studying_unknown`), `not_studying` |
| `residence_year_ago` | `total`, `same_municipality`, `moved_in` (= `elsewhere_in_spain` + `abroad`), `same_province`, `same_community`, `other_community`, `not_born` |
| `marital_status` | `total`, `single`, `married`, `widowed`, `divorced_separated` (INE gives them together), `not_stated` |
| `value` | Persons |
| `origin` | `published` (the base level, as INE publishes it), `aggregated` (summed from the level below) or `imputed` |

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
- `population_arrival_spain`: like `population_birthplace`, with the imputed units filling exactly
  what each province and municipality publishes.
- `population_education`, `population_education_born`: the total from its parts, and every level
  above against the same tables, with imputed units filling exactly what's published.
- `population_education_detail`: its groups by sex against `population_education` summed up to
  municipalities (248,385 values, the ones without imputed sections): exact.
- The mobility and education datasets by municipality: every breakdown (categories, sexes, age groups, nationalities) adds up to
  the totals INE publishes.
- `population_birthplace`: the total from its parts against INE's, and the levels above against
  the same tables' rows. Gipuzkoa's table (69172) comes in English format ("Period", 733,149):
  `common/ine.py` reads it as the others.
- `population_marital_status`: every breakdown (statuses, sexes) adds up to its total, and the
  municipalities summed up match 76288 exactly for every province, community and Spain;
  `population_marital_status_age`, as the other datasets by municipality.
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
| `population_birthplace` | section 3,826,368 · district 1,099,014 · municipality 853,797 · province 5,460 · autonomous community 1,995 · Spain 105 |
| `population_arrival_spain` | section 3,826,368 · district 1,099,014 · municipality 853,797 · province 5,460 · autonomous community 1,995 · Spain 105 |
| `population_previous_residence` | municipality 1,491,840 |
| `population_arrival_municipality` | municipality 163,080 |
| `population_residence_year_ago` | municipality 244,620 |
| `population_education` | section 2,184,810 · district 628,155 · municipality 487,875 · province 3,120 · autonomous community 1,140 · Spain 60 |
| `population_education_detail` | municipality 3,729,600 |
| `population_studying` | municipality 2,237,760 |
| `population_education_age` | municipality 2,983,680 |
| `population_marital_status` | municipality 585,450 · province 3,744 · autonomous community 1,368 · Spain 72 |
| `population_marital_status_age` | municipality 1,491,840 |
| `population_mean_age` | section 546,616 · district 156,998 · municipality 121,967 · province 780 · autonomous community 285 · Spain 15 |

## Code lists

`common/codelists.py`: sex, five-year age groups, Spanish/foreign nationality, and countries and
country groups (`COUNTRY_MAIN`, `COUNTRY_DETAIL`), as stable English codes for INE's Spanish labels. An unknown label stops the run.

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
