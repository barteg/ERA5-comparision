# How accurate are ERA5 temperatures in the Alps?

Compares ERA5 (and, optionally, ERA5-Land) daily mean 2 m temperature with
ECA&D ground stations across the Alps and their forelands, following the four
steps of the project plan: get ERA5 → get stations → match site and calendar
day → correct for elevation and compute MBE, RMSE and Pearson r. Only stations
ERA5 cannot have assimilated are used.

    pip install -r requirements.txt
    python run.py                  # add --no-era5-land to skip the second product

Settings (domain, period, number of stations, lapse rate) are in
`era5_alps/config.py`. The first run takes a few minutes; later runs use the
cache in `data/` and take seconds.

## Results (2005–2024, 65 independent stations, 467,508 station-days)

| Regime | Stations | ERA5 RMSE raw → corrected (°C) | ERA5 bias raw → corrected (°C) |
|---|---|---|---|
| Lowland (< 300 m, inland) | 20 | 1.28 → 1.25 | −0.16 → +0.78 |
| Coastal (< 300 m, ≤ 25 km from sea) | 5 | 1.38 → 1.78 | −0.52 → −0.39 |
| Valley / foothill (300–800 m) | 20 | 2.19 → 1.34 | −0.45 → +0.47 |
| Mountain (≥ 800 m) | 20 | 3.83 → 2.14 | −0.55 → −0.79 |
| **All** | 65 | 2.57 → 1.64 | −0.40 → +0.11 |

- Error grows from lowland to mountain as the plan expected (about 1.3 °C raw in
  the lowlands, 3.8 °C in the mountains).
- Most of the valley and mountain error is elevation mismatch. Raw station bias
  follows the model-minus-station height difference almost linearly (r = −0.91).
- The fitted lapse rate is −5.2 °C/km, shallower than the assumed −6.5 °C/km in
  every season (−4.9 to −5.8). The standard correction therefore over-corrects
  slightly: lowland bias rises to +0.78 °C with no gain in RMSE.
- Mountain winter is the worst case: corrected RMSE is 2.7 °C in DJF against
  about 1.9 °C in the other seasons.
- Coastal figures rest on 5 stations and should not be relied on.
- Correlation is 0.95 raw and 0.98 corrected; 0.94 with the seasonal cycle removed.

ERA5-Land for this sample is not finished: the free API's daily quota ran out
with 60 of 65 grid cells downloaded. `python run.py` continues from the cache;
until then use `python run.py --no-era5-land`. An earlier 3-year run on an
unscreened sample found ERA5-Land better at the coast, similar in the lowlands
and slightly worse in the mountains.

Tables and figures are in `results/`; `ERA5_Alps_results.pptx` is the slide deck.

## Independence from ERA5

ERA5's surface analysis ingests 2 m temperature from stations exchanged on the
WMO network, so scoring ERA5 against those would be partly circular. With
`REQUIRE_INDEPENDENT = True` (the default) a station is used only if

- ECA&D lists no SYNOP-derived series for it (source ids 9xxxxx), and
- no NOAA ISD station (the archive of exchanged SYNOP/METAR reports) active in
  the study period lies within 5 km.

Of 699 stations with data, 301 pass. This ensures the station's own
measurements were not in the exchanged stream; it rests on public station lists,
not ECMWF's assimilation records, and ERA5 still draws on exchanged stations
nearby. On an earlier unscreened sample, exchanged and independent stations
scored alike (corrected RMSE 1.74 vs 1.72 °C).

## How duplicated data are avoided

- **ERA5 / ERA5-Land are fetched per unique grid cell, not per station.**
  Stations sharing a cell share one download (65 stations → 61 ERA5 cells), and
  cells already in `data/` are never requested again.
- **The 0.9 GB ECA&D archive is not downloaded.** Only the station list and the
  individual station files are read from it with HTTP range requests, and each
  is cached after trimming to the study period.
- **ECA&D "blended" series are de-blended.** Blended files fill gaps with values
  from neighbouring stations, so the same measurements can appear under several
  station IDs. Only values measured at the station's own site are used (source
  within 2 km and 50 m height), each source series may feed one station only,
  and co-located stations are skipped.
- **One value per station-day**, checked with an assertion after matching, and
  both products are scored on identical station-days.

## Data sources and caveats

- Stations: ECA&D blended daily mean temperature (TG), https://www.ecad.eu
  (non-commercial research and education use; cite Klein Tank et al. 2002).
- Reanalysis: ERA5 and ERA5-Land from Copernicus C3S, retrieved through the
  Open-Meteo archive API (no account needed) with `elevation=nan`, which returns
  the raw grid-cell value and model height instead of Open-Meteo's downscaled
  value. This is not the official CDS route; values are rounded to 0.1 °C.
- The free API has minute, hour and day request quotas. The code waits out the
  first two and stops cleanly on the third; a rerun resumes from the cache.
- Stations are a seeded random sample, up to 20 per regime, so the "All" row is
  not an area-weighted Alpine average. France dominates (39 of 65) and only 5
  coastal stations qualify as independent.
- The ERA5 daily mean is the 00–24 UTC average. National services define the
  station daily mean differently (various observation hours), which adds a few
  tenths of a degree of noise.
- Stations in ERA5-Land sea cells (no data) are left out of both products'
  statistics when ERA5-Land is included.
# ERA5-comparision
