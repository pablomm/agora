# Income distribution

The income distribution of every census section and year (2015–2024), fitted to what INE's
household income atlas (ADRH) publishes about it: the population by net income per consumption
unit, as a Dagum distribution, from census sections to Spain. Its parameters are the
`income_distribution` dataset, in the catalogue but **not a map layer** (a distribution's
parameters say nothing on a map): a unit's detail will draw its distribution from them, and they
answer what INE doesn't publish (any threshold or quantile, polarisation, areas that aren't
administrative units).

```sh
python pipelines/income_distribution/fit.py           # ~7 min; needs the income pipeline's output
python pipelines/income_distribution/plot.py 2807901001 2023 --out section.png
```

Needs `scipy`, and `matplotlib` for the plots (`pip install -e '.[plots]'`).

## Model

Each unit and year has up to 13 published figures about the same distribution:

- nine points of its CDF: the share below 5,000, 7,500 and 10,000 €; below 40, 50 and 60% of the
  median; above 140, 160 and 200%;
- its median and mean income per consumption unit, Gini index and P80/P20 ratio.

The relative thresholds are a share of **Spain's** median, the same in euros for every unit. The
median isn't published before 2021, so the pipeline estimates it each year as the one that fits
the sections best: 19,204 € for 2023 against the 19,250 € published (2022 and 2024 as close). In
2021 the thresholds behave like a median of about 16,400 €, not the 17,150 € published: Spain's own
figures agree (fewer people below 60% of the median than below 10,000 €, so 60% of it is under
10,000 €).

A **Dagum** distribution, F(x) = (1 + (x/b)^-a)^-p, is fitted to them by weighted least squares
(batched Levenberg–Marquardt), with a **lognormal** alongside as a baseline:

- Hidden and imputed figures aren't used. Units with fewer than 4 figures inherit the fit of the
  nearest unit above (a section its district's, else its municipality's…), else (nothing above:
  foral units before 2020) their own in the nearest year.
- INE caps the extremes (each year ~170 sections share the top value of each figure, ~30 the
  bottom). A figure at the cap is a bound: past it costs ten times less than short of it.
- The tail index is kept above 2 (finite mean and variance), and a weak prior holds the shape near
  a typical section's: both only matter where caps leave the tails free, as in the richest
  sections, whose median, mean, Gini and top shares are all at the cap.

Every level above sections is fitted directly too, and built as the population-weighted mixture of
its sections' distributions; comparing the mixture with what INE publishes for it measures how well
the sections' distributions add up.

## Results

Mean absolute error, in points for shares and Gini, in % for the median and mean (capped figures
left out). Out of sample: each figure left out of the fit of 5,000 fully published sections in
turn, then predicted.

| | Sections | Out of sample | Mixture: districts | Mixture: provinces | Mixture: Spain |
|---|---|---|---|---|---|
| Shares (9) | 0.5–0.8 | 0.6–1.0 | 0.5–0.7 | 0.15–0.35 | 0.02–0.2 |
| Median | 1.5% | 2.2% | 1.4% | 1.2% | 0.9% |
| Mean | 1.6% | 1.7% | 1.7% | 0.9% | 1.3% |
| Gini | 0.7 | 1.2 | 0.7 | 0.8 | 1.2 |
| P80/P20 | 0.07 | 0.11 | 0.07 | 0.06 | 0.10 |

The lognormal is 2–4 times worse on everything (shares 1.2–3.2 points off in sample).

Known biases: the mixture's Gini is above INE's, increasingly up the levels (+0.4 points in
districts, +1.2 in Spain), and its mean 1% below (INE's mean per consumption unit is total income
over total units, not quite the persons' mean). Sections: 94.7% fitted, 5.3% inherit their
district's or municipality's fit; communities without anything above (foral, before 2020) take
their own in the nearest year. No unit is left without a distribution.

## Output

`data/processed/income_distribution/`:

- `income_distribution/{level}.parquet`, the dataset: `entity_id`, `code`, `period`,
  `distribution_parameter` (`a`, `b`, `p`), `value` and `origin` (`fitted`, `inherited` from the
  unit above, `nearest_year`). Every level from census sections; Spain from 2021 (INE publishes it
  from then). With F(x) = (1 + (x/b)^-a)^-p:
  - share below x: F(x); quantile u: b·(u^(-1/p) - 1)^(-1/a); density: a·p/x · (x/b)^(ap) / (1 + (x/b)^a)^(p+1);
  - mean: b·Γ(p + 1/a)·Γ(1 - 1/a)/Γ(p); Gini: Γ(p)·Γ(2p + 1/a)/(Γ(2p)·Γ(p + 1/a)) - 1.
- `fits.parquet`: the fits with their diagnostics, one row per level, unit and year: `figures` (how
  many were published), the Dagum's and the lognormal's parameters and loss, `origin`, and the
  `population` that weights the mixtures (ADRH's).
- `mixture_validation.parquet`: each published figure above sections against its sections' mixture.
- `meta.json`: the national medians, caps, units by origin and every error measure.

## License

Derived from INE's ADRH ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)). Attribution:
"Elaboración propia con datos extraídos del sitio web del INE: www.ine.es".
