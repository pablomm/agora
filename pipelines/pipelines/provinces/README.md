# Provinces

The 52 provinces of Spain (50 provinces plus the autonomous cities of Ceuta and Melilla), with
their boundaries, as GeoParquet keyed by INE code.

```sh
python pipelines/provinces/provinces.py            # reuses today's download if there is one
python pipelines/provinces/provinces.py --refresh  # downloads again
```

## Source

| | |
|---|---|
| Publisher | Instituto Geográfico Nacional (IGN) |
| Service | WFS INSPIRE *Unidades administrativas de España*: `https://www.ign.es/wfs-inspire/unidades-administrativas` |
| Feature type | `au:AdministrativeUnit`, filtered on `nationalLevel` = `3rdOrder` (provinces) |
| Format requested | GeoJSON in EPSG:4326 |
| Metadata | [IDEE catalogue record `spaignLLM`](https://www.idee.es/csw-inspire-idee/srv/spa/csw?SERVICE=CSW&VERSION=2.0.2&REQUEST=GetRecordById&outputSchema=http://www.isotc211.org/2005/gmd&ElementSetName=full&ID=spaignLLM) |
| License | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as stated in the service's capabilities |
| Attribution | **CC BY 4.0 ign.es** (required wherever the data or derived maps are shown) |

The request and parsing are shared with the [autonomous communities](../autonomous_communities/README.md), in `common/ign.py`.

## Validity

The service publishes the **current** state of IGN's administrative boundaries; features carry
no validity dates (`beginLifespanVersion` is empty). The data is therefore valid **as of the
retrieval date**, which every run records in `provinces.meta.json` and in the raw folder's name.

The set of provinces hasn't changed since 1927; the boundaries themselves can move slightly when
municipal boundaries are redrawn, so refresh before building a new tile set.

## What's included

- The 50 provinces and Ceuta (51) and Melilla (52), which INE codes as provinces.
- **Excluded**: IGN's third level also has *Territorios no asociados a ninguna provincia*
  (`34205400000`, the plazas de soberanía), which isn't an INE province.
- Geometry at **full resolution**, as published (about 116 MB as GeoJSON, 17 MB as GeoParquet).
  Simplification belongs to the tile builds, not here. Invalid geometries would be repaired
  with `make_valid`; the current download has none.
- Names exactly as IGN publishes them, bilingual where that's the official name
  (`Alacant/Alicante`, `Araba/Álava`, `València/Valencia`…).

## Identifiers

- Province: `es:ine:prov:{ine_code}`, e.g. `es:ine:prov:28` (Madrid).
- Parent autonomous community: `es:ine:ccaa:{ccaa_code}`, e.g. `es:ine:ccaa:13`.

IGN's `nationalCode` contains both INE codes: `34` (Spain) + autonomous community + province +
`00000`. For example, `34132800000` is Madrid (`13`, `28`). The pipeline fails if a code doesn't
follow that shape, or if the result isn't exactly provinces 01–52 once each.

## Output

In `data/processed/provinces/`:

- `provinces.parquet`: GeoParquet 1.1 (zstd, with a bbox covering column), EPSG:4326, one row
  per province, sorted by `id`. Columns: `id`, `ine_code`, `name`, `ccaa_code`, `parent_id`,
  `ign_code`, `geometry`.
- `provinces.meta.json`: run details (retrieval date, request, raw file size and SHA-256, row count).

The raw download is kept in `data/raw/provinces/{retrieval date}/provinces.geojson`.

## Catalogue

[`catalog.json`](catalog.json) describes what this pipeline adds to the catalogue: the
`province` entity type and its id scheme, the `part_of` relation to autonomous communities,
and the `ign_au_provinces` dataset (source, license, validity, coverage and fields).
