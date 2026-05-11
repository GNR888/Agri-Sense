"""Inference path: recommend top-k crops for a clicked map location.

# ---------------------------------------------------------------------------
# SAMPLE FEATURE VECTORS (run scripts/demo_predict.py --debug to populate)
# ---------------------------------------------------------------------------
# Paste the logged feature vectors for the three canonical test locations here
# after running inference. They should differ meaningfully across location/season.
#
# Location 1: Cần Thơ, Đông Xuân
#   (expected: rice-heavy features — low elevation, high humidity, Mekong delta)
#
# Location 2: Buôn Ma Thuột (Đắk Lắk), main season
#   (expected: coffee/pepper features — high elevation, central highlands)
#
# Location 3: Hà Nội area (Thái Bình), Hè Thu
#   (expected: rice features — Red River Delta, moderate temp)
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from agri_sense.ingestion.market_prices import load_prices
from agri_sense.ingestion.nasa_power import fetch_daily_weather
from agri_sense.ingestion.open_meteo import fetch_forecast_risk
from agri_sense.ingestion.sentinel import fetch_ndvi_timeseries
from agri_sense.ingestion.soilgrids import fetch_soil_properties
from agri_sense.market.price_forecast import forecast_6months
from agri_sense.models.crop_classifier import CropClassifier
from agri_sense.models.yield_regressor import YieldRegressor
from agri_sense.processing.build_dataset import aggregate_ndvi, aggregate_weather, season_window
from agri_sense.processing.features import add_province_features
from agri_sense.processing.normalise import NUMERIC_FEATURE_COLS
from agri_sense.recommendations.farm_plan import compute_farm_plan
from agri_sense.recommendations.farming_methods import farming_methods_for_crop
from agri_sense.recommendations.fertiliser import fertiliser_schedule, recommend_fertiliser
from agri_sense.recommendations.harvest_timing import _fallback_harvest_timing, compute_harvest_timing
from agri_sense.utils.config import config
from agri_sense.utils.geo import PROVINCES

logger = logging.getLogger(__name__)

# Sentinel-2 reliable coverage starts 2017; use previous full year for inference.
_SENTINEL2_START_YEAR = 2017
_INFERENCE_YEAR = date.today().year - 1

# Lazy singletons — loaded once on first call
_clf: CropClassifier | None = None
_reg: YieldRegressor | None = None
_scaler_params: dict[str, object] | None = None
_feature_cols: dict[str, list[str]] | None = None
_prices: dict[str, float] | None = None


def _load_artefacts() -> tuple[
    CropClassifier,
    YieldRegressor,
    dict[str, object],
    dict[str, list[str]],
    dict[str, float],
]:
    global _clf, _reg, _scaler_params, _feature_cols, _prices

    if _clf is None:
        clf = CropClassifier()
        clf.load(config.processed_dir / "classifier.json")
        _clf = clf

    if _reg is None:
        reg = YieldRegressor()
        reg.load(config.processed_dir / "regressor.json")
        _reg = reg

    if _scaler_params is None:
        _scaler_params = json.loads(
            (config.processed_dir / "scaler_params.json").read_text()
        )

    if _feature_cols is None:
        _feature_cols = json.loads(
            (config.processed_dir / "feature_columns.json").read_text()
        )

    if _prices is None:
        prices_df = load_prices()
        _prices = (
            prices_df.sort_values("year")
            .groupby("crop")["price_vnd_per_kg"]
            .last()
            .to_dict()
        )

    assert _clf is not None
    assert _reg is not None
    assert _scaler_params is not None
    assert _feature_cols is not None
    assert _prices is not None
    return _clf, _reg, _scaler_params, _feature_cols, _prices


def _nearest_province(lat: float, lon: float) -> str:
    """Return province key whose capital centroid is closest to (lat, lon)."""
    return min(
        PROVINCES.keys(),
        key=lambda k: (PROVINCES[k].capital_lat - lat) ** 2
        + (PROVINCES[k].capital_lon - lon) ** 2,
    )


def _fetch_ndvi_with_fallback(
    lat: float,
    lon: float,
    start: date,
    end: date,
    tag: str,
) -> pd.DataFrame:
    """Fetch NDVI with up to 3 attempts; return empty DataFrame on failure."""
    empty = pd.DataFrame(columns=["date", "ndvi_mean", "ndvi_std", "valid_pixel_pct"])
    for attempt in range(1, 4):
        try:
            return fetch_ndvi_timeseries(lat, lon, start, end)
        except Exception as exc:  # noqa: BLE001
            if attempt < 3:
                wait = 2 ** attempt
                logger.warning("NDVI attempt %d/3 failed (%s=%s), retrying in %ds", attempt, tag, exc, wait)
                time.sleep(wait)
            else:
                logger.warning("NDVI failed all 3 attempts for %s: %s → using NaN NDVI", tag, exc)
    return empty


def _build_raw_features(
    province_key: str,
    season: str,
    year: int,
) -> dict[str, object]:
    """Fetch and aggregate raw (unscaled) features for a province×season×year."""
    info = PROVINCES[province_key]
    start, end = season_window(year, season)

    weather_df = fetch_daily_weather(
        info.farm_lat,
        info.farm_lon,
        start,
        end,
        cache_tag=f"{province_key}_{season}_{year}",
    )
    climate = aggregate_weather(weather_df, start)

    if start.year >= _SENTINEL2_START_YEAR:
        tag = f"{province_key}/{year}/{season}"
        ndvi_df = _fetch_ndvi_with_fallback(info.farm_lat, info.farm_lon, start, end, tag)
    else:
        ndvi_df = pd.DataFrame(columns=["date", "ndvi_mean", "ndvi_std", "valid_pixel_pct"])
    ndvi = aggregate_ndvi(ndvi_df, start)

    soil = fetch_soil_properties(info.farm_lat, info.farm_lon)

    raw: dict[str, object] = {
        "farm_lat": info.farm_lat,
        "farm_lon": info.farm_lon,
    }
    raw.update(climate)
    raw.update({k: v for k, v in soil.items() if k != "soil_texture_class"})
    raw.update(ndvi)
    raw["soil_texture_class"] = soil.get("soil_texture_class", "loam")

    # Geographic features — carry location signal beyond lat/lon
    raw.update(add_province_features(province_key, info.region))

    return raw


def _normalise(
    raw: dict[str, object],
    season: str,
    scaler_params: dict[str, object],
    price_override: float | None = None,
) -> dict[str, float]:
    """Apply scaler_params min-max scaling and OHE; return flat feature dict."""
    feature_min: dict[str, float] = scaler_params["feature_min"]  # type: ignore[assignment]
    feature_max: dict[str, float] = scaler_params["feature_max"]  # type: ignore[assignment]
    season_cats: list[str] = scaler_params["season_categories"]  # type: ignore[assignment]
    soil_tex_cats: list[str] = scaler_params["soil_texture_categories"]  # type: ignore[assignment]

    result: dict[str, float] = {}

    # -- min-max scale numeric features
    for col in NUMERIC_FEATURE_COLS:
        if col not in feature_min:
            continue
        raw_val = raw.get(col)
        if col == "price_vnd_per_kg" and price_override is not None:
            val = price_override
        elif raw_val is None or (isinstance(raw_val, float) and math.isnan(raw_val)):
            result[col] = 0.5
            continue
        else:
            val = float(raw_val)

        lo = feature_min[col]
        hi = feature_max[col]
        rng = hi - lo
        result[col] = 0.0 if rng == 0.0 else max(0.0, min(1.0, (val - lo) / rng))

    # -- imputed flags (True when the raw value was NaN)
    for col in ["ndvi_peak", "ndvi_days_to_peak", "ndvi_mean_season"]:
        v = raw.get(col)
        result[f"{col}_imputed"] = (
            1.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else 0.0
        )

    # -- OHE season
    for cat in season_cats:
        result[f"season_{cat}"] = 1.0 if season == cat else 0.0

    # -- OHE soil texture
    soil_tex = str(raw.get("soil_texture_class", "loam"))
    for cat in soil_tex_cats:
        result[f"soil_tex_{cat}"] = 1.0 if soil_tex == cat else 0.0

    return result


def temperature_scale(probs: np.ndarray, T: float) -> np.ndarray:
    """Soften a probability distribution via temperature scaling.

    Higher T → flatter distribution (more uncertainty expressed).
    T=1.0 is a no-op; T=2.0 is the default from config.CLASSIFIER_TEMPERATURE.
    """
    logits = np.log(probs + 1e-9)
    scaled = logits / T
    exp = np.exp(scaled - scaled.max(axis=1, keepdims=True))
    return exp / exp.sum(axis=1, keepdims=True)


# Mapping from user-facing override keys to (raw_feature_key, unit_conversion)
# soc_pct is % organic carbon; raw uses g/kg → multiply by 10
# nitrogen_g_per_kg is g/kg; raw uses cg/kg → multiply by 100
_SOIL_OVERRIDE_MAP: dict[str, tuple[str, float]] = {
    "ph": ("ph", 1.0),
    "soc_pct": ("soc_g_per_kg", 10.0),
    "nitrogen_g_per_kg": ("nitrogen_cg_per_kg", 100.0),
}
# texture_class is handled separately (str, no conversion)


def recommend(
    lat: float,
    lon: float,
    season: str,
    top_k: int = 3,
    farm_size_ha: float | None = None,
    soil_overrides: dict[str, object] | None = None,
    planting_date: date | None = None,
) -> dict[str, object]:
    """Return crop recommendations with price forecasts, fertiliser advice, and farm plan.

    Args:
        lat:            Latitude of the clicked point (WGS-84).
        lon:            Longitude of the clicked point (WGS-84).
        season:         One of the Vietnamese season names or 'main' for annuals.
        top_k:          Number of crops to recommend (default 3).
        farm_size_ha:   Total farm size in hectares. When provided, a land
                        allocation plan is included in the response.
        soil_overrides: Optional dict of farmer-measured values that replace
                        SoilGrids defaults. Keys: ph, soc_pct (%), nitrogen_g_per_kg,
                        texture_class. Only provided keys are overridden.

    Returns:
        Dict with keys:
            recommendations: list of per-crop dicts (crop, probability,
                predicted_yield_t_ha, expected_revenue_vnd_per_ha, confidence,
                price_forecast_vnd_per_tonne, price_trend, fertiliser_recommendation)
            farm_plan: land-allocation dict (or None if farm_size_ha not provided)
            is_high_risk: bool from 14-day weather forecast
            raw_soil: dict of soil values actually used (post-override)
            data_source: "soilgrids" | "farmer_measured" | "mixed"
    """
    clf, reg, scaler_params, feature_cols, prices = _load_artefacts()

    _planting_date: date = planting_date if planting_date is not None else date.today() + timedelta(days=7)

    # 1. Find nearest province
    province_key = _nearest_province(lat, lon)
    info = PROVINCES[province_key]
    logger.info(
        "Nearest province: %s  farm=(%.4f, %.4f)",
        info.name,
        info.farm_lat,
        info.farm_lon,
    )

    # 2. Build raw features (ingestion pipeline, cached where possible)
    year = _INFERENCE_YEAR
    raw = _build_raw_features(province_key, season, year)

    # 2b. Apply farmer soil overrides (replaces SoilGrids values in feature vector)
    overridden_keys: list[str] = []
    if soil_overrides:
        for override_key, (raw_key, scale) in _SOIL_OVERRIDE_MAP.items():
            val = soil_overrides.get(override_key)
            if val is not None:
                raw[raw_key] = float(val) * scale  # type: ignore[arg-type]
                overridden_keys.append(override_key)
                logger.info(
                    "Soil override applied: %s=%.3f → %s=%.3f",
                    override_key, float(val), raw_key, float(val) * scale,  # type: ignore[arg-type]
                )
        tex = soil_overrides.get("texture_class")
        if tex is not None:
            raw["soil_texture_class"] = str(tex)
            overridden_keys.append("texture_class")
            logger.info("Soil override applied: texture_class=%s", tex)

    all_soil_keys = {"ph", "soc_pct", "nitrogen_g_per_kg", "texture_class"}
    if not overridden_keys:
        data_source = "soilgrids"
    elif set(overridden_keys) >= all_soil_keys:
        data_source = "farmer_measured"
    else:
        data_source = "mixed"

    # 3. Fetch 14-day weather forecast for risk signals (fails silently)
    forecast_risk = fetch_forecast_risk(info.farm_lat, info.farm_lon)
    is_high_risk = bool(forecast_risk["is_high_risk"])
    supply_shock = float(forecast_risk["supply_shock_multiplier"])
    forecast_rain_14d = float(forecast_risk.get("total_rain_mm_14d", 100.0))
    forecast_rain_days = int(forecast_risk.get("rain_days_14d", 0))
    forecast_temp_14d = float(forecast_risk.get("mean_temp_c", 28.0))

    # 4. Normalise for classifier (price unknown → 0.5 midpoint)
    norm_clf = _normalise(raw, season, scaler_params, price_override=None)

    # 5. Classify → calibrated + temperature-scaled probabilities
    clf_cols: list[str] = feature_cols["classifier_features"]
    row_clf = pd.DataFrame([{c: norm_clf.get(c, 0.0) for c in clf_cols}])

    # Log full feature vector for location-discrimination debugging
    logger.info(
        "Feature vector BEFORE model | province=%s season=%s\n%s",
        province_key,
        season,
        "\n".join(f"  {k}: {v:.4f}" for k, v in sorted(norm_clf.items())),
    )

    raw_proba: np.ndarray = clf.predict_proba(row_clf)  # shape (1, n_classes)
    T = config.classifier_temperature
    scaled_proba: np.ndarray = temperature_scale(raw_proba, T)[0]  # shape (n_classes,)

    top_indices = list(np.argsort(scaled_proba)[::-1][:top_k])

    # 6. Columns in the regressor that are NOT crop-OHE
    reg_cols: list[str] = feature_cols["regressor_features"]
    reg_base_cols = [c for c in reg_cols if not c.startswith("crop_")]
    crop_ohe_cols = [c for c in reg_cols if c.startswith("crop_")]

    # 7. Per-crop yield + price + revenue + fertiliser
    feature_min: dict[str, float] = scaler_params["feature_min"]  # type: ignore[assignment]
    feature_max: dict[str, float] = scaler_params["feature_max"]  # type: ignore[assignment]

    top_probs = [float(scaled_proba[idx]) for idx in top_indices]
    clipped = [max(0.05, p) for p in top_probs]
    total_clip = sum(clipped)
    normalised_probs = [p / total_clip for p in clipped]

    # Extract raw weather and soil values for fertiliser calculation
    rainfall_mm = float(raw.get("total_precip_mm") or 0.0)
    mean_temp_c = float(raw.get("mean_temp_c") or 28.0)
    soil_ph = float(raw.get("ph") or 6.5)
    soc_g_per_kg = float(raw.get("soc_g_per_kg") or 15.0)
    # Replace NaN with safe defaults
    if math.isnan(rainfall_mm): rainfall_mm = 1000.0
    if math.isnan(mean_temp_c): mean_temp_c = 28.0
    if math.isnan(soil_ph): soil_ph = 6.5
    if math.isnan(soc_g_per_kg): soc_g_per_kg = 15.0

    recommendations: list[dict[str, object]] = []
    price_forecasts_map: dict[str, dict[str, int]] = {}

    for rank, idx in enumerate(top_indices):
        crop_name = str(clf.classes_[idx])
        probability = normalised_probs[rank]

        # Yield prediction
        price_raw = float(prices.get(crop_name, 0.0))
        p_min = feature_min.get("price_vnd_per_kg", 0.0)
        p_max = feature_max.get("price_vnd_per_kg", 1.0)
        p_rng = p_max - p_min
        price_norm = 0.5 if p_rng == 0.0 else max(0.0, min(1.0, (price_raw - p_min) / p_rng))

        norm_reg = _normalise(raw, season, scaler_params, price_override=price_raw)
        row_reg: dict[str, float] = {c: norm_reg.get(c, 0.0) for c in reg_base_cols}
        if "price_vnd_per_kg" in row_reg:
            row_reg["price_vnd_per_kg"] = price_norm
        for col in crop_ohe_cols:
            row_reg[col] = 1.0 if col == f"crop_{crop_name}" else 0.0
        reg_input = pd.DataFrame([{c: row_reg.get(c, 0.0) for c in reg_cols}])
        predicted_yield = max(0.0, float(reg.predict(reg_input)[0]))

        expected_revenue = round(predicted_yield * 1_000.0 * price_raw)

        # Confidence labels
        if probability > 0.55:
            confidence = "high"
        elif probability > 0.35:
            confidence = "medium"
        else:
            confidence = "low"

        # Price forecast (6-month forward)
        price_forecast, price_trend = forecast_6months(crop_name, price_raw, supply_shock)
        price_forecasts_map[crop_name] = price_forecast

        # Fertiliser recommendation + split schedule
        fert = recommend_fertiliser(crop_name, rainfall_mm, mean_temp_c, soil_ph, soc_g_per_kg)
        fert["schedule"] = fertiliser_schedule(
            crop_name,
            {"ph": soil_ph, "soc_g_per_kg": soc_g_per_kg},
            forecast_risk,
            fert,
        )

        # Farming methods guidance
        methods = farming_methods_for_crop(
            crop=crop_name,
            soil_texture_class=str(raw.get("soil_texture_class", "loam")),
            season=season,
            forecast_rain_14d=forecast_rain_14d,
            forecast_rain_days=forecast_rain_days,
            forecast_mean_temp_c=forecast_temp_14d,
        )

        # Harvest timing with climate risk overlay
        try:
            harvest_timing = compute_harvest_timing(
                crop=crop_name,
                planting_date=_planting_date,
                province_key=province_key,
                lat=info.farm_lat,
                lon=info.farm_lon,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Harvest timing failed for %s: %s", crop_name, exc)
            harvest_timing = _fallback_harvest_timing(crop_name, _planting_date)

        recommendations.append(
            {
                "crop": crop_name,
                "probability": round(probability, 4),
                "predicted_yield_t_ha": round(predicted_yield, 2),
                "expected_revenue_vnd_per_ha": expected_revenue,
                "confidence": confidence,
                "price_forecast_vnd_per_tonne": price_forecast,
                "price_trend": price_trend,
                "fertiliser_recommendation": fert,
                "farming_methods": methods,
                "harvest_timing": harvest_timing,
            }
        )

    # 8. Farm plan (only if farm_size_ha provided)
    farm_plan: dict[str, object] | None = None
    if farm_size_ha is not None and farm_size_ha > 0:
        farm_plan = compute_farm_plan(
            recommendations,
            price_forecasts_map,
            farm_size_ha,
            is_high_risk,
        )

    return {
        "recommendations": recommendations,
        "farm_plan": farm_plan,
        "is_high_risk": is_high_risk,
        "raw_soil": {
            "ph": raw.get("ph"),
            "soc_g_per_kg": raw.get("soc_g_per_kg"),
            "nitrogen_cg_per_kg": raw.get("nitrogen_cg_per_kg"),
            "soil_texture_class": raw.get("soil_texture_class"),
            "cec_mmol_per_kg": raw.get("cec_mmol_per_kg"),
        },
        "data_source": data_source,
    }
