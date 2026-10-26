# Employment

Labour statistics at municipal level or finer, aggregated up to provinces, autonomous
communities and Spain. Only series with at least municipal detail are kept (the EPA and Social
Security affiliation, provincial at best in open data, are left out).

```sh
python pipelines/employment/sepe.py              # SEPE registers, monthly (≈ 3 min)
python pipelines/employment/census_activity.py sex             # INE census, by section (needs the population pipeline's census_annual.py first)
python pipelines/population/census_origin.py census_activity_born   # the same by birthplace (52 provincial tables)
python pipelines/employment/census_activity.py groups gaps     # both in one dimension, and the gaps
python pipelines/population/census_origin.py employed_occupation employed_sector employed_status   # the employed by occupation, sector and status, by section
python pipelines/population/census_municipal.py employed_cno11 employed_cnae2009 employed_status_detail  # … by CNO-11 and CNAE-2009 codes, status in detail (needs the classifications pipeline)
```

## Datasets

| Dataset | Source | Base level | Periods | Dimensions |
|---|---|---|---|---|
| `registered_unemployment` | SEPE, [Paro registrado por municipio](https://datos.gob.es/es/catalogo/ea0041513-paro-registrado-por-municipio) | Municipality | Monthly, 2006-01 → 2026-09 | sex × age band (<25, 25–44, ≥45); sector (agriculture, industry, construction, services, no previous job) |
| `job_seekers` | SEPE, [Demandantes de empleo por municipio](https://datos.gob.es/es/catalogo/ea0041513-demandantes-de-empleo-por-municipio) | Municipality | Monthly, 2006-01 → 2026-09 | as above |
| `contracts` | SEPE, [Contratos registrados por municipio](https://datos.gob.es/es/catalogo/ea0041513-contratos-registrados-por-municipio) | Municipality | Monthly, 2006-01 → 2026-09 | sex × contract type (permanent, temporary, converted to permanent); sector |
| `census_activity` | INE, Censo anual de población, table 66594 | Census section | Yearly (1 January), 2021–2024 | sex × relation with activity (employed, unemployed, pensioner, student, other inactive) |
| `census_activity_born` | INE, Censo anual de población, "Población de 16 y más años por país de nacimiento (España/extranjero) y relación con la actividad", one table per province (52, from 66640) | Census section | Yearly, 2021–2024 | born in Spain/abroad × relation with activity; hidden units imputed like the population pipeline's (`census_origin.py`) |
| `census_activity_groups` | Derived from the two above | Census section | Yearly, 2021–2024 | group (everyone, men, women, born in Spain, born abroad) × relation with activity, with `active` and `inactive` as groups |
| `employed_occupation` | INE, Censo anual, "Ocupados de 16 y más años por sexo y ocupación (agregada)", one table per province (52, from 70016) | Census section | Yearly, 2021–2023 | sex × occupation group (CNO-11 1–3, 4–8, 9, not stated); hidden units imputed |
| `employed_sector` | INE, Censo anual, "… por sexo y rama de actividad", one table per province (52, from 70017) | Census section | Yearly, 2021–2023 | sex × sector (CNAE-2009 A, B–E, F, G–U, not stated); hidden units imputed |
| `employed_status` | INE, Censo anual, "Ocupados de 16 y más años por sexo y situación profesional (agregada)", one table per province (52, from 70018) | Census section | Yearly, 2021–2023 | sex × professional status (self-employed, employees and other); hidden units imputed |
| `employed_status_detail` | INE, Censo anual, table 69993 | Municipality (500 residents or more) | Yearly, 2021–2023 | sex × professional status (employers, own-account, permanent and temporary employees, nested in the two above); matches `employed_status` summed up to municipalities exactly |
| `employed_cno11` | INE, Censo anual, table 69991 | Municipality (500 residents or more) | Yearly, 2021–2023 | sex × CNO-11 major group (`1`–`9`, codes of the classification) |
| `employed_cnae2009` | INE, Censo anual, table 69992 | Municipality (500 residents or more) | Yearly, 2021–2023 | sex × CNAE-2009 section (`A`–`U`), plus groups: professional services (M–N), public administration, education and health (O–Q) |
| `census_activity_gaps` | Derived from `census_activity_groups` | Census section | Yearly, 2021–2024 | rate (activity, employment, unemployment) × comparison (women − men, born abroad − born in Spain), in points |

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
for later months), job seekers (by sex and age; by sector), contracts (by sex and type, and each
type's share of all contracts; by sector, and each sector's share; share of permanent contracts), and from the census: unemployment, activity and employment
rates, and population 16+ by relation with activity (count and share, with the active and the
inactive), all by group (sex or birthplace); and the gaps in those rates between women and men,
and between those born abroad and in Spain. The employed by occupation and by sector (nº · %),
down to census sections, and by CNO-11 major group and CNAE-2009 section in municipalities of 500
residents or more (with professional services and administration, education and health as groups
of sections); by professional status (self-employed, employees) down to sections, and in detail
(employers, own-account, permanent and temporary employees) by municipality. Their totals match the employed of `census_activity` exactly.
