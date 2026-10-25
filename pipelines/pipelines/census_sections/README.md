# Census sections and districts

The census sections of Spain (36,669 in 2026) from INE's yearly cartography, and the census
districts (10,452) built from them, as GeoParquet keyed by INE code.

```sh
python pipelines/census_sections/census_sections.py               # latest edition (2026)
python pipelines/census_sections/align_to_municipalities.py       # redraw them to IGN's municipal boundaries
python pipelines/census_sections/census_sections.py --year 2025   # another edition
python pipelines/census_sections/census_sections.py --refresh     # download again
```

## Source

| | |
|---|---|
| Publisher | Instituto Nacional de Estadística (INE) |
| Product | *Cartografía digitalizada de secciones censales*, one edition a year |
| File | `https://www.ine.es/prodyser/cartografia/seccionado_{year}.zip` (2026: 65 MB, published March 2026) |
| Content | One shapefile for the whole country, `SECC_CE_{year}0101.shp`, ETRS89 / UTM 30N (EPSG:25830), Canarias included |
| License | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), per [INE's legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125) (only for content whose original source is INE) |
| Attribution | **Elaboración propia con datos extraídos del sitio web del INE: www.ine.es** (INE's suggested wording for processed data; the date of the edition should be cited too) |

INE's legal notice states CC BY 4.0, while its site footer mentions CC BY-SA 4.0; the legal notice
is the specific statement on reuse, so the catalogue records CC BY 4.0.

## Validity

Each edition is the sectioning **in force on 1 January** of its year. INE redraws sections and
districts every year (they follow population), and **a code can be reused with different
boundaries** in another edition. So:

- Outputs carry the year in their file name and a `year` column.
- Statistics by section must be matched with the edition of their own year.
- Only the latest edition (2026) is built for now; `--year` builds any other.

## Districts

INE doesn't publish district boundaries. Each district is the union of its sections, grouped by
INE's district code (municipality + district).

## Identifiers

- Section: `es:ine:sec:{CUSEC}`, ten digits: province (2) + municipality (3) + district (2) +
  section (3). E.g. `es:ine:sec:2807901001`.
- District: `es:ine:dist:{code}`, seven digits: municipality (5) + district (2). E.g. `es:ine:dist:2807901`.

The pipeline fails if any code isn't built from the ones above it, or on duplicated section codes.

## Checks (2026 edition)

- 36,669 sections, 10,452 districts, 8,132 municipalities: exactly the same municipality codes as
  IGN's current municipalities (`municipalities` pipeline).
- 14 invalid geometries in the source, repaired with `make_valid`.
- Every section's district exists, and every district's municipality is one of IGN's.

## Differences with IGN's boundaries

INE's cartography isn't IGN's, so at high zoom section lines won't fall exactly on IGN's municipal
boundaries. Comparing each municipality's area as the union of its INE sections with IGN's
polygon: median difference 0.13 %, 95th percentile 5 %. In about 40 municipalities (mostly Navarra
and Burgos) it's over 20 %, because INE assigns IGN's shared territories (facerías, comunidades…)
to municipalities, and in a few very small ones (Llocnou de la Corona) because any shift is large
next to their size.

Municipality names also differ in form in 621 cases: INE puts articles at the end (`Roda, La`),
IGN doesn't (`La Roda`). Join by code.

## Aligned to IGN's municipal boundaries

INE's lines don't meet IGN's, so on the map sections and municipalities wouldn't match.
`align_to_municipalities.py` (needs the municipalities pipeline) redraws them, municipality by
municipality:

1. Each section is clipped to IGN's polygon of its municipality.
2. Whatever of the municipality no section covers goes to the section it shares the longest border
   with (the nearest one if it touches none).
3. Districts are the union of their redrawn sections.

2026 edition: 1,935 km² cut off (mostly IGN's shared territories, which INE assigns to
municipalities), 222,419 gaps filled (2,271 km², mostly slivers between both cartographies), and
every municipality equals the union of its sections to within 0.0001 % of its area.

Two sections of Mislata (`4616901001`, `4616901002`, 0.07 km²) lie entirely inside València by
IGN's boundary, so they can't be clipped to Mislata: they keep INE's geometry, flagged
`aligned = false`.

The tile layers and the map use the aligned files; INE's own geometry stays in the original ones.

## Output

In `data/processed/census_sections/`:

- `census_sections_{year}.parquet`: GeoParquet 1.1 (zstd, bbox covering column), EPSG:4326, sorted
  by `id`. Columns: `id`, `ine_code`, `section_code`, `district_code`, `municipality_code`,
  `province_code`, `ccaa_code`, `municipality_name`, `parent_id`, `year`, `geometry`.
- `census_districts_{year}.parquet`: same format. Columns: `id`, `ine_code`, `district_code`,
  `municipality_code`, `province_code`, `ccaa_code`, `municipality_name`, `parent_id`, `year`, `geometry`.
- A `.meta.json` next to each, with the run details.
- `census_sections_{year}_aligned.parquet` and `census_districts_{year}_aligned.parquet`: the same,
  redrawn to IGN's municipal boundaries; sections also have `aligned` (false where they couldn't
  be). `census_{year}_aligned.meta.json` records what was cut and filled.

The raw download is kept in `data/raw/census_sections/{retrieval date}/seccionado_{year}.zip`.

## Catalogue

[`catalog.json`](catalog.json) describes the `census_section` and `census_district` entity types,
their `part_of` relations (section → district → municipality), and both datasets.
