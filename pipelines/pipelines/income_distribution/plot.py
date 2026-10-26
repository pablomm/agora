"""
Draws one unit's fitted income distribution against what INE publishes for it: the CDF with the
published points, the density, and a table of published and fitted figures. Above sections, the
mixture of its sections' distributions is drawn too.

    python pipelines/income_distribution/plot.py 2807901001 2023 [--out file.png]
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from fit import FIGURES, FIXED, MODELS, RELATIVE, THRESHOLDS, Dagum, caps, design, load, prediction_frame, predict  # noqa: E402

from common.paths import DATA_DIR, output_dir  # noqa: E402

LEVEL_BY_LENGTH = {10: "census_section", 7: "census_district", 5: "municipality", 2: "province"}
INK, MUTED, GRID = "#1f2328", "#656d76", "#e6e8eb"
COLORS = {"dagum": "#2563eb", "lognormal": "#9ca3af", "mixture": "#d97706"}
LABELS = {"dagum": "Dagum", "lognormal": "Lognormal", "mixture": "Mezcla de secciones"}
NAMES = {
    "below_5000": "< 5.000 €", "below_7500": "< 7.500 €", "below_10000": "< 10.000 €",
    "below_40": "< 40 % mediana", "below_50": "< 50 % mediana", "below_60": "< 60 % mediana",
    "above_140": "> 140 % mediana", "above_160": "> 160 % mediana", "above_200": "> 200 % mediana",
    "median": "Mediana (€)", "mean": "Media (€)", "gini": "Gini", "p80_p20": "P80/P20",
}


def params(row: pd.Series, model) -> list[float]:
    return [float(row[f"{model.name}_{name}"]) for name in model.params]


def theta(row: pd.Series, model) -> np.ndarray:
    """The fit's parameters (what `predict` takes) from the natural ones in `fits.parquet`."""
    return model.pack(*(np.array([value]) for value in params(row, model)))


def main(code: str, period: int, out: Path) -> None:
    level = LEVEL_BY_LENGTH.get(len(code), "autonomous_community")
    fits = pd.read_parquet(output_dir("income_distribution") / "fits.parquet")
    meta = json.loads((output_dir("income_distribution") / "meta.json").read_text())
    median = meta["national_median"]["estimated"][str(period)]
    row = fits[(fits["level"] == level) & (fits["code"] == code) & (fits["period"] == period)].iloc[0]
    frame = load(level)
    published = frame.loc[(code, period)]
    # Which published figures are at INE's cap (top or bottom code), as the fit treats them.
    capped = design(frame.loc[[(code, period)]], {period: median}, caps(load("census_section")))[3][0] != 0
    thresholds = np.array([*FIXED.values(), *(median * share for share in RELATIVE.values())])

    grid = np.geomspace(500, 400_000, 1500)
    curves = {name: (model.cdf(grid, *params(row, model)), model.pdf(grid, *params(row, model))) for name, model in MODELS.items()}
    figures = {name: prediction_frame(predict(model, theta(row, model), thresholds[None, :]))[0] for name, model in MODELS.items()}

    if level != "census_section":
        sections = fits[(fits["level"] == "census_section") & (fits["period"] == period) & fits["code"].str.startswith(code)]
        sections = sections.dropna(subset=["dagum_a", "population"])
        weights = sections["population"].to_numpy() / sections["population"].sum()
        a, b, p = (sections[f"dagum_{name}"].to_numpy()[:, None] for name in Dagum.params)
        curves["mixture"] = (weights @ Dagum.cdf(grid, a, b, p), weights @ Dagum.pdf(grid, a, b, p))
        validation = pd.read_parquet(output_dir("income_distribution") / "mixture_validation.parquet")
        validation = validation[(validation["code"] == code) & (validation["period"] == period) & (validation["level"] == level)]
        figures["mixture"] = validation.set_index("figure")["predicted"].reindex(FIGURES).to_numpy()

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK})
    figure = plt.figure(figsize=(14, 8.5))
    grid_spec = figure.add_gridspec(2, 2, width_ratios=[1.35, 1], hspace=0.32, wspace=0.18)
    cdf_axis, pdf_axis, table_axis = figure.add_subplot(grid_spec[0, 0]), figure.add_subplot(grid_spec[1, 0]), figure.add_subplot(grid_spec[:, 1])
    order = [name for name in ("lognormal", "mixture", "dagum") if name in curves]
    limit = float(np.interp(0.98, curves["dagum"][0], grid))
    for name in order:
        style = {"color": COLORS[name], "lw": 2, "ls": "--" if name == "lognormal" else "-", "label": LABELS[name]}
        cdf_axis.plot(grid, curves[name][0] * 100, **style)
        pdf_axis.plot(grid, curves[name][1] * 1000 * 100, **style)
    # Published points of the CDF ("above" shares as 100 - share); hollow when hidden.
    for j, figure_name in enumerate(THRESHOLDS):
        value = published[figure_name]
        if pd.isna(value):
            continue
        y = 100 - value if figure_name.startswith("above") else value
        cdf_axis.plot(thresholds[j], y, "o", ms=8, color="white" if capped[j] else INK, mec=INK, mew=1.5, zorder=5)
    cdf_axis.plot([], [], "o", ms=8, color=INK, mec="white", label="Publicado por el INE")
    if capped[: len(THRESHOLDS)].any():
        cdf_axis.plot([], [], "o", ms=8, color="white", mec=INK, mew=1.5, label="En el tope del INE")
    # The Dagum density can rise towards 0 €: scaled to the body of the distribution.
    pdf_axis.set_ylim(0, max(curves[name][1][grid > 2000].max() for name in order) * 1000 * 100 * 1.12)
    for axis in (cdf_axis, pdf_axis):
        axis.set_xlim(0, limit)
        axis.grid(color=GRID, lw=0.8)
        axis.spines[["top", "right"]].set_visible(False)
        axis.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k €"))
    for axis in (cdf_axis, pdf_axis):
        top = axis.get_ylim()[1] if axis is pdf_axis else 100
        for value, label, style, align in ((published["median"], "mediana", "-", "right"), (published["mean"], "media", ":", "left")):
            if pd.notna(value):
                axis.axvline(value, color=MUTED, lw=1, ls=style)
                axis.text(value, top, f" {label} ", color=MUTED, fontsize=8, va="top", ha=align)
    cdf_axis.set_ylabel("% de la población con menos renta")
    cdf_axis.set_ylim(0, 100)
    pdf_axis.set_ylabel("% de la población por cada 1.000 €")
    pdf_axis.set_xlabel("renta neta por unidad de consumo")
    cdf_axis.legend(frameon=False, loc="lower right")

    rows = [[NAMES[name], ("tope " if capped[j] else "") + _format(name, published[name]), *(_format(name, figures[model][j]) for model in order[::-1])] for j, name in enumerate(FIGURES)]
    table_axis.axis("off")
    table = table_axis.table(cellText=rows, colLabels=["", "INE", *(LABELS[name].split(" ")[0] for name in order[::-1])], loc="upper center", cellLoc="right", colLoc="right")
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.6)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.visible_edges = "B"
        if r == 0:
            cell.set_text_props(color=MUTED, weight="bold")
        if c == 0:
            cell.set_text_props(ha="left", color=MUTED)
            cell._loc = "left"
    loss = row["dagum_loss"]
    table_axis.text(0, 0.02, f"Pérdida de la Dagum: {loss:.1f} ({int(row['figures'])} cifras publicadas)\nMediana de España usada para los umbrales: {median:,.0f} €".replace(",", "."), color=MUTED, fontsize=9, transform=table_axis.transAxes)
    figure.suptitle(f"{_name(level, code)} · {period}", x=0.06, ha="left", fontsize=14, weight="bold")
    figure.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(out)


def _format(name: str, value: float) -> str:
    if pd.isna(value):
        return "oculto"
    if name in ("median", "mean"):
        return f"{value:,.0f}".replace(",", ".")
    if name == "p80_p20":
        return f"{value:.2f}".replace(".", ",")
    return f"{value:.1f}".replace(".", ",")


def _name(level: str, code: str) -> str:
    path = DATA_DIR / "processed/municipalities/municipalities.parquet"
    names = pd.read_parquet(path, columns=["ine_code", "name"]).set_index("ine_code")["name"] if path.exists() else pd.Series(dtype=str)
    label = {"census_section": "sección", "census_district": "distrito", "municipality": "", "province": "provincia"}.get(level, "")
    place = names.get(code[:5], code) if len(code) >= 5 else code
    suffix = {"census_section": f"distrito {code[5:7]}, sección {code[7:]}", "census_district": f"distrito {code[5:7]}"}.get(level, label)
    return f"{place}, {suffix}" if suffix else place


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plots a unit's fitted income distribution against INE's figures.")
    parser.add_argument("code", help="INE code: section (10 digits), district (7), municipality (5) or province (2)")
    parser.add_argument("period", type=int)
    parser.add_argument("--out", type=Path, help="PNG to write (default: income_distribution_<code>_<period>.png here)")
    args = parser.parse_args()
    main(args.code, args.period, args.out or Path(f"income_distribution_{args.code}_{args.period}.png"))
