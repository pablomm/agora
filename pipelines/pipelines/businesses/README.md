# Businesses

Companies from INE's Directorio Central de Empresas (DIRCE), the register of every active company
in Spain but farms, fisheries, public administration, households and extraterritorial bodies (CNAE
sections A, O, T and U). Each company counts once, in the municipality of its registered seat, on
1 January, by main activity (CNAE-2009).

```sh
python pipelines/businesses/dirce.py   # ~15 s; ~100 MB download (one table)
```

Needs the provinces pipeline (provinces → autonomous communities) and the population pipeline's
official figures (`official_figures.py`), whose population weighs the imputation.

## Datasets

| Dataset | Values | Levels | Periods | Breakdown |
|---|---|---|---|---|
| `companies` | Active companies | municipality → province → autonomous community → Spain | 2012–2025 | `activity_group` |

Table 4721 ("Empresas por municipio y actividad principal") has every level. `activity_group`:
total; industry (B–E), construction (F), trade, transport and hospitality (G–I) and the other
services (J–S, INE's "Total servicios", which leaves out G–I); and those other services in six
(J, K, L, M–N, P–Q, R–S), nested under them. Each breakdown adds up exactly to its parent (checked).

What INE publishes by municipality:

- **Totals** for every municipality, but small ones are hidden (".", statistical secrecy): about
  1,200 a year. INE doesn't state its threshold; no published total is under 4, so hidden ones are
  taken as 0 to 3.
- **The four main groups** for about 3,100 municipalities, and **services in detail** for about
  1,300; the rest have no breakdown (empty cells). Within a breakdown, INE hides small cells and
  at least one more with each (secondary secrecy, so they can't be worked out from the total):
  usually two per municipality.

Output: `data/processed/businesses/companies/{level}.parquet` with `entity_id`, `code`, `period`,
`activity_group`, `value` and `origin` (`published`, `imputed` for municipalities, `aggregated` for
communities). `meta.json` has the checks and imputation counts.

## Imputation

No hidden cell is left blank; municipalities without a breakdown stay without one.

- **A hidden total**: what its province has beyond its published municipalities, shared out among
  the hidden ones by population (official figures, same year), none above 3, as integers.
- **A hidden group**: what its parent (the total, or the other services) has beyond the published
  groups, shared out by the province's mix of those groups.

Provinces and Spain are kept as published; communities are summed from provinces. Municipalities
add up to their province in every year but two: in 2012 INE's totals for Málaga (135) and
Tarragona (283) are more than their municipalities can hold, even with every hidden one at 3. Those
companies aren't assigned to any municipality (`province_beyond_municipalities` in `meta.json`).

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
