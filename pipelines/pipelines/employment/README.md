# Employment

Labour statistics at municipal level or finer, aggregated up to provinces, autonomous
communities and Spain. Only series with at least municipal detail are kept (the EPA and Social
Security affiliation, provincial at best in open data, are left out).

```sh
python pipelines/employment/sepe.py              # SEPE registers, monthly (≈ 3 min)
python pipelines/employment/census_activity.py   # INE census, by section (needs the population pipeline's census_annual.py first)
```

## Datasets

| Dataset | Source | Base level | Periods | Dimensions |
|---|---|---|---|---|
| `registered_unemployment` | SEPE, [Paro registrado por municipio](https://datos.gob.es/es/catalogo/ea0041513-paro-registrado-por-municipio) | Municipality | Monthly, 2006-01 → 2026-09 | sex × age band (<25, 25–44, ≥45); sector (agriculture, industry, construction, services, no previous job) |
| `job_seekers` | SEPE, [Demandantes de empleo por municipio](https://datos.gob.es/es/catalogo/ea0041513-demandantes-de-empleo-por-municipio) | Municipality | Monthly, 2006-01 → 2026-09 | as above |
| `contracts` | SEPE, [Contratos registrados por municipio](https://datos.gob.es/es/catalogo/ea0041513-contratos-registrados-por-municipio) | Municipality | Monthly, 2006-01 → 2026-09 | sex × contract type (permanent, temporary, converted to permanent); sector |
| `census_activity` | INE, Censo anual de población, table 66594 | Census section | Yearly (1 January), 2021–2024 | sex × relation with activity (employed, unemployed, pensioner, student, other inactive) |

Output: `data/processed/employment/{dataset}/{level}.parquet` (`entity_id`, `code`, `period`,
dimensions, `value`, `origin`) and `meta.json`. Monthly periods are integers `YYYYMM`. SEPE's
sector breakdown doesn't cross with sex or age: its rows have `sex = age_band = total`.

## SEPE: gaps and hidden values

- **Files**: one CSV per year; the months they lack come from the half-year XLS files (2013 after
  April; 2026's registered unemployment CSV is cut short at the source).
- **December 2020** isn't published in any file: it's interpolated (mean of November 2020 and
  January 2021, adjusted so breakdowns add up) and flagged `imputed`.
- **Values under 5** are hidden as "<5" since January 2022 (about 1.5 million cells per series).
  They're imputed so every breakdown adds up to its total:
  - a hidden total comes from the municipality's nearest months with a known total, within what
    its breakdowns allow (each hidden cell is 1 to 4);
  - the hidden cells of a breakdown share what's left of the total, each 1 to 4, in proportion
    to the municipality's own composition in 2019–2021 (complete data) blended with its
    province's that month.
  Imputed rows have `origin = "imputed"`. Every row adds up (checked); national totals match
  SEPE's published figures exactly up to 2021 and within ±0.03 % after (December 2024: 2,561,372
  against 2,560,718 published), the difference coming from hidden totals.

## INE census: hidden values

INE hides small units: sections ("."), and municipalities (left empty, or "."). A hidden
municipality's cells share its province's remainder (province minus known municipalities), and a
hidden section's cells its municipality's, in proportion to their population aged 15 and over
(annual census), rounded so they add up. After imputation, sections add up exactly to every
municipality INE publishes and municipalities to every province (checked: 0 mismatches).

## Licences

- SEPE: CC BY 4.0 (datos.gob.es). Attribution: "Servicio Público de Empleo Estatal (SEPE)",
  stating that values under 5 were imputed.
- INE: CC BY 4.0, "Elaboración propia con datos extraídos del sitio web del INE: www.ine.es".

## Layers (catalog.json)

Registered unemployment (by sex and age; by sector; share by sector; over population aged 15–64,
which divides each month by the census population of its year, from 2021, the latest census year
for later months), job seekers (by sex and age; by sector), contracts (by sex and type; by
sector; share of permanent contracts), and from the census: unemployment, activity and employment
rates, and population 16+ by relation with activity (count and share), all by sex.
