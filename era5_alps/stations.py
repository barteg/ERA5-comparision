"""Station selection: Alpine domain, regimes, and removal of duplicated data."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import requests

from . import config, ecad

EARTH_KM = 6371.0
SOUID_KEY = 100_000
REGIMES = ["Lowland", "Coastal", "Valley / foothill", "Mountain"]


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def load_lines(url: str, name: str) -> list[np.ndarray]:
    """Natural Earth line features near the domain as (lon, lat) arrays (cached)."""
    path = config.DATA_DIR / name
    if not path.exists():
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    lines = []
    for feat in json.loads(path.read_text())["features"]:
        geom = feat["geometry"]
        parts = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
        for part in parts:
            xy = np.asarray(part, float)[:, :2]
            near = (
                (xy[:, 0] > config.LON_MIN - 3) & (xy[:, 0] < config.LON_MAX + 3)
                & (xy[:, 1] > config.LAT_MIN - 3) & (xy[:, 1] < config.LAT_MAX + 3)
            )
            if near.any():
                lines.append(xy)
    return lines


def load_exchanged_stations() -> pd.DataFrame:
    """NOAA ISD stations active in the study period, near the domain.

    ISD is built from the SYNOP/METAR reports exchanged internationally, i.e.
    the same observation stream reanalyses assimilate.
    """
    path = config.DATA_DIR / "isd-history.csv"
    if not path.exists():
        r = requests.get(config.ISD_HISTORY_URL, timeout=120)
        r.raise_for_status()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    isd = pd.read_csv(path, dtype=str)
    isd["lat"], isd["lon"] = pd.to_numeric(isd["LAT"], errors="coerce"), pd.to_numeric(isd["LON"], errors="coerce")
    begin, end = pd.to_datetime(isd["BEGIN"], format="%Y%m%d"), pd.to_datetime(isd["END"], format="%Y%m%d")
    keep = (
        isd["lat"].between(config.LAT_MIN - 0.5, config.LAT_MAX + 0.5)
        & isd["lon"].between(config.LON_MIN - 0.5, config.LON_MAX + 0.5)
        & (begin <= config.END) & (end >= config.START)
    )
    return isd.loc[keep, ["STATION NAME", "lat", "lon"]].reset_index(drop=True)


def exchanged_distance_km(lat, lon) -> np.ndarray:
    """Distance from each point to the nearest internationally exchanged station."""
    isd = load_exchanged_stations()
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    d = haversine_km(lat[:, None], lon[:, None], isd["lat"].to_numpy()[None], isd["lon"].to_numpy()[None])
    return d.min(axis=1)


def coast_distance_km(lat, lon) -> np.ndarray:
    """Distance from each point to the nearest sea coastline segment."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    best = np.full(lat.shape, np.inf)
    kx = EARTH_KM * np.radians(1.0) * np.cos(np.radians(lat))  # km per degree lon
    ky = EARTH_KM * np.radians(1.0)
    for xy in load_lines(config.COASTLINE_URL, "ne_50m_coastline.geojson"):
        a, b = xy[:-1], xy[1:]
        # Local flat-earth projection centred on each station.
        ax = (a[:, 0][None] - lon[:, None]) * kx[:, None]
        ay = (a[:, 1][None] - lat[:, None]) * ky
        dx = (b[:, 0] - a[:, 0])[None] * kx[:, None]
        dy = (b[:, 1] - a[:, 1])[None] * ky
        t = np.clip(-(ax * dx + ay * dy) / np.maximum(dx**2 + dy**2, 1e-12), 0, 1)
        best = np.minimum(best, np.hypot(ax + t * dx, ay + t * dy).min(axis=1))
    return best


def classify(elev_m, coast_km) -> np.ndarray:
    elev_m, coast_km = np.asarray(elev_m), np.asarray(coast_km)
    return np.select(
        [elev_m >= config.MOUNTAIN_ELEV_M, elev_m >= 300, coast_km <= config.COAST_KM],
        ["Mountain", "Valley / foothill", "Coastal"],
        default="Lowland",
    )


def select(archive: ecad.RemoteArchive) -> tuple[pd.DataFrame, dict[int, pd.Series]]:
    """Pick stations for the study and return their observed daily series.

    Duplicate data are excluded at three levels:

    1. Blended gap-filling: only values measured at the station's own site are
       used (source series located within DUPLICATE_RADIUS_KM / DUPLICATE_DZ_M
       of the station), never values borrowed from a neighbouring station.
    2. Shared sources: a source series (SOUID) counts for one station only.
    3. Co-located stations: a station next to an already accepted one is skipped.
    """
    st = ecad.load_stations(archive)
    st = st[
        st["lat"].between(config.LAT_MIN, config.LAT_MAX)
        & st["lon"].between(config.LON_MIN, config.LON_MAX)
        & st["elev_m"].notna()
    ].copy()

    src = ecad.load_sources(archive).merge(st, on="staid", suffixes=("_src", ""))
    src["own"] = (
        haversine_km(src["lat"], src["lon"], src["lat_src"], src["lon_src"]) <= config.DUPLICATE_RADIUS_KM
    ) & ((src["elev_m"] - src["elev_m_src"]).abs() <= config.DUPLICATE_DZ_M)
    # Source ids in the station files and in sources.txt differ in their leading
    # digit (e.g. 119155 vs 219155), so they are matched on the last five digits
    # within a station. If that is ambiguous, every match must be the station's own.
    src["key"] = src["souid"] % SOUID_KEY
    by_key = src.groupby(["staid", "key"]).agg(own=("own", "all"), souids=("souid", set))
    # Cheap pre-filter before downloading: the station's own sources must reach
    # both ends of the period (actual coverage is checked on the data below).
    own = src[src["own"]].groupby("staid").agg(start=("start", "min"), stop=("stop", "max"))
    own = own[(own["start"] <= config.START) & (own["stop"] >= config.END)]
    st = st[st["staid"].isin(own.index)].copy()

    # Independence from ERA5. ERA5's surface analysis ingests 2 m temperature
    # from stations exchanged on the WMO network. A station counts as exchanged if
    # ECA&D lists a SYNOP-derived series for it (source ids 9xxxxx, at any
    # location) or a NOAA ISD station lies within INDEPENDENCE_RADIUS_KM.
    synop_ids = set(src.loc[src["souid"] >= 900_000, "staid"])
    st["synop"] = st["staid"].isin(synop_ids)
    st["exchanged_km"] = exchanged_distance_km(st["lat"], st["lon"])
    st["independent"] = ~st["synop"] & (st["exchanged_km"] > config.INDEPENDENCE_RADIUS_KM)
    print(
        f"  {len(st)} stations with data; {int(st['synop'].sum())} have a SYNOP series, "
        f"{int((st['exchanged_km'] <= config.INDEPENDENCE_RADIUS_KM).sum())} are within "
        f"{config.INDEPENDENCE_RADIUS_KM:g} km of an exchanged station, {int(st['independent'].sum())} are independent"
    )
    if config.REQUIRE_INDEPENDENT:
        st = st[st["independent"]].copy()

    st["coast_km"] = coast_distance_km(st["lat"], st["lon"])
    st["regime"] = classify(st["elev_m"], st["coast_km"])
    print(f"  {len(st)} candidate stations in the domain: {st['regime'].value_counts().to_dict()}")

    rng = np.random.default_rng(0)
    queues = {r: list(rng.permutation(st.loc[st["regime"] == r, "staid"].to_numpy())) for r in REGIMES}
    quota = config.MAX_STATIONS // len(REGIMES)
    n_days = len(pd.date_range(config.START, config.END))
    meta = st.set_index("staid")

    chosen: list[int] = []
    series: dict[int, pd.Series] = {}
    claimed: set[int] = set()
    counts = dict.fromkeys(REGIMES, 0)
    rejected = {"coverage": 0, "shared source": 0, "co-located": 0}

    for regime in REGIMES:
        while counts[regime] < quota and queues[regime]:
            sid = int(queues[regime].pop())
            row = meta.loc[sid]
            if chosen:
                acc = meta.loc[chosen]
                near = (haversine_km(row["lat"], row["lon"], acc["lat"], acc["lon"]) <= config.DUPLICATE_RADIUS_KM) & (
                    (acc["elev_m"] - row["elev_m"]).abs() <= config.DUPLICATE_DZ_M
                )
                if near.any():
                    rejected["co-located"] += 1
                    continue
            df = ecad.load_series(archive, sid)
            info = by_key.loc[sid].reindex(df["souid"].to_numpy() % SOUID_KEY)
            df = df[info["own"].fillna(False).to_numpy(bool)]
            used = set().union(*by_key.loc[sid].loc[np.unique(df["souid"].to_numpy() % SOUID_KEY), "souids"]) if len(df) else set()
            if used & claimed:
                rejected["shared source"] += 1
                continue
            if len(df) < config.MIN_COVERAGE * n_days:
                rejected["coverage"] += 1
                continue
            claimed |= used
            chosen.append(sid)
            series[sid] = df["tg"]
            counts[regime] += 1

    print(f"  selected {len(chosen)} stations {counts}; rejected {rejected}")
    out = meta.loc[chosen].reset_index()
    out["n_obs"] = [len(series[s]) for s in chosen]
    return out, series
