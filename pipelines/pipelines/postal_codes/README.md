# Postal codes

Postal code areas of Spain (10,874), as GeoParquet keyed by postal code.

```sh
python pipelines/postal_codes/postal_codes.py
```

## Source

| | |
|---|---|
| Origin | GeoParquet from an earlier project, dated 8 January 2024 |
| Provenance | **To be documented**: original source, method and license |
| Location | `data/raw/postal_codes/2024-01-08/postal-codes.geo.parquet` (and `postal-codes.parquet`, the same rows without geometry) |
| CRS | WGS 84 (EPSG:4326) |

**This source isn't downloaded**: the files were put in `data/raw/` by hand and are the only copy.
`data/` is outside git, so keep a backup of that folder; if it's lost, this pipeline can't run.

There are no official open postal code boundaries in Spain: Correos doesn't publish them, and
CartoCiudad (IGN/CNIG, built with Grupo Correos) only shows them as a map image (WMS), with no
download. Postal codes have no official boundary either way (they're sets of addresses), so any
polygons are an approximation.

Until the provenance is documented, the map credits them as "Códigos postales: elaboración propia".

## Validity

A snapshot as of January 2024. Correos creates and changes postal codes now and then; codes added
since then aren't here.

## Checks

On the 2024-01-08 snapshot:

- 10,874 postal codes, unique, five digits each, in all 52 provinces; every code starts with its
  province's INE code (and matches the source's `province_id`).
- No overlaps between areas, and together they cover 99.95 % of IGN's area of Spain (361 km² of
  IGN's Spain uncovered, 108 km² outside it, mostly coastline differences).
- 302 areas reach slightly beyond their province's IGN boundary; 9 lie mostly outside it.
  Differences of cartography; kept as they are.
- 5 invalid geometries, repaired with `make_valid`.

## What's kept

| Source column | Kept as | Why |
|---|---|---|
| `postal_code` | `postal_code` | The key |
| `province_id` | `province_code` (two digits) | Same as the code's prefix |
| `name` | — | Just "CP 01001": nothing more than the code |
| `postal_id` | — | The code as a number |
| `area` | — | Derivable from the geometry (km²) |
| `lng`, `lat` | — | A centroid, which falls outside its own area in 4.5 % of codes |

## Identifiers

`es:correos:cp:{postal_code}`, e.g. `es:correos:cp:28001`: Correos assigns the codes. Parent:
the province, `es:ine:prov:{first two digits}`.

## Output

In `data/processed/postal_codes/`:

- `postal_codes.parquet`: GeoParquet 1.1 (zstd, bbox covering column), EPSG:4326, sorted by `id`.
  Columns: `id`, `postal_code`, `province_code`, `parent_id`, `geometry`.
- `postal_codes.meta.json`: run details (source file, its size and SHA-256, row count).

## Catalogue

[`catalog.json`](catalog.json) describes the `postal_code` entity type, its `part_of` relation to
provinces and the dataset. Its license and provenance are pending, like here.
