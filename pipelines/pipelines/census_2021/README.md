# Census 2021

INE's Censos de Población y Viviendas 2021: a one-off picture of dwellings and households on
1 January 2021, down to census sections (as drawn in 2021). The yearly census (population
pipeline) has no dwellings or households: this is the only source for them by section.

```sh
python pipelines/census_2021/census_2021.py          # seconds; ~23 MB of downloads
python pipelines/census_2021/custom_tables.py        # ~8 hours: 1,080 tables from INE's tool, one at a time
python pipelines/census_2021/census_2021_detail.py   # ~5 min, after the two above
```

Needs the provinces pipeline (provinces → autonomous communities).

## Datasets

| Dataset | Values | Breakdown | Levels |
|---|---|---|---|
| `dwellings_2021` | Conventional family dwellings | `dwelling`: `total`, `principal` (`owned`, `rented`, `other_tenure`), `non_principal` | section → … → Spain |
| `households_2021` | Households | `household_size`: `total`, `1`, `2`, `3`, `4`, `5_plus` | section → … → Spain |
| `housing_means_2021` | Mean usable floor area of the dwellings (m²), floor area per occupant (m²), mean household size (people) | `housing_indicator`: `mean_floor_area`, `floor_area_per_occupant`, `mean_household_size` | section → … → Spain |
| `dwelling_use_2021` | Dwellings by their electricity use in 2020 | `dwelling_use`: `total`, `empty`, `very_low`, `sporadic` (251–500, 501–750 kWh), `regular` (kWh bands from 751 to over 10,000) | municipality (1,000 residents or more), province, community, Spain |
| `electricity_consumption_2021` | Annual electricity consumption per dwelling (kWh) | `consumption_statistic`: `p10`, `p25`, `median`, `p75`, `p90` | district (percentiles); municipality (1,000 residents or more), province, community, Spain (median) |

Output: `data/processed/census_2021/{dataset}/{level}.parquet` with `entity_id`, `code`, `period`
(2021), the breakdown, `value` and `origin`; `meta.json` with the sources and checks.

## Sources

- [Section indicators](https://www.ine.es/censos2021/C2021_Indicadores.csv) (`C2021_Indicadores.csv`):
  T18–T20 (dwellings by type, principal dwellings by tenure), T21–T22 (households by size). The rest
  (population, age, nationality, education, activity, marital status) is in the yearly census.
- INE's [census map viewer](https://www.ine.es/censos2021/visor/), an ArcGIS feature service with
  one layer per level (`SAS_seleccion_2021/FeatureServer/1`–`6`: Spain to sections), queried for
  its attributes: the means (floor area, per occupant, household size) at every level. Its counts
  of dwellings and households fill the sections the indicators file leaves blank, and match what
  is imputed here from the municipal tables (99.5% of them exactly).
- Tables for every municipality: 59525 (dwellings by type), 59543 (households by size).
- 59523: principal dwellings by tenure, by province and municipality size (communities and their
  provinces share one column; a label is a province when its code belongs to the community above).
- 59531 (dwellings by electricity use, municipalities of 1,000 residents or more, provinces,
  communities, Spain; the smaller municipalities together as "Resto de …", left out) and 59532
  (consumption percentiles by district). Some districts' names end in "*", which INE doesn't
  explain: ignored.

## Levels and imputation

Every level as INE publishes it where it does, summed where it doesn't:

- **Sections** as published. 1,363 are blank, nearly all municipalities under 100 residents with a
  single section: their municipality's figures (59525, 59543) less its published sections' are
  shared out among them by population (`common/imputation.py`), and their principal dwellings split
  by tenure like their province's unpublished rest of municipalities of the same size (59523 less
  the published sections), largest remainders. `origin = "imputed"`.
- **Districts** summed from sections.
- **Municipalities** as in 59525 and 59543; tenure summed from sections (no municipal table).
- **Provinces, communities, Spain** summed from municipalities.

The means (`housing_means_2021`) are INE's at every level: a mean floor area can't be rebuilt from
the sections' (it isn't weighted by dwellings or households). A 0 is a hidden mean (four sections,
one district, one municipality): it takes the unit above's. Floor area per occupant and household
size don't apply to units without households (two sections). Eight sections have a mean floor area
under 30 m² (down to 0.95 m², 3501601061), as INE publishes them.

INE calls the section figures provisional (some dwellings' sections were being updated). Checks:

- Households: the sections add up exactly to every municipality's 59543 figures.
- Dwellings: the sections differ from 59525 in 29 municipalities, by up to 658 dwellings (04902, El
  Ejido); the run stops past 60 municipalities or 1,000 dwellings.
- Provinces' tenure against 59523: within 12 dwellings (0.3%); 78 published sections whose tenure
  doesn't add up to their principal dwellings (by 1 to 261) are kept as INE has them.
- Electricity: the uses add up to the dwellings for every unit (empty + very low + sporadic +
  regular = total); 59531's dwellings match 59525 for every municipality.
- Spain: the municipalities add up to 59525's and 59543's national rows exactly.

371 of the 36,333 sections of 2021 (1%) no longer exist as such, and 29 districts: the map, drawn
with today's sections, leaves them out.

## Definitions

- **Principal dwelling**: someone's usual residence; **non-principal**: second homes, empty and
  others. Conventional family dwellings only (not group quarters).
- **Floor area**: usable floor area, which INE estimates from Catastro's built area with a model
  fitted to a sample with both (methodology, chapter 8.1); per occupant, of principal dwellings.
- **Electricity use** (INE methodology, chapter 8.2): **empty**, no supply contract or a consumption
  under the municipality's mean divided by 24 (half a month's use in a year); **very low**, up to
  250 kWh; **sporadic**, 251 to 750 kWh (one to three months' use); **regular**, the rest, in
  bands up to over 10,000 kWh.

## Detail by section: INE's custom tables

`custom_tables.py` downloads, and `census_2021_detail.py` turns into datasets, what INE only offers
through its custom tables tool ([Crear tablas](https://www.ine.es/Censo2021/Inicio.do)): 20 tables
with sections as rows, as PC-Axis files in `data/raw/census_2021/{date}/custom/{table}/{group}.px`.

| Dataset | Values | Breakdown |
|---|---|---|
| `dwellings_by_year_2021` | Dwellings | `construction_period`: before 1900 … 2011–2020 (11), grouped (before 1951, 1951–1980, 1981–2000, 2001–2020), not stated |
| `dwellings_mean_age_2021` | Mean age of the dwellings (years) | `dwelling`: `total`, `principal`, `non_principal` |
| `dwellings_by_building_2021` | Dwellings | `building_type`: one, two, three or more dwellings, non-residential, not stated |
| `dwellings_by_floor_area_2021` | Dwellings | `floor_area_band`: up to 30 m² … over 180 m² (10), grouped (up to 60, 61–90, 91–120, over 120) |
| `dwellings_by_floors_2021` | Dwellings | `building_floors`: 1 … 9, 10 or more, grouped (1–2, 3–5, 6–9), not stated |
| `households_by_structure_2021` | Households | `household_structure`: alone (woman or man, under 65 or 65 and over), lone parent (with a child under 25, or all 25 and over), couple without or with children (likewise), parents with children and others, other |
| `households_by_type_2021` | Households | `household_type`: one person, no family, one family (5 kinds), two or more families |
| `households_by_nuclei_2021`, `households_by_families_2021` | Households | number of family nuclei (0, 1, 2, 3 or more), of families (0, 1, 2 or more) |
| `households_by_members_2021` | Households | `member_group` (aged 0–4, 5–15, 65–84, 85 or more; aged 16–64 working, unemployed) × `members` (0, 1, 2, 3 or more; any) |
| `nuclei_by_type_2021` | Family nuclei | `nucleus_type`: couple without or with children, parent 1 or 2 with children (INE's names) |
| `nuclei_by_couple_kind_2021` | Family nuclei | `couple_kind`: married, cohabiting (both single, other), not a couple |
| `nuclei_by_couple_sexes_2021` | Family nuclei | `couple_sexes`: different sex, same sex (two women, two men), not a couple |
| `nuclei_by_children_2021` | Family nuclei | `children`: number of children |
| `nuclei_mean_children_2021` | Mean children per nucleus | `nucleus_type` |

How the tool is asked (`custom_tables.py`): a table per group of municipalities of up to 2,500
sections (a whole province is too big for Madrid's or Barcelona's: 54 requests per table), each in
a fresh session, one at a time. **INE's server mixes up concurrent requests**: run in parallel, a
table came with another's rows or values (10 of the first 721). Every table is checked: the
municipalities asked for, the variable asked for, as many values as rows × columns, and counts that
add up to each section's official total (nuclei: 0.4–1.2 per household in at least 90% of sections; means: in range).
A failing table is asked again; tables already there are skipped, so running it again (with
`--date` set to the folder's day) completes a download. A download from 2023 (47,606 tables, run in parallel) had 1,114
such tables (whole provinces with another's data) and isn't used.

How it's turned into sections (`census_2021_detail.py`). The tool only shows sections of about 500
units or more (dwellings, households or nuclei, whatever the table counts: the smallest shown has
~500), and so whole small municipalities (Madrid: 1,646 of its 2,443 sections shown; Soria: 26 of
183 municipalities). Its districts, municipalities and group totals **add up their shown sections
only** (the difference is ±30 at most, in every table): there is no remainder for the hidden ones.
It also perturbs its cells slightly (statistical disclosure control: ±1–3 against the indicators
file). So:

- **Counts**: a shown section keeps its split by category; a hidden one takes its district's (else
  its municipality's, else the group's), which is the split of the shown sections around it. Each
  section's split is then fitted to its total in integers (largest remainders), which takes the
  noise out: the official dwellings or households (`dwellings_2021`, `households_2021`); nuclei,
  the tool's own, and for a hidden section its households' nuclei from `households_by_nuclei_2021`
  (one, two, three for "3 or more"; in shown sections this matches the tool's total within 0.5%).
  Districts and up are summed from sections, so every table adds up to Spain's 18,539,223
  households (13.2 million nuclei). Hidden sections, `imputed`, are about 29% of sections for
  dwellings (4% by floor area), 51% for households and 79% for nuclei; as they take the split of
  bigger sections nearby, they lean towards it (in rural areas, fewer single-family dwellings and
  old buildings than they surely have).
- **Means**: as the tool gives them for shown sections; a hidden one takes its district's, else
  its municipality's, else its group's (of shown sections); a 0 (nothing to average: no
  non-principal dwellings) is left out. Every level up is weighted by what it's the mean of.

## Not here yet

By municipality INE also publishes, only for provincial capitals and municipalities of over 50,000
residents: dwellings by year of construction and floor area, tenure, households by type and
structure (tables 59526–59530, 59544, 59545; downloaded, not used: the custom tables cover them by
section). The tool has more (people by any census variable, dwellings by detailed year…): add a line
to `TABLES` in `custom_tables.py` and a dataset in `census_2021_detail.py`. The microdata (10%
sample) identify municipalities of over 10,000 residents only.

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
