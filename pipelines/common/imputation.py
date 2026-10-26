"""Imputing figures a source hides, so that the parts still add up to what it publishes."""

import numpy as np
import pandas as pd


def share_out(residual: pd.DataFrame, hidden: pd.DataFrame, weights: pd.Series, parent: str, dimensions: list[str], by: str = "sex") -> pd.Series:
    """
    Integers for the hidden units' cells: each parent's residual (per period and dimensions) split
    among its hidden units by weight (equal shares where there's no weight), largest remainder.
    `residual` has parent, period, the dimensions and residual; `hidden` the hidden cells (code,
    parent, period, dimensions); `weights` is indexed by code, period and `by` (a weight for each
    unit and sex, say). Returns values indexed like `hidden`.
    """
    keys = [parent, "period", *dimensions]
    frame = hidden.merge(residual, on=keys, how="left")
    frame["residual"] = frame["residual"].fillna(0).clip(lower=0)
    frame["weight"] = weights.reindex(pd.MultiIndex.from_frame(frame[["code", "period", by]])).fillna(0).to_numpy()
    totals = frame.groupby(keys)["weight"].transform("sum")
    count = frame.groupby(keys)["weight"].transform("size")
    share = np.where(totals > 0, frame["weight"] / totals.where(totals > 0, 1), 1 / count)
    exact = frame["residual"] * share
    floor = np.floor(exact)
    frame["value"] = floor
    frame["remainder"] = exact - floor
    left = (frame["residual"] - frame.groupby(keys)["value"].transform("sum")).round().astype(int)
    # The units with the largest remainders get one more until the residual is used up.
    frame["rank"] = frame.groupby(keys)["remainder"].rank(method="first", ascending=False)
    frame["value"] += (frame["rank"] <= left).astype(float)
    return frame.set_index(hidden.index)["value"]
