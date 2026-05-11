"""Fetch soil properties from SoilGrids 2.0 REST API for a lat/lon point.

Unit conversions from SoilGrids mapped units to natural units:
  phh2o    pH×10      → pH           (÷10)
  soc      dg/kg      → g/kg         (÷10)
  nitrogen cg/kg      → cg/kg        (no change — output field keeps cg/kg)
  sand     g/kg       → %            (÷10)
  silt     g/kg       → %            (÷10)
  clay     g/kg       → %            (÷10)
  cec      mmol(c)/kg → mmol(c)/kg   (no change — output field keeps mmol/kg)
  bdod     cg/cm³     → kg/dm³       (÷100; 1 kg/dm³ = 1 g/cm³)

Note on masked pixels: SoilGrids returns null means for urban, water, and some
coastal pixels. When this occurs, the fetch automatically searches a spiral of
neighbouring offsets (up to ±0.012°, roughly 1.3 km) and returns the first
non-masked pixel, logging a warning with the applied offset.
"""

import json
import logging
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agri_sense.utils.config import config

logger = logging.getLogger(__name__)

_PROPERTIES = ["phh2o", "soc", "nitrogen", "sand", "silt", "clay", "cec", "bdod"]
_DEPTHS = ["0-5cm", "5-15cm", "15-30cm"]
_DEPTH_WEIGHTS: dict[str, int] = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}

# (output_key, divisor) — divisor converts mapped integer to natural unit
_CONVERSIONS: dict[str, tuple[str, float]] = {
    "phh2o": ("ph", 10.0),
    "soc": ("soc_g_per_kg", 10.0),
    "nitrogen": ("nitrogen_cg_per_kg", 1.0),
    "sand": ("sand_pct", 10.0),
    "silt": ("silt_pct", 10.0),
    "clay": ("clay_pct", 10.0),
    "cec": ("cec_mmol_per_kg", 1.0),
    "bdod": ("bulk_density_kg_per_dm3", 100.0),
}

# Spiral of (Δlat, Δlon) offsets tried when the primary pixel is masked.
# Cardinals first at each ring, then diagonals; step sizes up to 0.020° ≈ 2.2 km.
_NEIGHBOR_OFFSETS: list[tuple[float, float]] = [
    (0.0, 0.0),
    # ring ~0.005° (≈ 550 m)
    (0.005, 0.0),
    (-0.005, 0.0),
    (0.0, 0.005),
    (0.0, -0.005),
    # ring ~0.010° (≈ 1.1 km)
    (0.010, 0.0),
    (-0.010, 0.0),
    (0.0, 0.010),
    (0.0, -0.010),
    (0.005, 0.005),
    (-0.005, 0.005),
    (0.005, -0.005),
    (-0.005, -0.005),
    # ring ~0.015° (≈ 1.7 km)
    (0.015, 0.0),
    (-0.015, 0.0),
    (0.0, 0.015),
    (0.0, -0.015),
    (0.010, 0.010),
    (-0.010, 0.010),
    (0.010, -0.010),
    (-0.010, -0.010),
    # ring ~0.020° (≈ 2.2 km)
    (0.020, 0.0),
    (-0.020, 0.0),
    (0.0, 0.020),
    (0.0, -0.020),
    (0.015, 0.015),
    (-0.015, 0.015),
    (0.015, -0.015),
    (-0.015, -0.015),
]

VALID_TEXTURE_CLASSES: frozenset[str] = frozenset(
    {
        "sand",
        "loamy sand",
        "sandy loam",
        "loam",
        "silt loam",
        "silt",
        "sandy clay loam",
        "clay loam",
        "silty clay loam",
        "sandy clay",
        "silty clay",
        "clay",
    }
)


def _usda_texture_class(sand: float, silt: float, clay: float) -> str:
    """Classify soil texture using the USDA 12-class triangle (priority-ordered rules)."""
    # Heavy clays (clay ≥ 40 %)
    if clay >= 40:
        if silt >= 40:
            return "silty clay"
        if sand >= 45:
            return "sandy clay"
        return "clay"

    # Sandy clay (clay 35–40, sand ≥ 45)
    if clay >= 35 and sand >= 45:
        return "sandy clay"

    # Clay loam group (clay 27–40)
    if clay >= 27:
        if silt > 40:
            return "silty clay loam"
        if sand > 20:
            return "clay loam"
        return "silty clay loam"

    # Sandy clay loam (clay 20–35, sand > 45, silt < 28)
    if clay >= 20 and sand > 45 and silt < 28:
        return "sandy clay loam"

    # Pure silt / silt loam (high silt)
    if silt >= 80 and clay < 12:
        return "silt"
    if silt >= 50:
        return "silt loam"
    if silt >= 28 and clay < 12 and sand < 50:
        return "silt loam"

    # Sandy classes (high sand)
    if sand >= 85 and (silt + 1.5 * clay) < 15:
        return "sand"
    if sand >= 70 and (silt + 2 * clay) < 30:
        return "loamy sand"
    if sand >= 52 and clay < 20:
        return "sandy loam"
    if sand >= 43 and clay < 7:
        return "sandy loam"

    # Loam (broad middle ground)
    if clay >= 7 and silt >= 28 and sand < 52:
        return "loam"

    return "loam"  # boundary catch-all


def _cache_path(lat: float, lon: float) -> Path:
    cache_dir = config.raw_dir / "soilgrids"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{lat:.4f}_{lon:.4f}.json"


def _weighted_mean_0_30cm(depths_data: list[dict[str, object]]) -> float | None:
    """Return thickness-weighted mean across the three 0–30 cm depth slices."""
    total = 0.0
    weight_sum = 0
    for entry in depths_data:
        label = str(entry["label"])
        weight = _DEPTH_WEIGHTS.get(label)
        if weight is None:
            continue
        values = entry.get("values")
        if not isinstance(values, dict):
            continue
        val = values.get("mean")
        if val is None:
            continue
        total += float(val) * weight
        weight_sum += weight
    return (total / weight_sum) if weight_sum > 0 else None


def _has_any_data(payload: dict[str, object]) -> bool:
    """Return True if at least one layer/depth has a non-null mean."""
    layers = payload.get("properties", {}).get("layers", [])  # type: ignore[union-attr]
    for layer in layers:
        for depth_entry in layer.get("depths", []):
            if depth_entry.get("values", {}).get("mean") is not None:
                return True
    return False


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _fetch_from_api(lat: float, lon: float) -> dict[str, object]:  # type: ignore[return]
    url = f"{config.soilgrids_base_url}/properties/query"
    params: list[tuple[str, object]] = [
        ("lon", lon),
        ("lat", lat),
        *[("property", p) for p in _PROPERTIES],
        *[("depth", d) for d in _DEPTHS],
        ("value", "mean"),
    ]
    logger.info("Fetching SoilGrids: lat=%s lon=%s", lat, lon)
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def _process_payload(payload: dict[str, object]) -> dict[str, float | str]:
    """Convert a raw API response to the flat output dict with natural units."""
    layers: list[dict[str, object]] = payload["properties"]["layers"]  # type: ignore[index]
    result: dict[str, float | str] = {}
    for layer in layers:
        prop_name = str(layer["name"])
        conversion = _CONVERSIONS.get(prop_name)
        if conversion is None:
            continue
        output_key, divisor = conversion
        depths_data: list[dict[str, object]] = layer["depths"]  # type: ignore[assignment]
        raw_mean = _weighted_mean_0_30cm(depths_data)
        result[output_key] = round(raw_mean / divisor, 4) if raw_mean is not None else float("nan")

    sand = float(result.get("sand_pct", float("nan")))
    silt = float(result.get("silt_pct", float("nan")))
    clay = float(result.get("clay_pct", float("nan")))
    result["soil_texture_class"] = _usda_texture_class(sand, silt, clay)
    return result


def fetch_soil_properties(lat: float, lon: float) -> dict[str, float | str]:
    """Return soil properties for the 0–30 cm root zone at (lat, lon).

    Keys: ph, soc_g_per_kg, nitrogen_cg_per_kg, sand_pct, silt_pct, clay_pct,
    cec_mmol_per_kg, bulk_density_kg_per_dm3, soil_texture_class.

    Results are cached to data/raw/soilgrids/{lat}_{lon}.json.
    When the primary pixel is masked (urban/water), the nearest unmasked
    neighbour within ~1.3 km is used automatically.
    """
    cache = _cache_path(lat, lon)
    if cache.exists():
        logger.info("Cache hit: %s", cache)
        with cache.open() as fh:
            return json.load(fh)  # type: ignore[no-any-return]

    payload: dict[str, object] | None = None
    for dlat, dlon in _NEIGHBOR_OFFSETS:
        trial_lat = round(lat + dlat, 6)
        trial_lon = round(lon + dlon, 6)
        candidate = _fetch_from_api(trial_lat, trial_lon)
        if _has_any_data(candidate):
            payload = candidate
            if dlat != 0.0 or dlon != 0.0:
                logger.warning(
                    "Primary pixel masked; using neighbour offset (Δlat=%+.4f, Δlon=%+.4f)",
                    dlat,
                    dlon,
                )
            break

    if payload is None:
        logger.error("No SoilGrids data found within search radius for lat=%s lon=%s", lat, lon)
        result: dict[str, float | str] = {
            out_key: float("nan") for out_key, _ in _CONVERSIONS.values()
        }
        result["soil_texture_class"] = "loam"
    else:
        result = _process_payload(payload)

    with cache.open("w") as fh:
        json.dump(result, fh, indent=2, default=str)
    logger.info("Cached to %s", cache)
    return result
