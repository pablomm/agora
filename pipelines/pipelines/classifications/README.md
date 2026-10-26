# Classifications

INE's national statistical classifications, as tables to join data with later. Not geographic:
codes and labels of activities, occupations, education and products, with their hierarchy and the
correspondences between versions and with the international ones.

```sh
python pipelines/classifications/classifications.py   # seconds (10 small files)
```

## Classifications

| Id | Classification | Levels (count) | Source |
|---|---|---|---|
| `cnae2025` | Clasificación Nacional de Actividades Económicas, CNAE-2025 | Sección 22 · División 87 · Grupo 287 · Clase 664 | `Estructura_CNAE2025.xlsx` |
| `cnae2009` | CNAE-2009 (what the census and most series still use) | Sección 21 · División 88 · Grupo 272 · Clase 629 | `estructura_cnae2009.xls` |
| `cno11` | Clasificación Nacional de Ocupaciones, CNO-11 | Gran grupo 10 · Grupo principal 17 · Subgrupo principal 62 · Subgrupo 170 · Grupo primario 502 | `cno11_estructura.xls` |
| `cned2014_a` | Clasificación Nacional de Educación, niveles de formación alcanzados (CNED-A 2014) | Agregado 3 · Nivel de formación 9 · Grupo 13 · Nivel detallado 24 | `CNED14_A_estr.xls` |
| `cned2014_f` | CNED 2014, sectores de estudio (CNED-F) | Sector amplio 11 · Sector específico 39 · Sector detallado 93 | `CNED_F_estr.xlsx` |
| `cpa22` | Clasificación de Productos por Actividades, CPA 2.2 | Sección 22 · División 87 · Grupo 284 · Clase 644 · Categoría 1,433 · Subcategoría 3,354 | `CPA_22_estructura.xlsx` |

- Codes are INE's, except that CNAE and CPA drop their dots, so both CNAE versions write a class
  the same way (`0111`); the API takes codes with or without dots.
- Parents come from the codes (CNAE, CPA, CNED-F: a code's prefix) or from INE's order where
  digits and letters interleave: CNO-11 is gran grupo `2` > grupo principal `B` > `21` > `211` >
  `2111`; CNED-A is `C` > `8` > `CM` > `81`.
- Each run checks every parent is a code of its classification, codes don't repeat, and every
  correspondence names codes that exist.

## Correspondences

| From | To | Pairs | Source |
|---|---|---|---|
| `cnae2009` | `cnae2025` | 1,665 | `Correspondencia_CNAE09_CNAE25.xlsx` |
| `cnae2025` | `cnae2009` | 1,665 | `Correspondencia_CNAE25_CNAE09.xlsx` |
| `cno11` | `ciuo08` (ISCO-08) | 541 | `corr_cno11_ciuo08.xls` (ISCO-08 occupations with no Spanish one are left out) |
| `cned2014_a` | `cine2011_a` (ISCED-A 2011) | 24 | `CORR_CNED14_CINE11_A.xls` |
| `education_level` | `cned2014_a` | 19 | This pipeline: the census education levels used across the platform (see the population pipeline) as CNED-A groups |
| `occupation_group` | `cno11` | 9 | This pipeline: the census occupation groups (CNO-11 major groups 1–3, 4–8, 9) |
| `sector` | `cnae2009` | 21 | This pipeline: the sectors of the census and the SEPE registers (A; B–E; F; G–U) |

One row per pair; an item can match several (a CNAE-2009 class split in CNAE-2025). Labels of
ISCO-08 and ISCED-2011 come with the pairs (they aren't classifications here).

## Links with the data

Data dimensions say how they relate to a classification, in their pipeline's `catalog.json`:

- `"classification": {"id": "cno11", "level": 1}`: the values are the classification's codes of
  that level (`employed_cno11`'s `cno11`: `1`–`9`; `cnae2009`: `A`–`U`), with its labels; the API
  checks every code exists.
- `"groups_of": "cnae2009"`: the values group the classification's codes, through the
  correspondences above (`sector`, `occupation_group`, `education_level`); the API checks every
  value has them.

`/classifications/{id}/{code}` lists the dimensions that hold a code, directly or in a group (CNO-11
`2111` is in `cno11` = `2` and in `occupation_group` = `high_skilled`).

## Output

`data/processed/classifications/items.parquet` (`classification`, `code`, `label`, `level`,
`level_name`, `parent`, `position`) and `correspondences.parquet` (`from_classification`,
`from_code`, `to_classification`, `to_code`, `to_label`, `note`); `meta.json` has the sources'
checksums and counts. The API loads both into its catalogue (`/classifications`).

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
