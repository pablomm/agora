# Municipalities

The 8,132 municipalities of Spain, with their current boundaries, as GeoParquet keyed by INE
code; and, in a separate file, the 81 shared territories that belong to several municipalities
at once.

```sh
python pipelines/municipalities/municipalities.py            # reuses today's download if there is one
python pipelines/municipalities/municipalities.py --refresh  # downloads again
```

The download is about 460 MB and takes a few minutes; the run needs about 2 GB of memory.

## Source

| | |
|---|---|
| Publisher | Instituto Geográfico Nacional (IGN) |
| Service | WFS INSPIRE *Unidades administrativas de España*: `https://www.ign.es/wfs-inspire/unidades-administrativas` |
| Feature type | `au:AdministrativeUnit`, filtered on `nationalLevel` = `4thOrder` |
| Format requested | GeoJSON in EPSG:4326 |
| Metadata | [IDEE catalogue record `spaignLLM`](https://www.idee.es/csw-inspire-idee/srv/spa/csw?SERVICE=CSW&VERSION=2.0.2&REQUEST=GetRecordById&outputSchema=http://www.isotc211.org/2005/gmd&ElementSetName=full&ID=spaignLLM) |
| License | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as stated in the service's capabilities |
| Attribution | **CC BY 4.0 ign.es** (required wherever the data or derived maps are shown) |

Same service as the [provinces](../provinces/README.md) and
[autonomous communities](../autonomous_communities/README.md); the request and parsing live in `common/ign.py`.

## Validity

The service publishes the **current** municipalities and boundaries, without validity dates. The
data is valid **as of the retrieval date**, recorded in the `.meta.json` files and the raw folder's name.

Municipalities change a few times a year (new ones split off, others merge, names change), so:

- This is a **snapshot**: municipalities that no longer exist aren't here, and older statistics
  may refer to codes this file doesn't have.
- Codes, names and their changes over time will come from INE's registry in a separate pipeline
  (planned): each municipality's validity, its earlier names, and merges and splits as relations.
- The pipeline expects exactly **8,132** municipalities, INE's count when it was written. If IGN
  publishes a different number, the run fails on purpose: check what changed, then update
  `EXPECTED_MUNICIPALITIES`.

## What's in IGN's fourth level

| Units | What they are | Where they go |
|---|---|---|
| 8,132 | Municipalities, each with its INE code | `municipalities.parquet` |
| 81 | Shared territories: land held in common by several municipalities (comunidades, facerías, parzonerías, ledanías, Bardenas Reales…) | `shared_territories.parquet` |
| 7 | *Territorios no asociados a ninguna provincia*: plazas de soberanía, Isla de los Faisanes and Gibraltar | Excluded |

The shared territories aren't municipalities (no INE code, no population of their own), but they
cover about 1,260 km², and without them the map would have holes: 5.7 % of Navarra, 3.6 % of
Gipuzkoa. Bardenas Reales alone is 420 km².

## Identifiers

- Municipality: `es:ine:mun:{ine_code}`, e.g. `es:ine:mun:28079` (Madrid). The INE code has five
  digits (province + three), without the control digit INE adds in some publications.
- Shared territory: `es:ign:au:{ign_code}`, e.g. `es:ign:au:34153153078` (Bardenas Reales), since
  only IGN codes them.

IGN's `nationalCode` is `34` (Spain) + autonomous community + province + five digits. For a
municipality, the five digits are its INE code (`34132828079` is Madrid); shared territories have
`53` + three digits instead. The pipeline fails on any other shape, on a municipality code that
doesn't start with its province, on duplicated codes, on a province without municipalities, or on
a count other than the expected one.

## Names

As IGN publishes them, bilingual where that's the official form. INE writes some names
differently (articles at the end: `Coruña, A`), so joining by name is unreliable: always join by code.
Some shared territories are named after the INE codes of the municipalities that share them
(`Comunidad de 09076, 09290 y 09578`).

## Consistency with provinces

Checked on the 2026-10-25 download: every `parent_id` is one of the 52 provinces, all geometries
are valid, and for each province the union of its municipalities and shared territories equals
the province's geometry (no area difference).

## Output

In `data/processed/municipalities/`:

- `municipalities.parquet`: GeoParquet 1.1 (zstd, with a bbox covering column), EPSG:4326, one row
  per municipality, sorted by `id`. Columns: `id`, `ine_code`, `name`, `province_code`,
  `ccaa_code`, `parent_id`, `ign_code`, `geometry`.
- `shared_territories.parquet`: same format. Columns: `id`, `name`, `province_code`, `ccaa_code`,
  `parent_id`, `ign_code`, `geometry`.
- `municipalities.meta.json`, `shared_territories.meta.json`: run details (retrieval date,
  request, raw file size and SHA-256, row count).

The raw download is kept in `data/raw/municipalities/{retrieval date}/municipalities.geojson`.

## Catalogue

[`catalog.json`](catalog.json) describes the `municipality` and `shared_territory` entity types and
their id schemes, their `part_of` relations to provinces, and the two datasets (source, license,
validity, coverage and fields).
