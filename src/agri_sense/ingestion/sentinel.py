"""Fetch Sentinel-2 L2A NDVI timeseries from Microsoft Planetary Computer."""

import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import planetary_computer as pc
import pystac
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
from tqdm import tqdm

from agri_sense.utils.config import config

logger = logging.getLogger(__name__)

_PC_CATALOG = "https://planetarycomputer.microsoft.com/api/stac/v1"
_COLLECTION = "sentinel-2-l2a"

# SCL classes to exclude from NDVI computation.
# Keep only 4 (vegetation) and 5 (bare soil/not vegetated).
# Everything else — no-data, defects, shadow, water, cloud — is masked out.
#   0  No data
#   1  Saturated / defective
#   2  Dark area pixels (topographic shadow; also dark water in flat terrain)
#   3  Cloud shadow
#   6  Water  ← critical for Mekong Delta; large negative NDVI biases mean
#   7  Unclassified
#   8  Cloud medium probability
#   9  Cloud high probability
#  10  Thin cirrus
#  11  Snow / ice
_INVALID_SCL: frozenset[int] = frozenset({0, 1, 2, 3, 6, 7, 8, 9, 10, 11})

_SCL_LABELS: dict[int, str] = {
    0: "no_data",
    1: "saturated/defective",
    2: "dark_pixels",
    3: "cloud_shadow",
    4: "vegetation",
    5: "bare_soil",
    6: "water",
    7: "unclassified",
    8: "cloud_med_prob",
    9: "cloud_high_prob",
    10: "thin_cirrus",
    11: "snow_ice",
}

# Pre-fetch cloud-cover threshold.  Mekong Delta is genuinely cloudy; per-pixel
# SCL masking (above) handles residual cloud within the buffer window.
_CLOUD_COVER_THRESHOLD = 40


def _cache_path(lat: float, lon: float, start: date, end: date) -> Path:
    cache_dir = config.raw_dir / "sentinel"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{lat}_{lon}_{start}_{end}.parquet"


def _log_scl_distribution(scl: np.ndarray, scene_id: str) -> None:
    """Log the SCL pixel-class breakdown for a single scene window."""
    total = scl.size
    values, counts = np.unique(scl, return_counts=True)
    lines = [f"SCL class distribution — {scene_id} (total {total} px):"]
    for v, c in sorted(zip(values.tolist(), counts.tolist()), key=lambda x: -x[1]):
        label = _SCL_LABELS.get(int(v), "unknown")
        flag = " [INVALID]" if int(v) in _INVALID_SCL else " [valid]"
        lines.append(f"  SCL {int(v):2d} {label:<22}{flag}  {c:6d} px  ({100*c/total:5.1f}%)")
    logger.info("\n".join(lines))


def _read_scene(
    item: pystac.Item,
    cx: float,
    cy: float,
    buffer_m: int,
) -> tuple[float, float, float, np.ndarray] | None:
    """Sample a buffer_m × buffer_m window and return (ndvi_mean, ndvi_std, valid_pixel_pct, scl).

    ``scl`` is the (upsampled) raw SCL array — caller can log its distribution.
    Returns None when the scene cannot be read or yields zero valid pixels.
    """
    left = cx - buffer_m
    right = cx + buffer_m
    bottom = cy - buffer_m
    top = cy + buffer_m

    try:
        with rasterio.open(item.assets["B04"].href) as src:
            win = from_bounds(left, bottom, right, top, src.transform)
            b04 = src.read(1, window=win).astype(np.float32)
            nodata_val: float = float(src.nodata) if src.nodata is not None else 0.0

        with rasterio.open(item.assets["B08"].href) as src:
            win = from_bounds(left, bottom, right, top, src.transform)
            b08 = src.read(1, window=win).astype(np.float32)

        with rasterio.open(item.assets["SCL"].href) as src:
            win = from_bounds(left, bottom, right, top, src.transform)
            scl = src.read(1, window=win)
    except Exception as exc:
        logger.warning("Failed to read scene %s: %s", item.id, exc)
        return None

    if b04.size == 0 or b08.size == 0:
        return None

    # SCL is at 20 m, B04/B08 at 10 m — upsample with nearest-neighbour
    if scl.shape != b04.shape:
        r_scale = max(b04.shape[0] // scl.shape[0], 1)
        c_scale = max(b04.shape[1] // scl.shape[1], 1)
        scl = np.repeat(np.repeat(scl, r_scale, axis=0), c_scale, axis=1)
        scl = scl[: b04.shape[0], : b04.shape[1]]

    invalid = (b04 == nodata_val) | (b08 == nodata_val) | np.isin(scl, list(_INVALID_SCL))

    total = b04.size
    valid_count = int(total - invalid.sum())
    valid_pct = 100.0 * valid_count / total if total > 0 else 0.0

    if valid_count == 0:
        return None

    denom = b08 + b04
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where((denom > 0) & ~invalid, (b08 - b04) / denom, np.nan)

    return float(np.nanmean(ndvi)), float(np.nanstd(ndvi)), valid_pct, scl


def fetch_ndvi_timeseries(
    lat: float,
    lon: float,
    start: date,
    end: date,
    buffer_m: int = 500,
) -> pd.DataFrame:
    """Return NDVI timeseries for a lat/lon point over a date range.

    Searches sentinel-2-l2a for scenes with cloud cover < 40 % (tile-level),
    samples a buffer_m × buffer_m window, computes NDVI = (B08−B04)/(B08+B04),
    and masks non-vegetation/soil pixels using the SCL band.

    Invalid SCL classes (masked out): 0 no-data, 1 saturated, 2 dark pixels,
    3 cloud shadow, 6 water, 7 unclassified, 8–10 cloud, 11 snow.
    Valid classes (kept): 4 vegetation, 5 bare soil.

    Columns: date (pd.Timestamp), ndvi_mean, ndvi_std, valid_pixel_pct.
    Scenes where valid_pixel_pct < 50 % are dropped. When multiple tiles cover
    the same date, the one with the highest valid_pixel_pct is kept.

    SCL class distribution is logged at INFO for the first readable scene.

    Results cached to data/raw/sentinel/{lat}_{lon}_{start}_{end}.parquet.
    """
    cache = _cache_path(lat, lon, start, end)
    if cache.exists():
        logger.info("Cache hit: %s", cache)
        return pd.read_parquet(cache)

    buf_deg = max(buffer_m / 111_320.0, 0.005)

    client = pystac_client.Client.open(_PC_CATALOG, modifier=pc.sign_inplace)
    search = client.search(
        collections=[_COLLECTION],
        bbox=[lon - buf_deg, lat - buf_deg, lon + buf_deg, lat + buf_deg],
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": _CLOUD_COVER_THRESHOLD}},
    )

    items = list(search.items())
    n_total = len(items)
    logger.info(
        "STAC search → %d scenes (cloud_cover < %d%%) | lat=%s lon=%s %s→%s",
        n_total,
        _CLOUD_COVER_THRESHOLD,
        lat,
        lon,
        start,
        end,
    )

    if not items:
        logger.warning("No Sentinel-2 scenes found.")
        return pd.DataFrame(columns=["date", "ndvi_mean", "ndvi_std", "valid_pixel_pct"])

    rows: list[dict[str, object]] = []
    n_crs_err = 0
    n_low_valid = 0
    scl_logged = False

    for item in tqdm(items, desc="Sentinel-2 scenes", unit="scene"):
        try:
            with rasterio.open(item.assets["B04"].href) as src:
                epsg = src.crs.to_epsg()
        except Exception as exc:
            logger.warning("Cannot determine CRS for %s: %s", item.id, exc)
            n_crs_err += 1
            continue

        trans = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        cx, cy = trans.transform(lon, lat)

        result = _read_scene(item, cx, cy, buffer_m)
        if result is None:
            n_crs_err += 1
            continue

        ndvi_mean, ndvi_std, valid_pct, scl = result

        if not scl_logged:
            _log_scl_distribution(scl, item.id)
            scl_logged = True

        if valid_pct < 50.0:
            logger.debug("Skipping %s — valid_pixel_pct=%.1f%%", item.id, valid_pct)
            n_low_valid += 1
            continue

        rows.append(
            {
                "date": pd.Timestamp(item.datetime.date()),
                "ndvi_mean": ndvi_mean,
                "ndvi_std": ndvi_std,
                "valid_pixel_pct": valid_pct,
            }
        )

    n_used = len(rows)
    logger.info(
        "Scene funnel: %d total → %d CRS/read errors → %d low valid_pct → %d used",
        n_total,
        n_crs_err,
        n_low_valid,
        n_used,
    )

    if not rows:
        return pd.DataFrame(columns=["date", "ndvi_mean", "ndvi_std", "valid_pixel_pct"])

    df = (
        pd.DataFrame(rows)
        .sort_values("valid_pixel_pct", ascending=False)
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )

    df.to_parquet(cache)
    logger.info("Cached to %s (%d rows)", cache, len(df))
    return df
