"""ERA5 / ERA5-Land daily mean 2 m temperature on the native model grid.

Data come from the Open-Meteo archive API, which serves ERA5 and ERA5-Land
without an account. Two things matter for a fair comparison:

* ``elevation=nan`` switches off Open-Meteo's own downscaling, so we get the raw
  grid-cell value together with the model's grid-cell height.
* Many stations fall in the same grid cell. Requests are made per *unique grid
  cell*, never per station, and every cell is cached on disk, so no reanalysis
  series is downloaded or stored twice.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import requests

from . import config

BATCH = 5  # grid cells per HTTP request


def snap(values, step: float) -> np.ndarray:
    """Coordinates of the nearest grid-cell centre on a regular grid."""
    return np.round(np.round(np.asarray(values, float) / step) * step, 4)


def cell_id(lat: float, lon: float) -> str:
    return f"{lat:.2f}_{lon:.2f}"


def _paths(product: str):
    stem = product.lower().replace("-", "_")
    return (
        config.DATA_DIR / f"{stem}_daily.parquet",
        config.DATA_DIR / f"{stem}_cells.parquet",
    )


def _request(model: str, lats, lons) -> list[dict]:
    params = {
        "latitude": ",".join(f"{v:.2f}" for v in lats),
        "longitude": ",".join(f"{v:.2f}" for v in lons),
        "elevation": ",".join(["nan"] * len(lats)),
        "start_date": config.START,
        "end_date": config.END,
        "daily": "temperature_2m_mean",
        "timezone": "GMT",
        "models": model,
    }
    failures = 0
    while True:
        try:
            r = requests.get(config.OPEN_METEO_URL, params=params, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as exc:
            failures += 1
            if failures > 5:
                raise
            print(f"    network error ({type(exc).__name__}); retry {failures}/5", flush=True)
            time.sleep(10 * failures)
            continue
        if r.status_code == 429:
            reason = r.json().get("reason", "")
            if "aily" in reason:
                raise RuntimeError(
                    f"Open-Meteo daily quota reached ({reason}). Cells fetched so far "
                    "are cached; rerun tomorrow to continue where this stopped."
                )
            wait = 3600 if "ourly" in reason else 61
            print(f"    rate limited ({reason.strip()}); waiting {wait} s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        out = r.json()
        return out if isinstance(out, list) else [out]


def fetch(product: str, lats, lons) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily means for the grid cells containing the given points.

    Returns ``(daily, cells)``: ``daily`` is indexed by date with one column per
    cell id; ``cells`` is indexed by cell id with the cell centre and model
    height. Only cells missing from the cache are requested.
    """
    model, step = config.PRODUCTS[product]
    daily_path, cells_path = _paths(product)
    wanted = pd.DataFrame({"lat": snap(lats, step), "lon": snap(lons, step)}).drop_duplicates()
    wanted.index = [cell_id(a, b) for a, b in zip(wanted["lat"], wanted["lon"])]

    if daily_path.exists():
        daily, cells = pd.read_parquet(daily_path), pd.read_parquet(cells_path)
        # A cache built for a different period cannot be extended; start over.
        if str(daily.index[0].date()) != config.START or str(daily.index[-1].date()) != config.END:
            daily, cells = pd.DataFrame(), pd.DataFrame()
    else:
        daily, cells = pd.DataFrame(), pd.DataFrame()

    todo = wanted.loc[~wanted.index.isin(daily.columns)]
    print(
        f"  {product}: {len(wanted)} unique grid cells needed, "
        f"{len(wanted) - len(todo)} cached, {len(todo)} to download",
        flush=True,
    )
    for i in range(0, len(todo), BATCH):
        part = todo.iloc[i : i + BATCH]
        new_cols, new_cells = {}, {}
        for cid, loc in zip(part.index, _request(model, part["lat"], part["lon"])):
            if max(abs(loc["latitude"] - part.at[cid, "lat"]), abs(loc["longitude"] - part.at[cid, "lon"])) > step / 2:
                raise RuntimeError(f"{product}: asked for cell {cid}, got {loc['latitude']},{loc['longitude']}")
            idx = pd.to_datetime(loc["daily"]["time"]).rename("date")
            new_cols[cid] = pd.Series(loc["daily"]["temperature_2m_mean"], index=idx, dtype="float32")
            new_cells[cid] = {"lat": part.at[cid, "lat"], "lon": part.at[cid, "lon"], "model_elev_m": loc["elevation"]}
        daily = pd.concat([daily, pd.DataFrame(new_cols)], axis=1)
        cells = pd.concat([cells, pd.DataFrame.from_dict(new_cells, orient="index")])
        assert not daily.columns.duplicated().any()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        daily.to_parquet(daily_path)  # save after every batch: reruns resume here
        cells.to_parquet(cells_path)
        print(f"    {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
    return daily[wanted.index], cells.loc[wanted.index]
