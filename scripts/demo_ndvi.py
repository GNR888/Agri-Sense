"""NDVI timeseries demo — Cần Thơ (rice) and Buôn Ma Thuột (coffee).

Uses representative farm-point coordinates from geo.py, NOT capital centroids.
Runs both locations sequentially, prints diagnostics and saves plots.
"""

import logging
import matplotlib

matplotlib.use("Agg")

from datetime import date, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from agri_sense.ingestion.sentinel import fetch_ndvi_timeseries
from agri_sense.utils.geo import PROVINCES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

END = date.today()
START = END - timedelta(days=365)
OUT_DIR = Path("data/raw/sentinel")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _plot_and_save(df: pd.DataFrame, location: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 5))

    if not df.empty:
        ax.plot(
            df["date"],
            df["ndvi_mean"],
            color="#2ecc71",
            linewidth=1.8,
            marker="o",
            markersize=5,
            zorder=3,
            label="NDVI mean",
        )
        ax.fill_between(
            df["date"],
            df["ndvi_mean"] - df["ndvi_std"],
            df["ndvi_mean"] + df["ndvi_std"],
            alpha=0.25,
            color="#2ecc71",
            label="±1 std dev",
        )
        for _, row in df.iterrows():
            ax.annotate(
                f"{row['ndvi_mean']:.2f}",
                xy=(row["date"], row["ndvi_mean"]),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=7.5,
                color="#1a7a41",
            )

    ax.axhline(0.3, color="#e67e22", linewidth=0.9, linestyle="--", label="0.3 sparse veg")
    ax.axhline(0.6, color="#27ae60", linewidth=0.9, linestyle="--", label="0.6 dense veg")

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.xticks(rotation=30, ha="right")

    ax.set_ylim(-0.15, 1.05)
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("NDVI", fontsize=11)
    n_scenes = len(df) if not df.empty else 0
    ax.set_title(
        f"Sentinel-2 NDVI — {location}\n"
        f"{START} to {END}  |  {n_scenes} usable scenes  |  500 m farm buffer",
        fontsize=12,
        pad=12,
    )
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def run_location(province_id: str, out_filename: str) -> None:
    prov = PROVINCES[province_id]
    lat, lon = prov.farm_lat, prov.farm_lon
    display = f"{prov.name} ({prov.region})"

    print(f"\n{'='*70}")
    print(f"  Location : {display}")
    print(f"  Crop     : {prov.dominant_crop}")
    print(f"  Farm pt  : lat={lat}, lon={lon}")
    print(f"  Note     : {prov.farm_note}")
    print(f"  Period   : {START} → {END}")
    print(f"{'='*70}\n")

    df = fetch_ndvi_timeseries(lat=lat, lon=lon, start=START, end=END)

    if df.empty:
        print(f"[{prov.name}] No usable scenes found.")
    else:
        print(f"\n[{prov.name}] NDVI timeseries ({len(df)} scenes):")
        print(df.to_string(index=False, float_format="{:.4f}".format))
        print(f"\n  NDVI range : {df['ndvi_mean'].min():.3f} – {df['ndvi_mean'].max():.3f}")
        print(f"  Mean NDVI  : {df['ndvi_mean'].mean():.3f}")

    out_path = OUT_DIR / out_filename
    _plot_and_save(df, display, out_path)
    print(f"\n  Plot saved : {out_path}")


if __name__ == "__main__":
    run_location("can_tho", "cantho_ndvi.png")
    run_location("dak_lak", "daklak_ndvi.png")
    print("\nDone.")
