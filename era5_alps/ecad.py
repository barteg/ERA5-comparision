"""ECA&D daily mean temperature (TG) access.

The blended ECA&D archive is a single ~0.9 GB zip. Instead of downloading it,
we read the zip's central directory over HTTP range requests and pull out only
the members we need (the station list plus one small text file per selected
station). Everything fetched is cached, so nothing is downloaded twice.
"""
from __future__ import annotations

import io
import struct
import zipfile
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import config


class HTTPRangeFile(io.RawIOBase):
    """Read-only seekable file backed by HTTP range requests."""

    def __init__(self, url: str, session: requests.Session | None = None):
        self.url = url
        self.session = session or requests.Session()
        head = self.session.head(url, timeout=60)
        head.raise_for_status()
        if head.headers.get("Accept-Ranges", "").lower() != "bytes":
            raise OSError(f"{url} does not support range requests")
        self.size = int(head.headers["Content-Length"])
        self.pos = 0
        self.bytes_fetched = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.size + offset
        return self.pos

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        headers = {"Range": f"bytes={self.pos}-{self.pos + n - 1}"}
        r = self.session.get(self.url, headers=headers, timeout=120)
        r.raise_for_status()
        data = r.content
        buf[: len(data)] = data
        self.pos += len(data)
        self.bytes_fetched += len(data)
        return len(data)


class RemoteArchive:
    """Lazily opened remote ECA&D zip; only opened if a cache miss occurs."""

    def __init__(self, url: str = config.ECAD_ZIP_URL):
        self.url = url
        self._zip = None
        self._raw = None

    @property
    def zip(self) -> zipfile.ZipFile:
        if self._zip is None:
            self._raw = HTTPRangeFile(self.url)
            # A large buffer makes the central-directory read a handful of requests.
            self._zip = zipfile.ZipFile(io.BufferedReader(self._raw, buffer_size=4 << 20))
        return self._zip

    def read_text(self, member: str) -> str:
        """Fetch and inflate one member with a single exact range request."""
        info = self.zip.getinfo(member)
        if info.compress_type != zipfile.ZIP_DEFLATED:
            return self.zip.read(member).decode("latin-1")
        # Local header: 30 fixed bytes + file name + extra field (length only
        # known from the header itself, so over-read a little).
        slack = 30 + len(info.filename.encode()) + 256
        start = info.header_offset
        end = min(start + slack + info.compress_size, self._raw.size) - 1
        r = self._raw.session.get(self.url, headers={"Range": f"bytes={start}-{end}"}, timeout=120)
        r.raise_for_status()
        blob = r.content
        self._raw.bytes_fetched += len(blob)
        if blob[:4] != b"PK\x03\x04":
            raise zipfile.BadZipFile(f"bad local header for {member}")
        name_len, extra_len = struct.unpack("<HH", blob[26:30])
        data = blob[30 + name_len + extra_len :][: info.compress_size]
        return zlib.decompress(data, -zlib.MAX_WBITS).decode("latin-1")

    @property
    def bytes_fetched(self) -> int:
        return self._raw.bytes_fetched if self._raw else 0


def _dms_to_deg(s: str) -> float:
    """'+47:15:36' -> 47.26"""
    sign = -1.0 if s.strip().startswith("-") else 1.0
    d, m, sec = (float(x) for x in s.strip().lstrip("+-").split(":"))
    return sign * (d + m / 60 + sec / 3600)


def _skip_header(text: str, first_col: str) -> io.StringIO:
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.replace(" ", "").startswith(first_col))
    return io.StringIO("\n".join(lines[start:]))


def load_stations(archive: RemoteArchive) -> pd.DataFrame:
    """All ECA&D TG stations: staid, name, country, lat, lon, elev_m."""
    cache = config.DATA_DIR / "ecad_stations.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    raw = pd.read_csv(
        _skip_header(archive.read_text("stations.txt"), "STAID,"),
        skipinitialspace=True,
        dtype=str,
    )
    raw.columns = [c.strip() for c in raw.columns]
    df = pd.DataFrame(
        {
            "staid": raw["STAID"].astype(int),
            "name": raw["STANAME"].str.strip(),
            "country": raw["CN"].str.strip(),
            "lat": raw["LAT"].map(_dms_to_deg),
            "lon": raw["LON"].map(_dms_to_deg),
            "elev_m": pd.to_numeric(raw["HGHT"], errors="coerce"),
        }
    )
    df.loc[df["elev_m"] <= -999, "elev_m"] = np.nan
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def load_sources(archive: RemoteArchive) -> pd.DataFrame:
    """Source series metadata: which measured series feed each blended station.

    ECA&D "blended" station files are gap-filled with data from neighbouring
    stations, so the same source (SOUID) can appear under several STAIDs.
    """
    cache = config.DATA_DIR / "ecad_sources.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    # Fixed-width: participant names may contain commas.
    text = _skip_header(archive.read_text("sources.txt"), "STAID,").read()
    rows = [ln for ln in text.splitlines()[1:] if ln.strip()]
    df = pd.DataFrame(
        {
            "staid": [int(r[0:5]) for r in rows],
            "souid": [int(r[6:12]) for r in rows],
            "lat": [_dms_to_deg(r[57:66]) for r in rows],
            "lon": [_dms_to_deg(r[67:77]) for r in rows],
            "elev_m": [float(r[78:82]) for r in rows],
            "start": pd.to_datetime([r[88:96] for r in rows], format="%Y%m%d", errors="coerce"),
            "stop": pd.to_datetime([r[97:105] for r in rows], format="%Y%m%d", errors="coerce"),
        }
    )
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def load_series(archive: RemoteArchive, staid: int) -> pd.DataFrame:
    """Daily mean temperature for one station within the study period.

    Returns a frame indexed by date with columns ``tg`` (degC) and ``souid``
    (the source series each value came from). Values flagged suspect/missing
    by ECA&D (Q_TG != 0) are dropped.
    """
    # Cached series are trimmed to the study period, so the period is part of the key.
    cache_dir = config.DATA_DIR / f"ecad_tg_{config.START}_{config.END}"
    cache = cache_dir / f"{staid}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    text = archive.read_text(f"TG_STAID{staid:06d}.txt")
    raw = pd.read_csv(_skip_header(text, "STAID,"), skipinitialspace=True)
    raw.columns = [c.strip() for c in raw.columns]
    ok = (raw["Q_TG"] == 0) & (raw["TG"] > -9999)
    raw = raw[ok]
    df = pd.DataFrame(
        {"tg": raw["TG"].to_numpy() / 10.0, "souid": raw["SOUID"].to_numpy()},
        index=pd.to_datetime(raw["DATE"].astype(str), format="%Y%m%d").rename("date"),
    )
    # A date must appear once; keep the first if the source file repeats one.
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df = df.loc[config.START : config.END]
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    return df
