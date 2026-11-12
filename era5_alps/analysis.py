"""Matching, elevation correction and verification metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, reanalysis

SEASONS = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
SEASON_ORDER = ["DJF", "MAM", "JJA", "SON"]


def build_pairs(stations: pd.DataFrame, obs: dict[int, pd.Series], product: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match each station to its grid cell and calendar day.

    Returns ``(pairs, stations)``. ``pairs`` has one row per station-day with
    the observation, the raw model value and the lapse-rate corrected value.
    ``stations`` gains the model height and elevation difference for ``product``.
    """
    _, step = config.PRODUCTS[product]
    daily, cells = reanalysis.fetch(product, stations["lat"], stations["lon"])
    lat, lon = reanalysis.snap(stations["lat"], step), reanalysis.snap(stations["lon"], step)
    ids = [reanalysis.cell_id(a, b) for a, b in zip(lat, lon)]

    stations = stations.copy()
    stations["cell"] = ids
    stations["model_elev_m"] = cells.loc[ids, "model_elev_m"].to_numpy()
    # dz > 0: the model surface is above the real station.
    stations["dz_m"] = stations["model_elev_m"] - stations["elev_m"]

    frames = []
    for row in stations.itertuples():
        df = pd.concat([obs[row.staid].rename("obs"), daily[row.cell].rename("raw")], axis=1, join="inner").dropna()
        if df.empty:  # e.g. ERA5-Land has no data in sea cells
            continue
        # Bring the model value down/up to the station height.
        df["corrected"] = df["raw"] - config.LAPSE_RATE * row.dz_m
        df.insert(0, "staid", row.staid)
        frames.append(df.reset_index())
    pairs = pd.concat(frames, ignore_index=True)
    assert not pairs.duplicated(["staid", "date"]).any(), "duplicate station-days"
    pairs["product"] = product
    return pairs, stations


def metrics(df: pd.DataFrame, col: str) -> pd.Series:
    """MBE, RMSE and Pearson r of model column ``col`` against ``obs``."""
    err = df[col] - df["obs"]
    return pd.Series(
        {
            "n": len(df),
            "MBE": err.mean(),
            "RMSE": np.sqrt((err**2).mean()),
            "r": np.corrcoef(df[col], df["obs"])[0, 1] if len(df) > 2 else np.nan,
        }
    )


def anomaly_r(df: pd.DataFrame, col: str) -> float:
    """Correlation after removing each station's monthly means.

    Plain r is inflated by the shared seasonal cycle; this isolates agreement on
    day-to-day (synoptic) variability.
    """
    key = [df["staid"], df["date"].dt.year, df["date"].dt.month]
    a = df[col] - df.groupby(key)[col].transform("mean")
    b = df["obs"] - df.groupby(key)["obs"].transform("mean")
    return float(np.corrcoef(a, b)[0, 1])


def table(pairs: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Metrics for raw and corrected values, grouped by ``by`` (+ product)."""
    rows = []
    cols = ["product", *by]
    for keys, grp in pairs.groupby(cols if by else "product", sort=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        for version in ("raw", "corrected"):
            m = metrics(grp, version)
            m["r_anom"] = anomaly_r(grp, version)
            rows.append(dict(zip(cols, keys)) | {"version": version} | m.to_dict())
    out = pd.DataFrame(rows)
    out["n"] = out["n"].astype(int)
    return out


def station_table(pairs: pd.DataFrame, stations: dict[str, pd.DataFrame]) -> pd.DataFrame:
    out = table(pairs, ["staid"])
    info = pd.concat([s.assign(product=p) for p, s in stations.items()])
    cols = ["product", "staid", "name", "country", "lat", "lon", "elev_m", "regime", "independent", "exchanged_km", "cell", "model_elev_m", "dz_m"]
    return out.merge(info[cols], on=["product", "staid"])


def empirical_lapse_rates(pairs: pd.DataFrame, per_station: pd.DataFrame) -> pd.DataFrame:
    """Lapse rate implied by the data: slope of raw station bias against dz.

    If the standard -6.5 degC/km held, raw bias = -6.5e-3 * dz exactly.
    """
    dz = per_station.drop_duplicates(["product", "staid"]).set_index(["product", "staid"])["dz_m"]
    df = pairs.assign(season=pairs["date"].dt.month.map(SEASONS), err=pairs["raw"] - pairs["obs"])
    rows = []
    for product, grp in df.groupby("product", sort=False):
        for season, sub in [("All year", grp)] + [(s, grp[grp["season"] == s]) for s in SEASON_ORDER]:
            bias = sub.groupby("staid")["err"].mean()
            x = dz.loc[product].reindex(bias.index).to_numpy()
            slope, intercept = np.polyfit(x, bias.to_numpy(), 1)
            rows.append(
                {
                    "product": product,
                    "season": season,
                    "lapse_rate_C_per_km": slope * 1000,
                    "intercept_C": intercept,
                    "r": np.corrcoef(x, bias)[0, 1],
                    "n_stations": len(bias),
                }
            )
    return pd.DataFrame(rows)
