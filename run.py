#!/usr/bin/env python3
"""How accurate are ERA5 temperatures in the Alps?  Run:  python run.py

1. Get stations   ECA&D daily mean temperature + true altitude
2. Get ERA5       2 m temperature + model height (and ERA5-Land, optional)
3. Match          same site (grid cell) and calendar day
4. Correct/check  lapse-rate elevation adjustment, then MBE / RMSE / r

All downloads are cached in data/; a second run downloads nothing.
"""
import argparse

import pandas as pd

from era5_alps import analysis, config, ecad, plots, stations


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-era5-land", action="store_true", help="skip the optional ERA5-Land comparison")
    args = ap.parse_args()
    products = ["ERA5"] if args.no_era5_land else list(config.PRODUCTS)

    print("[1/4] Selecting ECA&D stations")
    archive = ecad.RemoteArchive()
    st, obs = stations.select(archive)
    print(f"  downloaded {archive.bytes_fetched / 1e6:.1f} MB from the ECA&D archive this run")

    print("[2/4] Reanalysis grid cells + [3/4] matching")
    pairs, st_by_product = [], {}
    for product in products:
        p, st_by_product[product] = analysis.build_pairs(st, obs, product)
        pairs.append(p)
    pairs = pd.concat(pairs, ignore_index=True)
    # Compare products on identical station-days only.
    common = pairs.groupby(["staid", "date"])["product"].transform("nunique") == len(products)
    dropped = sorted(set(st["staid"]) - set(pairs.loc[common, "staid"]))
    if dropped:
        names = st.set_index("staid").loc[dropped, "name"].str.title().tolist()
        print(f"  {len(dropped)} station(s) lack data in one product and are left out: {', '.join(names)}")
    pairs = pairs[common]

    print("[4/4] Metrics and figures")
    regime = st.set_index("staid")["regime"]
    pairs["regime"] = pairs["staid"].map(regime)
    pairs["season"] = pairs["date"].dt.month.map(analysis.SEASONS)
    # Stations ERA5 cannot have assimilated vs. ones it may have (only present
    # when config.REQUIRE_INDEPENDENT is off).
    pairs["reference"] = pairs["staid"].map(st.set_index("staid")["independent"]).map(
        {True: "Independent (not exchanged)", False: "Exchanged (ERA5 may have used it)"}
    )

    per_station = analysis.station_table(pairs, st_by_product)
    overall = analysis.table(pairs, [])
    by_regime = analysis.table(pairs, ["regime"])
    by_season = analysis.table(pairs, ["regime", "season"])
    lapse = analysis.empirical_lapse_rates(pairs, per_station)
    by_reference = analysis.table(pairs, ["reference"])
    by_reference_regime = analysis.table(pairs, ["regime", "reference"])
    n_ref = pairs.groupby("reference")["staid"].nunique()
    by_reference.insert(2, "stations", by_reference["reference"].map(n_ref))

    out = config.RESULTS_DIR
    out.mkdir(exist_ok=True)
    per_station.to_csv(out / "metrics_per_station.csv", index=False, float_format="%.3f")
    overall.to_csv(out / "metrics_overall.csv", index=False, float_format="%.3f")
    by_regime.to_csv(out / "metrics_by_regime.csv", index=False, float_format="%.3f")
    by_season.to_csv(out / "metrics_by_regime_season.csv", index=False, float_format="%.3f")
    by_reference.to_csv(out / "metrics_by_independence.csv", index=False, float_format="%.3f")
    by_reference_regime.to_csv(out / "metrics_by_independence_regime.csv", index=False, float_format="%.3f")
    lapse.to_csv(out / "empirical_lapse_rates.csv", index=False, float_format="%.3f")

    plots.bias_map(per_station)
    plots.bias_vs_dz(per_station, lapse)
    plots.rmse_by_regime(by_regime)
    plots.monthly_bias(pairs, per_station)
    plots.example_series(pairs, per_station)

    pd.set_option("display.width", 200, "display.float_format", "{:.2f}".format)
    n_st = pairs["staid"].nunique()
    print(f"\n{n_st} stations, {len(pairs) // len(products)} station-days, {config.START} to {config.END}")
    for product in products:
        n_cells = st_by_product[product].loc[st_by_product[product]["staid"].isin(pairs["staid"]), "cell"].nunique()
        print(f"  {product}: {n_st} stations share {n_cells} grid cells")
    print("\nOverall\n" + overall.to_string(index=False))
    print("\nBy regime\n" + by_regime.to_string(index=False))
    print("\nIndependent vs. possibly assimilated stations\n" + by_reference.to_string(index=False))
    print("\nEmpirical lapse rate (slope of raw bias vs. height difference)\n" + lapse.to_string(index=False))
    print(f"\nTables and figures written to {out}/")


if __name__ == "__main__":
    main()
