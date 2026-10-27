# Housing

Housing data that isn't in the census pipelines. For now, INE's experimental statistic on tourist
dwellings ("Medición del número de viviendas turísticas en España y su capacidad"): dwellings listed
on three of the main short-let platforms (INE doesn't name them), found by web scraping.

```sh
python pipelines/housing/tourist_dwellings.py   # ~1 min; ~100 MB of downloads (13 Excel files, 4 tables)
```

Needs the provinces pipeline (provinces → autonomous communities, for the checks).

## Datasets

| Dataset | Values | Levels | Periods | Breakdown |
|---|---|---|---|---|
| `tourist_dwellings` | Tourist dwellings, their beds, and their share of all dwellings (%) | section → district → municipality → province → autonomous community → Spain | 2020-08 – 2026-05 | `tourist_measure` (`dwellings`, `beds`, `share`) |

Periods are months (`202605`): February and August until 2024, then November 2024 and May and
November since. INE plans to publish every three months.

Every level is kept as INE publishes it (`origin = published`), with no imputation:

- **Sections and districts**: one Excel file per period, found on
  `exp_viv_turistica_descarga.htm` (`tabla5_{MONTH}{YEAR}.xlsx`); new periods are picked up on the next
  run. Their column names change case from file to file.
- **Municipalities**: tables 39363 (dwellings, beds) and 39366 (share).
- **Provinces, communities and Spain**: tables 39364 and 39365.

Counts add up exactly from sections to Spain in every period (checked, in `meta.json`). Beds per
dwelling isn't stored: the catalogue divides beds by dwellings (INE's own figure, rounded to two
decimals, is the same).

- **Sections are each period's**: 35,960 until February 2023 (as drawn for the 2011 census), 37,063
  in August 2023, about 36,500 since. 97% of the older ones and 99.7% of the newer ones are in
  today's cartography; the rest aren't drawn on the map.
- **The share** divides by the census's dwellings: the 2011 census until August 2023, the 2021 one
  since February 2024, so it jumps between both. INE hides it where the census counted few
  dwellings (statistical secrecy): those cells are left out, while their counts are kept.
- Areas without tourist dwellings have 0 dwellings, 0 beds and a 0% share.

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es". Experimental statistics are flagged by INE as
not yet meeting the quality standards of official ones.
