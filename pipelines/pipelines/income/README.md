# Income

INE's Atlas de Distribución de Renta de los Hogares (ADRH, operation 353): household income from
tax records, by census section, district and municipality, and by province, autonomous community
and Spain, from 2015.

```sh
python pipelines/income/adrh.py        # ~10 min; ~17 GB of downloads (530 tables)
```

Needs the provinces pipeline (provinces → autonomous communities).

## Datasets

| Dataset | Values | Breakdown |
|---|---|---|
| `income_levels` | Net and gross mean income per person and per household, mean and median income per consumption unit (€) | `income_indicator` |
| `income_sources` | Share of gross income from wages, pensions, unemployment benefits, other benefits, other income (%) | `income_source` |
| `income_inequality` | Gini index, P80/P20 ratio | `inequality_indicator` |
| `income_demographics` | Mean household size, single-person households (%), and ADRH's population, mean age and shares by age and nationality | `household_indicator` |
| `income_relative` | % of the population with income per consumption unit below 40, 50, 60% of the median, or above 140, 160, 200% | `sex` × `income_group` (everyone, age band or nationality) × `income_threshold` |
| `income_fixed` | % of the population below 5,000, 7,500, 10,000 € per consumption unit | `sex` × `income_group` × `income_threshold_fixed` |

Every level is kept as INE publishes it: means, medians and shares can't be summed. The period is
the income year (published about two years later). Output:
`data/processed/income/{dataset}/{level}.parquet` with `entity_id`, `code`, `period`, the
breakdown, `value` and `origin` (`published` or `imputed`); `meta.json` has the tables, hidden and
imputed cells by level.

## Sources

Ten kinds of table, each with one table per province (its municipalities, districts and sections)
and a national one (Spain, communities, provinces, islands; places by name, mapped to codes in
`adrh.py`). Each kind also has a table with every municipality of Spain, the provincial ones
together row by row: it isn't used.

- Spain as a whole is published from 2021 only (empty before), and some foral indicators are ".."
  (not available) before 2020: left out, as cells for units that didn't exist that year.
- Some tables come in English format ("Period", 12,345.6): read like the rest.
- A few units in 2015 (six sections, one district) have the shares above 140, 160 and 200% of
  the median rising, likely their complement published by mistake: taken as hidden and imputed.

## Hidden values

INE hides units with few tax returns ("."): 3–11% of municipalities and sections in the main
tables, and 80–90% of sections in the breakdowns by age and nationality. None is left blank
(`origin = imputed`), filled from the top down (province, municipality, district, section):

- A breakdown's cell (by sex, age or nationality) whose unit total is known: the unit's total
  times the cell's ratio to the total in the unit above. Shares are capped at 100.
- Anything else: the value of the nearest unit above that has one.
- Population, a count: what the unit above has beyond its published units, shared among the hidden
  ones by their size in the years they're published.
- With nothing above (foral municipalities before 2020): the same unit's value in the nearest year.

INE also caps the extremes: each year some 170 sections share the highest value of an indicator,
and some 30 the lowest (top- and bottom-coding for confidentiality). They're kept as published.

## License

INE: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per its
[legal notice](https://ine.es/dyngs/AYU/index.htm?cid=125). Attribution: "Elaboración propia con
datos extraídos del sitio web del INE: www.ine.es".
