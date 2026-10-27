# Sources

What data Agora has, where it comes from, and what's planned. One row per dataset (a table of
values: `pipelines/data/processed/<pipeline>/<dataset>/{level}.parquet`).

Coverage as in `api/data/catalog.sqlite` on 2026-10-27; rebuild the catalogue and update this file
when a pipeline changes. Details (method, imputation, licence) live in each pipeline's README and
`catalog.json`.

**Status**: ✅ done (in the catalogue) · 🚧 in progress · 📋 planned · 💡 idea (to evaluate).

**Levels**: sec = census section, dist = census district, mun = municipality, prov = province,
ccaa = autonomous community, es = Spain. `sec → es` means from census sections up to Spain (the
levels above the finest are summed or computed from it). `mun ≥500` = only municipalities of 500
residents or more, as INE publishes them, with no levels above.

## Statistical data

### Population (`population`)

INE: official population figures (DPOP) and the annual Population Census (operation 463).

| Dataset | What | Variables | Levels | Periods | Source tables | Status |
|---|---|---|---|---|---|---|
| `population_official` | Official population by sex (Padrón) | `population`, `population_sex_share`, `sex_ratio` | mun → es | 1996–2025 | DPOP 29005 (checked with 2852) | ✅ |
| `population_sex_age` | Population by sex and five-year age group | `population`, `population_sex_share`, `sex_ratio`, `population_by_age`, `population_age_share`, `ageing_index`, `dependency_ratio`, `overageing_index` | sec → es | 2021–2025 | Census 463, 53 tables by province | ✅ |
| `population_mean_age` | Mean age by sex (derived) | `mean_age` | sec → es | 2021–2025 | From `population_sex_age` (checked with 68527) | ✅ |
| `population_sex_age_nationality` | By sex, age and nationality (Spanish/foreign) | `population_foreign`, `population_foreign_share` | mun → es | 2021–2025 | Census 463: 68535 | ✅ |
| `population_nationality` | By sex and nationality (main countries) | `population_nationality`, `population_nationality_share`, `population_foreign`, `population_foreign_share` | sec → es | 2021–2025 | Census 463: 65040 + by province | ✅ |
| `population_nationality_detail` | By sex and nationality (detail and large groups) | `population_nationality_detail`, `…_share` | mun → es | 2021–2025 | Census 463: 66323, 68537 | ✅ |
| `population_birth_country` | By sex and country of birth (main countries) | `population_birth_country`, `…_share` | sec → es | 2021–2025 | Census 463: 65038 + by province | ✅ |
| `population_birth_country_detail` | By sex and country of birth (detail and large groups) | `population_birth_country_detail`, `…_share` | mun → es | 2021–2025 | Census 463: 66322, 68538 | ✅ |
| `population_birthplace` | By sex and birthplace vs. residence | `population_birthplace`, `…_share` | sec → es | 2021–2025 | Census 463: 65041 + by province | ✅ |
| `population_arrival_spain` | By year of arrival in Spain and sex | `population_arrival_spain`, `…_share` | sec → es | 2021–2025 | Census 463: 70510… by province | ✅ |
| `population_arrival_municipality` | By year of arrival in the municipality, sex and age | `population_arrival_municipality`, `…_share` | mun (151 capitals and main cities) | 2021–2025 | Census 463: 70371 | ✅ |
| `population_previous_residence` | By previous residence, sex and age | `population_previous_residence`, `…_share` | mun ≥500 | 2021–2025 | Census 463: 70382 | ✅ |
| `population_residence_year_ago` | By residence a year ago, sex, age and nationality | `population_residence_year_ago`, `…_share` | mun (151 capitals and main cities) | 2021–2025 | Census 463: 79570 | ✅ |
| `population_education` | 15+ by sex and education level (grouped) | `population_education`, `…_share` | sec → es | 2021–2024 | Census 463: 66637… by province | ✅ |
| `population_education_born` | 15+ by country of birth (Spain/abroad) and education level | `population_education_born`, `…_share` | sec → es | 2021–2024 | Census 463: 66638… by province | ✅ |
| `population_education_gender_gap` | Gender gap in education level (derived, points) | `education_gender_gap` | sec → es | 2021–2024 | From `population_education` | ✅ |
| `population_education_age` | 15+ by sex, age and education level | `population_education_age`, `…_share` | mun ≥500 | 2021–2024 | Census 463: 66620 | ✅ |
| `population_education_detail` | 15+ by sex, birthplace or nationality and education level (detail) | `population_education_detail`, `…_share` | mun ≥500 | 2021–2024 | Census 463: 66621, 66622 | ✅ |
| `population_studying` | 15+ by sex, birthplace or nationality and studies in progress | `population_studying`, `…_share` | mun ≥500 | 2021–2024 | Census 463: 66627, 66628 | ✅ |
| `population_marital_status` | 16+ by sex and marital status | `population_marital_status`, `…_share` | mun → es | 2021–2024 | Census 463: 76306, 76312 (checked with 76288) | ✅ |
| `population_marital_status_age` | 16+ by sex, age and marital status | `population_marital_status_age`, `…_share` | mun ≥500 | 2021–2024 | Census 463: 76306 | ✅ |

### Employment (`employment`)

SEPE open data (monthly registers) and INE's annual Population Census (activity and employed).

| Dataset | What | Variables | Levels | Periods | Source tables | Status |
|---|---|---|---|---|---|---|
| `registered_unemployment` | Registered unemployment by sex, age band and sector (hidden values imputed) | `registered_unemployment`, `registered_unemployment_rate`, `registered_unemployment_by_sector`, `registered_unemployment_sector_share` | mun → es | 2006-01 – 2026-09, monthly | SEPE `Paro_por_municipios_{year}_csv.csv` | ✅ |
| `job_seekers` | Job seekers by sex, age band and sector | `job_seekers`, `job_seekers_by_sector` | mun → es | 2006-01 – 2026-09, monthly | SEPE `Dtes_empleo_por_municipios_{year}_csv.csv` | ✅ |
| `contracts` | Contracts by sex, contract type and sector | `contracts`, `contracts_share`, `contracts_by_sector`, `contracts_sector_share`, `contracts_permanent_share` | mun → es | 2006-01 – 2026-09, monthly | SEPE `Contratos_por_municipios_{year}_csv.csv` | ✅ |
| `census_activity` | 16+ by sex and relation with activity | (through `census_activity_groups`) | sec → es | 2021–2024 | Census 463: 66594 | ✅ |
| `census_activity_born` | 16+ by country of birth and relation with activity | (through `census_activity_groups`) | sec → es | 2021–2024 | Census 463: 66640… by province | ✅ |
| `census_activity_groups` | Activity by sex or country of birth (derived) | `activity_rate`, `employment_rate`, `unemployment_rate`, `activity_status`, `activity_status_share` | sec → es | 2021–2024 | From the two above | ✅ |
| `census_activity_gaps` | Gaps in activity, employment and unemployment rates (derived, points) | `labour_gap` | sec → es | 2021–2024 | From `census_activity_groups` | ✅ |
| `employed_occupation` | Employed by sex and occupation (grouped) | `employed_by_occupation`, `…_share` | sec → es | 2021–2023 | Census 463: 70016… by province | ✅ |
| `employed_sector` | Employed by sex and branch of activity | `employed_by_sector`, `…_share` | sec → es | 2021–2023 | Census 463: 70017… by province | ✅ |
| `employed_status` | Employed by sex and professional status (grouped) | `employed_by_status`, `…_share` | sec → es | 2021–2023 | Census 463: 70018… by province | ✅ |
| `employed_status_detail` | Employed by sex and professional status (detail) | `employed_by_status_detail`, `…_share` | mun ≥500 | 2021–2023 | Census 463: 69993 | ✅ |
| `employed_cno11` | Employed by sex and occupation (CNO-11, 1 digit) | `employed_by_cno11`, `…_share` | mun ≥500 | 2021–2023 | Census 463: 69991 | ✅ |
| `employed_cnae2009` | Employed by sex and activity (CNAE-2009, section) | `employed_by_cnae2009`, `…_share` | mun ≥500 | 2021–2023 | Census 463: 69992 | ✅ |

### Income (`income`, `income_distribution`)

INE: Household Income Distribution Atlas (ADRH, operation 353).

| Dataset | What | Variables | Levels | Periods | Source tables | Status |
|---|---|---|---|---|---|---|
| `income_levels` | Mean and median income (per person, household, consumption unit) | `income` | sec → es | 2015–2024 (es 2021–2024) | ADRH 353 | ✅ |
| `income_sources` | Income by source (wages, pensions, benefits…) | `income_sources` | sec → es | 2015–2024 | ADRH 353 | ✅ |
| `income_inequality` | Gini index and P80/P20 | `income_gini`, `income_p80_p20` | sec → es | 2015–2024 | ADRH 353 | ✅ |
| `income_relative` | Population below or above relative thresholds, by sex, age or nationality | `income_thresholds` | sec → es | 2015–2024 | ADRH 353 | ✅ |
| `income_fixed` | Population below fixed thresholds, by sex, age or nationality | `income_fixed_thresholds` | sec → es | 2015–2024 | ADRH 353 | ✅ |
| `income_demographics` | Household size, single-person households | `household_size`, `single_person_households` | sec → es | 2015–2024 | ADRH 353 | ✅ |
| `income_distribution` | Income distribution fitted to a Dagum (derived) | (distribution parameters, no layer) | sec → es | 2015–2024 | From the ADRH tables above | ✅ |

### Census 2021 (`census_2021`)

INE: Censos de Población y Viviendas 2021, a single edition. Custom tables
(`ine.es/Censo2021`) show sections of about 500 units or more; the rest are imputed from their
district, fitted to official totals.

| Dataset | What | Variables | Levels | Periods | Source tables | Status |
|---|---|---|---|---|---|---|
| `dwellings_2021` | Dwellings by type, main dwellings by tenure | `dwellings_2021`, `…_share`, `dwellings_tenure_2021`, `…_share` | sec → es | 2021 | `C2021_Indicadores.csv` (T18–T20), 59525, 59523 | ✅ |
| `dwellings_by_year_2021` | Dwellings by building's year of construction | `dwellings_by_year_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `dwellings_by_building_2021` | Dwellings by building type | `dwellings_by_building_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `dwellings_by_floor_area_2021` | Dwellings by floor area | `dwellings_by_floor_area_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `dwellings_by_floors_2021` | Dwellings by building floors above ground | `dwellings_by_floors_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `dwellings_mean_age_2021` | Mean age of dwellings | `dwellings_mean_age_2021` | sec → es | 2021 | Custom tables | ✅ |
| `housing_means_2021` | Mean floor area, area per occupant, mean household size | `floor_area_2021`, `household_size_2021` | sec → es | 2021 | INE census map service (`SAS_seleccion_2021`) | ✅ |
| `dwelling_use_2021` | Dwellings by use intensity (from electricity use) | `dwelling_use_2021`, `…_share` | mun → es (3,139 mun) | 2021 | 59531 | ✅ |
| `electricity_consumption_2021` | Annual household electricity use: percentiles and median | `electricity_consumption_2021` | dist → es (5,077 dist) | 2021 | 59532, 59531 | ✅ |
| `households_2021` | Households by size | `households_2021`, `…_share` | sec → es | 2021 | `C2021_Indicadores.csv` (T21–T22), 59543 | ✅ |
| `households_by_structure_2021` | Households by structure | `households_by_structure_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `households_by_type_2021` | Households by type | `households_by_type_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `households_by_nuclei_2021` | Households by number of family nuclei | `households_by_nuclei_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `households_by_families_2021` | Households by number of families | `households_by_families_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `households_by_members_2021` | Households by members aged 0–4, 5–15, 65–84, 85+, working, unemployed | `households_by_members_2021`, `…_share` | sec → es | 2021 | Custom tables (6) | ✅ |
| `nuclei_by_type_2021` | Family nuclei by type | `nuclei_by_type_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `nuclei_by_couple_kind_2021` | Couples by kind of union | `couples_by_kind_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `nuclei_by_couple_sexes_2021` | Couples by sex of their members | `couples_by_sexes_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `nuclei_by_children_2021` | Family nuclei by number of children | `nuclei_by_children_2021`, `…_share` | sec → es | 2021 | Custom tables | ✅ |
| `nuclei_mean_children_2021` | Mean children per nucleus | `nuclei_mean_children_2021` | sec → es | 2021 | Custom tables | ✅ |

### Housing (`housing`)

INE: experimental statistic "Medición del número de viviendas turísticas en España y su capacidad"
(web scraping of three of the main short-let platforms).

| Dataset | What | Variables | Levels | Periods | Source tables | Status |
|---|---|---|---|---|---|---|
| `tourist_dwellings` | Tourist dwellings, beds, and share of all dwellings in the census (hidden where few) | `tourist_dwellings`, `tourist_dwellings_share`, `tourist_beds`, `tourist_beds_per_dwelling` | sec → es (every level as published) | 2020-08 – 2026-05, twice a year | Excel by district and section (one per period), 39363, 39366, 39364, 39365 | ✅ |

### Businesses (`businesses`)

INE: Directorio Central de Empresas (DIRCE).

| Dataset | What | Variables | Levels | Periods | Source tables | Status |
|---|---|---|---|---|---|---|
| `companies` | Active companies by main activity (11 groups; breakdown only for ~3,100 / ~1,300 municipalities); hidden municipalities imputed | `companies`, `companies_share`, `companies_per_1000` | mun → es | 2012–2025 | DIRCE 4721 | ✅ |

## Geography and reference data

Not values: units, boundaries (vector tiles via `tiles`) and classifications.

| Pipeline | What | Units | Edition | Source | Status |
|---|---|---|---|---|---|
| `autonomous_communities` | Boundaries | 17 + Ceuta and Melilla | Current snapshot | IGN, WFS INSPIRE unidades administrativas | ✅ |
| `provinces` | Boundaries | 52 | Current snapshot | IGN, WFS INSPIRE | ✅ |
| `municipalities` | Boundaries | 8,132 + 81 shared territories | Current snapshot | IGN, WFS INSPIRE | ✅ |
| `census_sections` | Census sections and districts | 36,669 sections, 10,452 districts | 2026 | INE, cartografía de secciones censales | ✅ |
| `postal_codes` | Postal code areas (no data yet) | 10,874 | 2024-01 | GeoParquet from an earlier project (by hand) | ✅ |
| `cadastre` | Urban parcels, rural polygons, cadastral zones (no data yet) | 13.2 M parcels, 183,133 polygons, 1.3 M zones | 2023 | Catastro INSPIRE + foral cadastres of Navarra and the Basque Country | ✅ |
| `classifications` | CNAE-2025, CNAE-2009, CNO-11, CNED-2014 A and F, CPA 2.2, and correspondences | — | As published | INE | ✅ |
| `tiles` | Vector tiles (PMTiles) of the boundaries above | — | — | The pipelines above | ✅ |

## Planned and ideas

New sources go here first. When one is done, move it to its section above.

| Source | What it would add | Levels | Periods | Publisher | Notes | Status |
|---|---|---|---|---|---|---|
| Cadastral data per parcel | Year built, floor area, use… per urban parcel | parcel (13.2 M) | Yearly | Catastro | Needs a way to serve values by area: see [TODO.md](TODO.md#data-by-cadastral-parcel) | 💡 |
| Censo 2021 en cuadrículas de 1 km² | Population on Eurostat's 1 km grid | 1 km cell (new level) | 2021 (2011 also exists) | INE | Not administrative: a new geometry, independent of boundary changes | 💡 |
| Nomenclátor | Population by singular entity and nucleus (Padrón) | Below mun (new level) | Yearly | INE | INE has no polygons: points, or IGN's population nuclei | 💡 |
| IPVA (experimental) | Rent price index and levels, from tax records | mun, districts of provincial capitals | Yearly, from 2015 | INE | The Housing Ministry's rent index reaches census sections (another publisher) | 💡 |
| Movimiento Natural de la Población | Births, deaths, marriages; natural balance | mun (threshold to check) → es | Yearly | INE | Check which municipalities INE publishes | 💡 |
| Estadística de Variaciones Residenciales | Arrivals and departures (domestic and abroad) | mun (threshold to check) → es | Yearly | INE | Migration flows, complements the census's previous residence | 💡 |
| Padrón by census section before 2021 | Population by sex and age per section, extending series back | sec | Years to check | INE | Sections were drawn differently: needs matching to today's | 💡 |
| Censo Agrario 2020 | Farms, utilised agricultural area, livestock | mun → es | 2020 (and 2009) | INE | | 💡 |
| Movilidad con teléfonos móviles (experimental) | Daily trips between mobility areas | Mobility areas (groups of sections) | Selected periods | INE | Origin–destination: a different kind of layer (flows) | 💡 |
