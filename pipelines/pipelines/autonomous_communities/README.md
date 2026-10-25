# Autonomous communities

The 17 autonomous communities of Spain and the autonomous cities of Ceuta and Melilla, with their
boundaries, as GeoParquet keyed by INE code.

```sh
python pipelines/autonomous_communities/autonomous_communities.py            # reuses today's download if there is one
python pipelines/autonomous_communities/autonomous_communities.py --refresh  # downloads again
```

## Source

| | |
|---|---|
| Publisher | Instituto Geográfico Nacional (IGN) |
| Service | WFS INSPIRE *Unidades administrativas de España*: `https://www.ign.es/wfs-inspire/unidades-administrativas` |
| Feature type | `au:AdministrativeUnit`, filtered on `nationalLevel` = `2ndOrder` (autonomous communities) |
| Format requested | GeoJSON in EPSG:4326 |
| Metadata | [IDEE catalogue record `spaignLLM`](https://www.idee.es/csw-inspire-idee/srv/spa/csw?SERVICE=CSW&VERSION=2.0.2&REQUEST=GetRecordById&outputSchema=http://www.isotc211.org/2005/gmd&ElementSetName=full&ID=spaignLLM) |
| License | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as stated in the service's capabilities |
| Attribution | **CC BY 4.0 ign.es** (required wherever the data or derived maps are shown) |

Same service as the [provinces](../provinces/README.md); the request and parsing live in `common/ign.py`.

## Validity

The service publishes the **current** state of IGN's administrative boundaries; features carry
no validity dates. The data is therefore valid **as of the retrieval date**, which every run
records in `autonomous_communities.meta.json` and in the raw folder's name.

## What's included

- The 17 autonomous communities (01–17) and the autonomous cities of Ceuta (18) and Melilla (19),
  with INE's codes.
- **Excluded**: IGN's second level also has *Territorios no asociados a ninguna autonomía*
  (`34200000000`, the plazas de soberanía), which isn't an INE autonomous community.
- Geometry at **full resolution**, as published (about 97 MB as GeoJSON, 15 MB as GeoParquet).
- Names exactly as IGN publishes them, bilingual where that's the official name
  (`Cataluña/Catalunya`, `País Vasco/Euskadi`).

## Consistency with provinces

Checked on the 2026-10-25 download: every province's `parent_id` is one of these 19 ids, every
autonomous community has at least one province, and each community's geometry equals the union
of its provinces (no area difference).

## Identifiers

`es:ine:ccaa:{ine_code}`, e.g. `es:ine:ccaa:13` (Comunidad de Madrid). IGN's `nationalCode` is
`34` (Spain) + the INE code + `0000000`; the pipeline fails if a code doesn't follow that shape,
or if the result isn't exactly codes 01–19 once each.

## Output

In `data/processed/autonomous_communities/`:

- `autonomous_communities.parquet`: GeoParquet 1.1 (zstd, with a bbox covering column),
  EPSG:4326, one row per autonomous community, sorted by `id`. Columns: `id`, `ine_code`,
  `name`, `ign_code`, `geometry`.
- `autonomous_communities.meta.json`: run details (retrieval date, request, raw file size and
  SHA-256, row count).

The raw download is kept in `data/raw/autonomous_communities/{retrieval date}/autonomous_communities.geojson`.

## Catalogue

[`catalog.json`](catalog.json) describes the `autonomous_community` entity type and its id
scheme, and the `ign_au_autonomous_communities` dataset (source, license, validity, coverage and
fields). The `part_of` relation from provinces is declared by the provinces pipeline.
