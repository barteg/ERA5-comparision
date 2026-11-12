"""Figures for the ERA5 vs. station comparison."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from . import config
from .stations import REGIMES, load_lines

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_LIGHT, ORANGE_LIGHT = "#9ec5f4", "#f6b99f"
PRODUCT_COLOR = {"ERA5": (BLUE, BLUE_LIGHT), "ERA5-Land": (ORANGE, ORANGE_LIGHT)}
DIVERGING = LinearSegmentedColormap.from_list("bias", ["#184f95", "#6da7ec", "#f0efec", "#e66767", "#a32222"])

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.size": 10, "text.color": INK, "axes.labelcolor": MUTED,
        "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": GRID,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "legend.frameon": False, "figure.dpi": 150,
    }
)


def _save(fig, name: str):
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(config.RESULTS_DIR / name, bbox_inches="tight")
    plt.close(fig)


def bias_map(per_station: pd.DataFrame, product: str = "ERA5"):
    """Station mean bias before and after the elevation correction."""
    df = per_station[per_station["product"] == product]
    lim = float(np.ceil(df.loc[df["version"] == "raw", "MBE"].abs().quantile(0.95)))
    norm = TwoSlopeNorm(0, -lim, lim)
    aspect = 1 / np.cos(np.radians((config.LAT_MIN + config.LAT_MAX) / 2))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4), sharey=True, constrained_layout=True)
    for ax, version, label in zip(axes, ["raw", "corrected"], ["Raw grid-cell value", "After −6.5 °C/km elevation correction"]):
        for xy in load_lines(config.COASTLINE_URL, "ne_50m_coastline.geojson"):
            ax.plot(xy[:, 0], xy[:, 1], color=MUTED, lw=0.9)
        for xy in load_lines(config.BORDERS_URL, "ne_50m_borders.geojson"):
            ax.plot(xy[:, 0], xy[:, 1], color="#b5b4ae", lw=0.6)
        sub = df[df["version"] == version]
        sc = ax.scatter(sub["lon"], sub["lat"], c=sub["MBE"], cmap=DIVERGING, norm=norm, s=62,
                        edgecolors=INK, linewidths=0.6, zorder=3)
        ax.set(xlim=(config.LON_MIN, config.LON_MAX), ylim=(config.LAT_MIN, config.LAT_MAX),
               aspect=aspect, title=label, xlabel="Longitude (°E)")
        ax.grid(False)
    axes[0].set_ylabel("Latitude (°N)")
    fig.colorbar(sc, ax=axes, shrink=0.85, pad=0.01, extend="both").set_label(f"Mean bias, {product} − station (°C)")
    fig.suptitle(f"{product} mean temperature bias at {df['staid'].nunique()} Alpine stations, "
                 f"{config.START[:4]}–{config.END[:4]}", x=0.01, ha="left", fontsize=13, fontweight="bold")
    _save(fig, "fig1_bias_map.png")


def bias_vs_dz(per_station: pd.DataFrame, lapse: pd.DataFrame):
    """Raw bias against model-minus-station height: the lapse-rate signature."""
    raw = per_station[per_station["version"] == "raw"]
    products = list(raw["product"].unique())
    fig, axes = plt.subplots(1, len(products), figsize=(6.2 * len(products), 4.6), sharey=True,
                             constrained_layout=True, squeeze=False)
    for ax, product in zip(axes[0], products):
        sub = raw[raw["product"] == product]
        color = PRODUCT_COLOR[product][0]
        x = np.array([sub["dz_m"].min(), sub["dz_m"].max()])
        fit = lapse[(lapse["product"] == product) & (lapse["season"] == "All year")].iloc[0]
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.plot(x, config.LAPSE_RATE * x, color=MUTED, lw=1.5, ls="--", label="Standard atmosphere: −6.5 °C/km")
        ax.plot(x, fit["intercept_C"] + fit["lapse_rate_C_per_km"] / 1000 * x, color=color, lw=2,
                label=f"Fitted to stations: {fit['lapse_rate_C_per_km']:.1f} °C/km".replace("-", "−"))
        ax.scatter(sub["dz_m"], sub["MBE"], s=46, color=color, edgecolors=SURFACE, linewidths=1, zorder=3)
        ax.set(title=product, xlabel="Model grid-cell height − station height (m)")
        ax.legend(loc="upper right")
    axes[0][0].set_ylabel("Raw mean bias, model − station (°C)")
    fig.suptitle("Raw bias is mostly an elevation mismatch", x=0.01, ha="left", fontsize=13, fontweight="bold")
    _save(fig, "fig2_bias_vs_elevation_difference.png")


def rmse_by_regime(by_regime: pd.DataFrame):
    """RMSE per geographic regime, raw vs. corrected, for each product."""
    products = list(by_regime["product"].unique())
    regimes = [r for r in REGIMES if r in set(by_regime["regime"])]
    fig, ax = plt.subplots(figsize=(10, 4.6), constrained_layout=True)
    n = 2 * len(products)
    width = 0.8 / n
    for i, (product, version) in enumerate((p, v) for p in products for v in ("raw", "corrected")):
        sub = by_regime[(by_regime["product"] == product) & (by_regime["version"] == version)].set_index("regime")
        vals = sub["RMSE"].reindex(regimes).to_numpy()
        xs = np.arange(len(regimes)) + (i - (n - 1) / 2) * width
        ax.bar(xs, vals, width * 0.9, color=PRODUCT_COLOR[product][version == "raw"],
               label=f"{product}, {'raw' if version == 'raw' else 'elevation-corrected'}")
        for x, v in zip(xs, vals):
            if np.isfinite(v):
                ax.text(x, v + 0.04, f"{v:.1f}", ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(np.arange(len(regimes)), regimes)
    ax.tick_params(axis="x", colors=INK, length=0)
    ax.set(ylabel="RMSE of daily mean temperature (°C)",
           title="Error grows with terrain complexity; the elevation correction removes much of it")
    ax.grid(axis="x", visible=False)
    ax.legend(ncols=2, loc="upper left")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.18)
    _save(fig, "fig3_rmse_by_regime.png")


def monthly_bias(pairs: pd.DataFrame, per_station: pd.DataFrame):
    """Mean bias through the year, per regime (small multiples, shared axis)."""
    regime = per_station.drop_duplicates("staid").set_index("staid")["regime"]
    df = pairs.assign(regime=pairs["staid"].map(regime), month=pairs["date"].dt.month)
    regimes = [r for r in REGIMES if r in set(df["regime"])]
    fig, axes = plt.subplots(1, len(regimes), figsize=(3.4 * len(regimes), 3.9), sharey=True, constrained_layout=True)
    for ax, reg in zip(np.atleast_1d(axes), regimes):
        ax.axhline(0, color=MUTED, lw=0.8)
        for product, sub in df[df["regime"] == reg].groupby("product", sort=False):
            g = sub.groupby("month")
            color = PRODUCT_COLOR[product][0]
            ax.plot(g["raw"].mean() - g["obs"].mean(), color=color, lw=1.5, ls=":", label=f"{product}, raw")
            ax.plot(g["corrected"].mean() - g["obs"].mean(), color=color, lw=2, marker="o", ms=4,
                    label=f"{product}, elevation-corrected")
        ax.set_xticks(range(1, 13), list("JFMAMJJASOND"))
        ax.set_title(reg)
    np.atleast_1d(axes)[0].set_ylabel("Mean bias, model − station (°C)")
    handles, labels = np.atleast_1d(axes)[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncols=4)
    fig.suptitle("Seasonal cycle of the bias by regime", x=0.01, ha="left", fontsize=13, fontweight="bold")
    _save(fig, "fig4_monthly_bias_by_regime.png")


def example_series(pairs: pd.DataFrame, per_station: pd.DataFrame, product: str = "ERA5"):
    """One year of daily values at the station with the largest height mismatch."""
    info = per_station[(per_station["product"] == product) & (per_station["version"] == "raw")]
    st = info.loc[info["dz_m"].abs().idxmax()]
    year = int(config.END[:4])
    df = pairs[(pairs["product"] == product) & (pairs["staid"] == st["staid"]) & (pairs["date"].dt.year == year)]
    df = df.set_index("date")
    fig, ax = plt.subplots(figsize=(11, 4.2), constrained_layout=True)
    ax.plot(df["raw"], color=ORANGE, lw=1.3, label=f"{product} raw (grid cell at {st['model_elev_m']:.0f} m)")
    ax.plot(df["corrected"], color=BLUE, lw=1.3, label=f"{product} elevation-corrected")
    ax.plot(df["obs"], color=INK, lw=1.3, label=f"Station (at {st['elev_m']:.0f} m)")
    ax.set(ylabel="Daily mean temperature (°C)",
           title=f"{st['name'].title()} ({st['country']}), {year}: largest model–station height difference "
                 f"({st['dz_m']:+.0f} m)")
    ax.legend(ncols=3, loc="upper left")
    ax.set_ylim(top=ax.get_ylim()[1] + 4)
    _save(fig, "fig5_example_station.png")
