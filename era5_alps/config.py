"""Study configuration. Edit here to change domain, period or sample size."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"        # download cache (safe to delete; will be refetched)
RESULTS_DIR = ROOT / "results"  # tables and figures

# --- Domain: the Alps and their forelands (Po plain, Adriatic/Ligurian coasts) ---
LAT_MIN, LAT_MAX = 43.5, 48.5
LON_MIN, LON_MAX = 5.0, 16.5

# --- Period ---
START, END = "2005-01-01", "2024-12-31"

# --- Station selection ---
MIN_COVERAGE = 0.95          # required fraction of valid days in the period
MAX_STATIONS = 80            # cap, split evenly across the four regimes
DUPLICATE_RADIUS_KM = 2.0    # stations closer than this (and within
DUPLICATE_DZ_M = 50.0        # this height difference) are the same site

# --- Independence from ERA5 ---
# ERA5's surface analysis ingests 2 m temperature from stations exchanged on the
# WMO network. With this on, only stations that were NOT exchanged are used:
# no SYNOP-derived series in ECA&D, and no NOAA ISD station (the archive of
# globally exchanged SYNOP/METAR reports) within INDEPENDENCE_RADIUS_KM.
REQUIRE_INDEPENDENT = True
INDEPENDENCE_RADIUS_KM = 5.0

# --- Regimes (slide "Expected outcomes by geographic regime") ---
COAST_KM = 25.0              # coastal: within this distance of the sea and below 300 m
MOUNTAIN_ELEV_M = 800.0      # mountain: station above this height
                             # valley / foothill: 300 m to MOUNTAIN_ELEV_M; lowland: the rest

# --- Elevation correction ---
LAPSE_RATE = -6.5e-3         # degC per metre (standard atmosphere)

# --- Sources ---
ECAD_ZIP_URL = "https://knmi-ecad-assets-prd.s3.amazonaws.com/download/ECA_blend_tg.zip"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
ISD_HISTORY_URL = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
COASTLINE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_coastline.geojson"
)
BORDERS_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_0_boundary_lines_land.geojson"
)

# Reanalysis products: name -> (Open-Meteo model id, grid spacing in degrees)
PRODUCTS = {
    "ERA5": ("era5", 0.25),
    "ERA5-Land": ("era5_land", 0.1),
}
