"""
The income distribution of every census section and year, fitted to what the ADRH publishes about
it (income pipeline, `total` sex and group): a Dagum distribution of the population by income per
consumption unit, with a lognormal fitted alongside as a baseline.

Each unit has up to 13 published figures, all about that same distribution:

- nine points of its CDF: the share below 5,000, 7,500 and 10,000 €, below 40, 50 and 60% of the
  median, and above 140, 160 and 200%. The relative thresholds are the same in euros for every unit:
  a share of Spain's median that year (estimated from the sections, see `national_median`).
- its median and mean income per consumption unit, Gini index and P80/P20 ratio.

The fit is a weighted least squares on those figures (`SIGMA`), batched over all units at once
(Levenberg–Marquardt). Hidden and imputed figures aren't used. Figures at INE's top or bottom cap
(many sections share the same extreme value each year) are a bound: going past the cap costs ten
times less than falling short of it (the true value is beyond it, likely not far). A weak prior
keeps the shape near a typical section's where the figures don't pin it down. Sections with too few
figures inherit the fit of the nearest unit above.

Districts, municipalities and every level up are fitted the same way and, separately, built as the
population-weighted mixture of their sections' distributions: compared with what INE publishes for
them, that measures how well the sections' distributions add up.

    python pipelines/income_distribution/fit.py [--holdout 5000]
"""

import argparse
import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import scipy.sparse as sparse
from scipy.special import gammaln, ndtr, ndtri

from common.paths import DATA_DIR, output_dir
from common.rollup import COUNTRY_ID, ID_PREFIX, ccaa_by_province, parent_codes

log = logging.getLogger(__name__)

PIPELINE = "income_distribution"
SOURCE = DATA_DIR / "processed/income"
LEVELS = ["census_section", "census_district", "municipality", "province", "autonomous_community", "country"]

FIXED = {"below_5000": 5000, "below_7500": 7500, "below_10000": 10000}
RELATIVE = {"below_40": 0.4, "below_50": 0.5, "below_60": 0.6, "above_140": 1.4, "above_160": 1.6, "above_200": 2.0}
THRESHOLDS = [*FIXED, *RELATIVE]
#: Every published figure, in the order of the model's predictions.
FIGURES = [*THRESHOLDS, "median", "mean", "gini", "p80_p20"]
#: How far (in the fit's scale: CDF, log euros, Gini as a fraction, log ratio) a prediction may be
#: from each figure for one unit of loss. Mean income per consumption unit is total income over
#: total units, not quite the mean of the persons' distribution: looser.
SIGMA = np.array([0.01] * len(THRESHOLDS) + [0.02, 0.04, 0.01, 0.03])
#: How much less a prediction past a capped figure costs than one short of it.
BEYOND_CAP = 10
#: Fewer published figures than this and the unit isn't fitted (a section inherits its parent's fit).
MIN_FIGURES = 4


class Lognormal:
    name, params, prior = "lognormal", ("mu", "sigma"), None

    @staticmethod
    def unpack(theta):
        return theta[..., 0], np.exp(theta[..., 1])

    @staticmethod
    def pack(mu, sigma):
        return np.stack([mu, np.log(sigma)], axis=-1)

    @staticmethod
    def cdf(x, mu, sigma):
        return ndtr((np.log(x) - mu) / sigma)

    @staticmethod
    def pdf(x, mu, sigma):
        return np.exp(-0.5 * ((np.log(x) - mu) / sigma) ** 2) / (x * sigma * np.sqrt(2 * np.pi))

    @staticmethod
    def quantile(u, mu, sigma):
        return np.exp(mu + sigma * ndtri(u))

    @staticmethod
    def log_mean(mu, sigma):
        return mu + sigma**2 / 2

    @staticmethod
    def gini(mu, sigma):
        return 2 * ndtr(sigma / np.sqrt(2)) - 1

    @staticmethod
    def starts(median, gini):
        sigma = np.sqrt(2) * ndtri((np.clip(gini, 0.1, 0.6) + 1) / 2)
        return [np.stack([np.log(median), np.log(sigma)], axis=-1)]


class Dagum:
    """
    F(x) = (1 + (x/b)^-a)^-p. Its upper tail is Pareto with index a: a > 2 keeps the mean and variance
    finite, which INE's caps alone don't (a capped mean or Gini only bounds them from below).
    """

    name, params = "dagum", ("a", "b", "p")
    #: A weak prior on the shape, log(a - 2) and log(p), around a typical section's (a ≈ 4.5,
    #: p ≈ 0.45): it only matters when the figures don't pin the tails down, as in the richest
    #: sections, whose median, mean and Gini are all at INE's top code.
    prior = (np.array([0.9, np.nan, -0.8]), np.array([0.5, np.nan, 0.5]))

    @staticmethod
    def unpack(theta):
        return 2 + np.exp(theta[..., 0]), np.exp(theta[..., 1]), np.exp(theta[..., 2])

    @staticmethod
    def pack(a, b, p):
        return np.stack([np.log(a - 2), np.log(b), np.log(p)], axis=-1)

    @staticmethod
    def cdf(x, a, b, p):
        return np.exp(-p * np.log1p(np.exp(-a * (np.log(x) - np.log(b)))))

    @staticmethod
    def pdf(x, a, b, p):
        z = np.exp(a * (np.log(x) - np.log(b)))
        return a * p / x * np.exp(p * np.log(z) - (p + 1) * np.log1p(z))

    @staticmethod
    def quantile(u, a, b, p):
        return b * (u ** (-1 / p) - 1) ** (-1 / a)

    @staticmethod
    def log_mean(a, b, p):
        return np.log(b) + gammaln(p + 1 / a) + gammaln(1 - 1 / a) - gammaln(p)

    @staticmethod
    def gini(a, b, p):
        return np.exp(gammaln(p) + gammaln(2 * p + 1 / a) - gammaln(2 * p) - gammaln(p + 1 / a)) - 1

    @staticmethod
    def starts(median, gini):
        out = []
        for a in (2.5, 4.0, 6.0):
            for p in (0.4, 0.8, 1.5):
                b = median * (2 ** (1 / p) - 1) ** (1 / a)
                out.append(Dagum.pack(np.full_like(median, a), b, np.full_like(median, p)))
        return out


MODELS = {model.name: model for model in (Dagum, Lognormal)}


def predict(model, theta: np.ndarray, x: np.ndarray) -> np.ndarray:
    """The 13 figures (in the fit's scale) of each unit's distribution; `x` has its thresholds in euros."""
    params = model.unpack(theta)
    column = [param[:, None] for param in params]
    cdf = model.cdf(x, *column)
    quantiles = model.quantile(np.array([0.5, 0.2, 0.8]), *column)
    return np.column_stack([cdf, np.log(quantiles[:, 0]), model.log_mean(*params), model.gini(*params), np.log(quantiles[:, 2] / quantiles[:, 1])])


def residuals(model, theta, x, y, mask, bound):
    """Scaled residuals; past a capped figure (in the direction its true value lies), much looser."""
    r = (predict(model, theta, x) - y) / SIGMA
    r = np.where(bound * r > 0, r / BEYOND_CAP, r)
    r = np.where(mask, r, 0.0)
    if model.prior is not None:
        center, scale = model.prior
        shape = np.isfinite(center)
        r = np.column_stack([r, (theta[:, shape] - center[shape]) / scale[shape]])
    return np.where(np.isfinite(r), r, 1e3)


def fit(model, x, y, mask, bound, iterations: int = 80) -> tuple[np.ndarray, np.ndarray]:
    """Batched Levenberg–Marquardt from the best of a few starts. Returns parameters and loss (sum of squares)."""
    median = np.exp(np.where(mask[:, 9], y[:, 9], np.where(mask[:, 10], y[:, 10] - 0.15, np.log(15000))))
    gini = np.where(mask[:, 11], y[:, 11], 0.3)
    best, loss = None, None
    for start in model.starts(median, gini):
        current = (residuals(model, start, x, y, mask, bound) ** 2).sum(1)
        if best is None:
            best, loss = start.copy(), current
        else:
            better = current < loss
            best[better], loss[better] = start[better], current[better]
    theta, damping = best, np.full(len(best), 1e-2)
    k = theta.shape[1]
    for _ in range(iterations):
        r = residuals(model, theta, x, y, mask, bound)
        jacobian = np.empty((*r.shape, k))
        for j in range(k):
            shifted = theta.copy()
            shifted[:, j] += 1e-6
            jacobian[:, :, j] = (residuals(model, shifted, x, y, mask, bound) - r) / 1e-6
        gradient = np.einsum("nfk,nf->nk", jacobian, r)
        hessian = np.einsum("nfj,nfk->njk", jacobian, jacobian)
        diagonal = np.einsum("njj->nj", hessian)
        system = hessian + (damping[:, None] * diagonal + 1e-9)[:, :, None] * np.eye(k)
        step = np.linalg.solve(system, -gradient[..., None])[..., 0]
        candidate = np.clip(theta + step, -20, 20)
        new = (residuals(model, candidate, x, y, mask, bound) ** 2).sum(1)
        better = new < loss
        theta[better], loss[better] = candidate[better], new[better]
        damping = np.where(better, damping * 0.3, damping * 10).clip(1e-7, 1e7)
    return theta, loss


def read(dataset: str, dimension: str, level: str) -> pd.DataFrame:
    filters = [("sex", "==", "total"), ("income_group", "==", "total")] if dataset in ("income_relative", "income_fixed") else None
    frame = pd.read_parquet(SOURCE / dataset / f"{level}.parquet", columns=["code", "period", dimension, "value", "origin"], filters=filters)
    return frame.rename(columns={dimension: "figure"})


def load(level: str) -> pd.DataFrame:
    """One row per unit and year: the published figures (NaN when hidden), in INE's units, and the population."""
    parts = [
        read("income_relative", "income_threshold", level),
        read("income_fixed", "income_threshold_fixed", level),
        read("income_levels", "income_indicator", level).replace({"figure": {"median_per_consumption_unit": "median", "mean_per_consumption_unit": "mean"}}),
        read("income_inequality", "inequality_indicator", level),
    ]
    frame = pd.concat(parts, ignore_index=True)
    frame = frame[frame["figure"].isin(FIGURES) & (frame["origin"] == "published")]
    wide = frame.pivot_table(index=["code", "period"], columns="figure", values="value", aggfunc="first").reindex(columns=FIGURES)
    population = read("income_demographics", "household_indicator", level)
    # ADRH's population, the mixtures' weights (hidden ones shared out by the income pipeline).
    population = population[population["figure"] == "population"].set_index(["code", "period"])["value"]
    wide["population"] = population.reindex(wide.index)
    # Units with a population but no published figure at all still get a (inherited) distribution.
    missing = population.index.difference(wide.index)
    wide = pd.concat([wide, pd.DataFrame({"population": population.reindex(missing)}, index=missing)])
    return wide.sort_index()


def caps(sections: pd.DataFrame) -> dict[tuple[int, str], tuple[float, float]]:
    """INE's top and bottom codes: each year's extreme value of a figure, when many sections share it."""
    out = {}
    for period, frame in sections.groupby(level="period"):
        for figure in FIGURES:
            values = frame[figure].dropna()
            if values.empty:
                continue
            high, low = values.max(), values.min()
            out[(period, figure)] = (high if (values == high).sum() >= 20 else np.inf, low if (values == low).sum() >= 20 else -np.inf)
    return out


def design(frame: pd.DataFrame, medians: dict[int, float], codes: dict) -> tuple[np.ndarray, ...]:
    """Thresholds in euros, figures in the fit's scale, which are published, and which only bound the fit."""
    periods = frame.index.get_level_values("period").to_numpy()
    median = np.array([medians[period] for period in periods])
    x = np.column_stack([np.full(len(frame), value, dtype=float) for value in FIXED.values()] + [median * share for share in RELATIVE.values()])
    raw = frame[FIGURES].to_numpy(dtype=float)
    y = raw.copy()
    above = [FIGURES.index(name) for name in RELATIVE if name.startswith("above")]
    y[:, : len(THRESHOLDS)] /= 100
    y[:, above] = 1 - y[:, above]
    y[:, 9:11] = np.log(y[:, 9:11])
    y[:, 11] /= 100
    y[:, 12] = np.log(y[:, 12])
    mask = np.isfinite(y)
    bound = np.zeros_like(y, dtype=np.int8)
    for j, figure in enumerate(FIGURES):
        high = np.array([codes.get((period, figure), (np.inf, -np.inf))[0] for period in periods])
        low = np.array([codes.get((period, figure), (np.inf, -np.inf))[1] for period in periods])
        # The true value is at least the top code (at most the bottom one); "above" shares flip in the CDF.
        sign = -1 if j in above else 1
        bound[:, j] = np.where(raw[:, j] >= high, sign, np.where(raw[:, j] <= low, -sign, 0))
    return x, np.where(mask, y, 0.0), mask, bound


def national_median(sections: pd.DataFrame, codes: dict, published: dict[int, float], sample: int = 4000) -> dict[int, float]:
    """
    The median the relative thresholds are a share of: the one that fits the sections best, per year
    (golden-section search over a sample of fully published sections). It matches Spain's published
    median where there is one (2021 on), which `meta.json` records; Spain isn't published before.
    """
    rng = np.random.default_rng(0)
    out = {}
    for period, frame in sections.groupby(level="period"):
        full = frame[frame[FIGURES].notna().all(axis=1)]
        full = full.iloc[rng.choice(len(full), min(sample, len(full)), replace=False)]
        guess = float(full["median"].median())

        def loss(median: float) -> float:
            x, y, mask, bound = design(full, {period: median}, codes)
            return float(fit(Dagum, x, y, mask, bound, iterations=40)[1].sum())

        low, high = guess * 0.7, guess * 1.4
        ratio = (np.sqrt(5) - 1) / 2
        c, d = high - ratio * (high - low), low + ratio * (high - low)
        fc, fd = loss(c), loss(d)
        while high - low > 20:
            if fc < fd:
                high, d, fd = d, c, fc
                c = high - ratio * (high - low)
                fc = loss(c)
            else:
                low, c, fc = c, d, fd
                d = low + ratio * (high - low)
                fd = loss(d)
        out[int(period)] = round((low + high) / 2)
        log.info("%d: national median %d (published %s)", period, out[int(period)], published.get(int(period)))
    return out


def fit_level(frame: pd.DataFrame, medians: dict, codes: dict) -> pd.DataFrame:
    """Both models' fits for every unit and year with enough figures, and how far each is from the figures."""
    x, y, mask, bound = design(frame, medians, codes)
    enough = mask.sum(1) >= MIN_FIGURES
    out = pd.DataFrame(index=frame.index)
    out["figures"] = mask.sum(1)
    for model in MODELS.values():
        theta = np.full((len(frame), len(model.params)), np.nan)
        loss = np.full(len(frame), np.nan)
        theta[enough], loss[enough] = fit(model, x[enough], y[enough], mask[enough], bound[enough])
        for j, name in enumerate(model.params):
            out[f"{model.name}_theta{j}"] = theta[:, j]
        out[f"{model.name}_loss"] = loss
    out["origin"] = np.where(enough, "fitted", "unfitted")
    return out


def errors(model, theta: np.ndarray, frame: pd.DataFrame, medians: dict, codes: dict) -> pd.DataFrame:
    """Predicted against published figures, in INE's units, one row per unit, year and figure."""
    x, _, _, bound = design(frame, medians, codes)
    return compare(prediction_frame(predict(model, theta, x)), frame, bound)


def prediction_frame(predicted: np.ndarray) -> np.ndarray:
    """From the fit's scale to INE's units (shares in %, euros, Gini in points)."""
    out = predicted.copy()
    above = [FIGURES.index(name) for name in RELATIVE if name.startswith("above")]
    out[:, above] = 1 - out[:, above]
    out[:, : len(THRESHOLDS)] *= 100
    out[:, 9:11] = np.exp(out[:, 9:11])
    out[:, 11] *= 100
    out[:, 12] = np.exp(out[:, 12])
    return out


def compare(predicted: np.ndarray, frame: pd.DataFrame, bound: np.ndarray) -> pd.DataFrame:
    """Figures at INE's caps are left out: their true value is beyond the cap."""
    published = np.where(bound == 0, frame[FIGURES].to_numpy(dtype=float), np.nan)
    long = pd.DataFrame({
        "code": np.repeat(frame.index.get_level_values("code"), len(FIGURES)),
        "period": np.repeat(frame.index.get_level_values("period"), len(FIGURES)),
        "figure": np.tile(FIGURES, len(frame)),
        "published": published.ravel(),
        "predicted": predicted.ravel(),
    })
    return long.dropna(subset=["published"])


def summary(long: pd.DataFrame) -> dict:
    """Per figure: mean absolute error in points for shares, Gini and P80/P20; in % for euros."""
    out = {}
    for figure, frame in long.groupby("figure", sort=False):
        error = frame["predicted"] - frame["published"]
        if figure in ("median", "mean"):
            error = 100 * error / frame["published"]
        out[figure] = {"mae": round(float(error.abs().mean()), 3), "p90": round(float(error.abs().quantile(0.9)), 3), "bias": round(float(error.mean()), 3), "n": int(len(error))}
    return out


def inherit(sections: pd.DataFrame, fits: dict[str, pd.DataFrame], ccaa: pd.Series) -> pd.DataFrame:
    """Sections without a fit take their district's, else their municipality's… (same year)."""
    out = fits["census_section"].copy()
    columns = [column for column in out.columns if "_theta" in column]
    codes = pd.Series(out.index.get_level_values("code"), index=out.index)
    for level in LEVELS[1:]:
        todo = out[columns[0]].isna()
        if not todo.any():
            break
        parent = parent_codes(codes[todo], level, ccaa)
        keys = pd.MultiIndex.from_arrays([parent.to_numpy(), out.index[todo].get_level_values("period")])
        source = fits[level][columns].reindex(keys).to_numpy()
        out.loc[todo, columns] = source
        out.loc[out.index[todo][np.isfinite(source[:, 0])], "origin"] = "inherited"
    return out


def mixtures(model, sections: pd.DataFrame, fitted: pd.DataFrame, medians: dict, ccaa: pd.Series) -> dict[str, pd.DataFrame]:
    """
    Every level above sections as the population-weighted mixture of its sections' distributions,
    evaluated on a fine grid of incomes: its CDF at the thresholds, quantiles, mean and Gini
    (1 - ∫(1 - F)² dx / mean).
    """
    grid = np.geomspace(50, 3e6, 3000)
    out = {}
    for period in sorted(sections.index.get_level_values("period").unique()):
        frame = fitted.xs(period, level="period", drop_level=False)
        weights = sections.loc[frame.index, "population"].to_numpy(dtype=float)
        theta = frame[[column for column in frame.columns if column.startswith(f"{model.name}_theta")]].to_numpy()
        usable = np.isfinite(theta).all(1) & np.isfinite(weights)
        frame, weights, theta = frame[usable], weights[usable], theta[usable]
        params = model.unpack(theta)
        codes = pd.Series(frame.index.get_level_values("code"), index=frame.index)
        # CDFs in chunks of sections, summed into every level at once through membership matrices.
        members = {}
        for level in LEVELS[1:]:
            parent = parent_codes(codes, level, ccaa)
            units, index = np.unique(parent.to_numpy(), return_inverse=True)
            matrix = sparse.csr_matrix((weights, (index, np.arange(len(frame)))), shape=(len(units), len(frame)))
            members[level] = (units, matrix)
        cdf = {level: np.zeros((len(units), len(grid))) for level, (units, _) in members.items()}
        for start in range(0, len(frame), 4000):
            chunk = slice(start, start + 4000)
            values = model.cdf(grid[None, :], *[param[chunk, None] for param in params])
            for level, (_, matrix) in members.items():
                cdf[level] += matrix[:, chunk] @ values
        means = np.exp(model.log_mean(*params))
        thresholds = np.array([*FIXED.values(), *(medians[period] * share for share in RELATIVE.values())])
        for level, (units, matrix) in members.items():
            total = np.asarray(matrix.sum(1)).ravel()
            f = cdf[level] / total[:, None]
            mean = (matrix @ means) / total
            # ∫(1 - F)² dx on a log grid (dx = x dlog x); below the grid's start, 1 - F ≈ 1.
            tail = np.trapezoid((1 - f) ** 2 * grid, np.log(grid), axis=1) + grid[0]
            gini = 1 - tail / mean
            quantile = lambda u: np.array([np.interp(u, row, grid) for row in f])
            at = np.array([np.interp(thresholds, grid, row) for row in f])
            above = [FIGURES.index(name) for name in RELATIVE if name.startswith("above")]
            at[:, above] = 1 - at[:, above]
            predicted = np.column_stack([at * 100, quantile(0.5), mean, gini * 100, quantile(0.8) / quantile(0.2)])
            out.setdefault(level, []).append(pd.DataFrame(predicted, columns=FIGURES, index=pd.MultiIndex.from_arrays([units, np.full(len(units), period)], names=["code", "period"])))
    return {level: pd.concat(parts) for level, parts in out.items()}


def holdout(sections: pd.DataFrame, medians: dict, codes: dict, size: int) -> dict:
    """Out of sample: each figure in turn left out of the fit of fully published sections, then predicted."""
    rng = np.random.default_rng(1)
    full = sections[sections[FIGURES].notna().all(axis=1)]
    full = full.iloc[rng.choice(len(full), min(size, len(full)), replace=False)]
    x, y, mask, bound = design(full, medians, codes)
    out = {}
    for model in MODELS.values():
        out[model.name] = {}
        for j, figure in enumerate(FIGURES):
            hidden = mask.copy()
            hidden[:, j] = False
            theta, _ = fit(model, x, y, hidden, bound)
            predicted = prediction_frame(predict(model, theta, x))[:, j]
            published = full[figure].to_numpy(dtype=float)
            error = predicted - published
            if figure in ("median", "mean"):
                error = 100 * error / published
            # Censored figures aren't a fair target: their true value is beyond the cap.
            error = error[bound[:, j] == 0]
            # Without some figures a few fits run off (a P80/P20 without its bottom quantile): counted apart.
            finite = np.isfinite(error)
            out[model.name][figure] = {"mae": round(float(np.abs(error[finite]).mean()), 3), "p90": round(float(np.quantile(np.abs(error[finite]), 0.9)), 3), "degenerate": int((~finite).sum())}
        log.info("Holdout %s: %s", model.name, {figure: value["mae"] for figure, value in out[model.name].items()})
    return out


def main(holdout_size: int) -> None:
    ccaa = ccaa_by_province()
    data = {level: load(level) for level in LEVELS}
    codes = caps(data["census_section"])
    country = data["country"]["median"].dropna()
    published = {int(period): float(value) for (_, period), value in country.items()}
    medians = national_median(data["census_section"], codes, published)

    fits, metrics = {}, {"in_sample": {}, "mixture": {}, "direct": {}}
    for level in LEVELS:
        fits[level] = fit_level(data[level], medians, codes)
        log.info("%s: %d units fitted, %d not", level, (fits[level]["origin"] == "fitted").sum(), (fits[level]["origin"] == "unfitted").sum())
    fits["census_section"] = inherit(data["census_section"], fits, ccaa)

    for model in MODELS.values():
        columns = [f"{model.name}_theta{j}" for j in range(len(model.params))]
        fitted = fits["census_section"][fits["census_section"]["origin"] == "fitted"]
        metrics["in_sample"][model.name] = summary(errors(model, fitted[columns].to_numpy(), data["census_section"].loc[fitted.index], medians, codes))
        metrics["direct"][model.name] = {}
        for level in LEVELS[1:]:
            direct = fits[level][fits[level]["origin"] == "fitted"]
            metrics["direct"][model.name][level] = summary(errors(model, direct[columns].to_numpy(), data[level].loc[direct.index], medians, codes))
        mixed = mixtures(model, data["census_section"], fits["census_section"], medians, ccaa)
        metrics["mixture"][model.name] = {}
        validation = []
        for level, predicted in mixed.items():
            figures = data[level].reindex(predicted.index)
            long = compare(predicted[FIGURES].to_numpy(), figures, design(figures, medians, codes)[3])
            metrics["mixture"][model.name][level] = summary(long)
            validation.append(long.assign(level=level, model=model.name))
        if model is Dagum:
            pd.concat(validation, ignore_index=True).to_parquet(output_dir(PIPELINE) / "mixture_validation.parquet", index=False)
    metrics["holdout"] = holdout(data["census_section"], medians, codes, holdout_size) if holdout_size else None

    out = output_dir(PIPELINE)
    rows = []
    for level, frame in fits.items():
        frame = frame.reset_index()
        frame.insert(0, "level", level)
        frame.insert(1, "entity_id", COUNTRY_ID if level == "country" else ID_PREFIX[level] + frame["code"])
        for model in MODELS.values():
            params = model.unpack(frame[[f"{model.name}_theta{j}" for j in range(len(model.params))]].to_numpy())
            for name, values in zip(model.params, params):
                frame[f"{model.name}_{name}"] = values
        rows.append(frame.drop(columns=[column for column in frame.columns if "_theta" in column]))
    table = pd.concat(rows, ignore_index=True)
    table["population"] = pd.concat([data[level]["population"] for level in LEVELS]).to_numpy()
    table.to_parquet(out / "fits.parquet", index=False)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "processed/income (INE ADRH, operation 353)",
        "national_median": {"estimated": medians, "published": published},
        "caps": {f"{period}:{figure}": [value for value in pair if np.isfinite(value)] for (period, figure), pair in codes.items() if np.isfinite(pair).any()},
        "units": {level: {origin: int(count) for origin, count in fits[level]["origin"].value_counts().items()} for level in LEVELS},
        "metrics": metrics,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    log.info("Wrote %s", out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fits the income distribution of every census section (and level up) to INE's ADRH figures.")
    parser.add_argument("--holdout", type=int, default=5000, help="sections in the leave-one-figure-out test (0 to skip)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main(args.holdout)
