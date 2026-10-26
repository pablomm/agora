# Census 2021

INE's Censos de Población y Viviendas 2021: a one-off picture of dwellings and households on
1 January 2021, down to census sections (as drawn in 2021). The yearly census (population
pipeline) has no dwellings or households: this is the only source for them by section.

```sh
python pipelines/census_2021/census_2021.py   # seconds; ~23 MB of downloads
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

## Not here yet

By municipality INE also publishes, only for provincial capitals and municipalities of over 50,000
residents: dwellings by year of construction and floor area, tenure, households by type and
structure (tables 59526–59530, 59544, 59545; downloaded, not used).

By section, the rest is only in INE's custom tables tool ([Crear tablas](https://www.ine.es/Censo2021/Inicio.do)).
For family dwellings it offers, with sections as rows: floor area and floor area per occupant
(bands), tenure, dwelling type by building (one, two, three or more dwellings, non-residential),
floors above and below ground, year of construction (grouped and in detail), household size; and as
measures, the count, the dwellings' **mean age**, mean floor area and the share of non-principal
ones. Households, couples and family nuclei have their own variables (household type and
structure, nuclei by type). Two ways in, neither in files:

- "Todas las secciones" (all of Spain at once): too big to show; INE offers to process it and email
  the result, which asks for a name, organisation, email and phone.
- One municipality at a time, choosing its districts and sections: some 8,000 requests per table.

The microdata (10% sample) identify municipalities of over 10,000 residents only.

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
