"""FastAPI application for the Agri-Sense crop recommendation service."""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agri_sense.utils.geo import PROVINCES

logger = logging.getLogger(__name__)

# Vietnam geographic bounds (WGS-84 bounding box)
_VN_LAT: tuple[float, float] = (8.5, 23.5)
_VN_LON: tuple[float, float] = (102.0, 110.0)

_models_loaded: bool = False


def _try_load_models() -> bool:
    """Attempt to load all model artefacts into the predict module's singletons."""
    global _models_loaded
    try:
        from agri_sense.models.predict import _load_artefacts  # noqa: PLC0415

        _load_artefacts()
        _models_loaded = True
        logger.info("Model artefacts loaded successfully.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model artefacts could not be loaded: %s", exc)
        _models_loaded = False
    return _models_loaded


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    await asyncio.to_thread(_try_load_models)
    yield


app = FastAPI(title="Agri-Sense", version="0.3.0", lifespan=lifespan)

_cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000").strip()
_CORS_ORIGINS: list[str] = ["*"] if _cors_raw == "*" else [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1_000
    logger.info(
        "%s %s → %d  %.1f ms",
        request.method,
        request.url.path,
        response.status_code,
        ms,
    )
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nan_to_none(v: object, scale: float = 1.0, ndigits: int = 2) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f * scale, ndigits)


def _derive_salinity_risk(province_key: str) -> str:
    info = PROVINCES.get(province_key)
    if not info:
        return "Unknown"
    r = info.region.lower()
    if "mekong" in r:
        return "Moderate — Mekong Delta province"
    if "red river" in r:
        return "Low — Red River Delta"
    if "coast" in r or "central" in r:
        return "Low — coastal influence"
    return "Very Low"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    models_loaded: bool


_VALID_TEXTURE_CLASSES = frozenset({
    "sand", "loamy sand", "sandy loam", "loam", "silt loam", "silt",
    "sandy clay loam", "clay loam", "silty clay loam", "sandy clay", "silty clay", "clay",
})


class SoilOverrides(BaseModel):
    ph: float | None = Field(default=None, ge=3.0, le=10.0, description="Measured soil pH")
    soc_pct: float | None = Field(default=None, ge=0.0, le=20.0, description="Organic carbon (%)")
    nitrogen_g_per_kg: float | None = Field(default=None, ge=0.0, le=10.0, description="Total N (g/kg)")
    texture_class: str | None = Field(default=None, description="USDA texture class")


class SoilHealthSummary(BaseModel):
    health_score: float
    nutrient_status: dict[str, str]
    issues: list[str]


class SoilData(BaseModel):
    ph: float | None
    soc_pct: float | None                # organic carbon %
    nitrogen_g_per_kg: float | None      # total N g/kg
    texture_class: str
    cec_mmol_per_kg: float | None
    salinity_risk: str
    source: str = "SoilGrids 2.0"
    health: SoilHealthSummary


class RecommendRequest(BaseModel):
    lat: float
    lon: float
    mode: Literal["today", "forecast"] = "today"
    target_month: int | None = Field(default=None, ge=1, le=12, description="1–12; required when mode='forecast'.")
    top_k: int = Field(default=3, ge=1, le=5)
    farm_size_ha: float | None = Field(default=None, gt=0, description="Total farm area (ha). Required for farm plan.")
    soil_overrides: SoilOverrides | None = Field(default=None, description="Farmer-measured values that override SoilGrids.")


class LocationInfo(BaseModel):
    lat: float
    lon: float
    nearest_province: str


class SeasonInfo(BaseModel):
    season: str
    region_type: str
    in_transition: bool
    next_season: str | None
    days_until_next_season: int | None
    banner_message: str


class PriceForecast(BaseModel):
    month_1: int
    month_2: int
    month_3: int
    month_4: int
    month_5: int
    month_6: int


class FertiliserApplication(BaseModel):
    timing: str
    N_kg_per_ha: int
    P2O5_kg_per_ha: int
    K2O_kg_per_ha: int
    method: str
    product_examples: list[str]
    warnings: list[str]


class FertiliserSchedule(BaseModel):
    applications: list[FertiliserApplication]
    total_N_kg_per_ha: int
    total_P2O5_kg_per_ha: int
    total_K2O_kg_per_ha: int
    general_notes: list[str]


class FertiliserRecommendation(BaseModel):
    N_kg_per_ha: int
    P2O5_kg_per_ha: int
    K2O_kg_per_ha: int
    lime_tonnes_per_ha: float
    notes: list[str]
    schedule: FertiliserSchedule | None = None


class IrrigationStage(BaseModel):
    stage: str
    days: str
    moisture_target: str
    frequency: str
    note: str


class FarmingMethods(BaseModel):
    land_preparation: list[str]
    planting: list[str]
    water_management: list[str]
    pest_watch: list[str]
    irrigation_schedule: list[IrrigationStage]


class CropAllocation(BaseModel):
    crop: str
    area_ha: float
    share_pct: int
    expected_revenue_vnd: int


class FarmPlan(BaseModel):
    farm_size_ha: float
    reserve_ha: float
    plantable_ha: float
    allocations: list[CropAllocation]
    total_expected_revenue_vnd: int
    weather_hedge_applied: bool
    notes: list[str]


class ClimateRisk(BaseModel):
    risk: str
    severity: str
    action: str


class HarvestTiming(BaseModel):
    estimated_planting_date: str
    earliest_harvest_date: str
    latest_harvest_date: str
    optimal_harvest_window: str
    recommended_harvest_date: str
    reason: str
    climate_risks: list[ClimateRisk]
    harvest_tips: list[str]
    data_basis: str


class CropRecommendation(BaseModel):
    crop: str
    probability: float
    predicted_yield_t_ha: float
    expected_revenue_vnd_per_ha: int
    confidence: str
    price_forecast_vnd_per_tonne: PriceForecast
    price_trend: Literal["rising", "falling", "stable"]
    fertiliser_recommendation: FertiliserRecommendation
    farming_methods: FarmingMethods
    harvest_timing: HarvestTiming


class TransitionInfo(BaseModel):
    next_season: str
    days_until: int
    recommendations: list[CropRecommendation]


class DataFreshnessLayer(BaseModel):
    source: str
    is_live: bool
    fetched_at: str | None = None        # ISO-8601 UTC timestamp; None for static sources
    horizon_days: int | None = None      # forecast horizon (weather only)
    vintage: str | None = None           # data vintage year (soil only)
    latest_image_date: str | None = None # most recent scene date (NDVI only)
    note: str                            # human-readable status line


class DataFreshness(BaseModel):
    weather_forecast: DataFreshnessLayer
    soil_data: DataFreshnessLayer
    market_prices: DataFreshnessLayer
    ndvi: DataFreshnessLayer


class RecommendResponse(BaseModel):
    location: LocationInfo
    season_info: SeasonInfo
    recommendations: list[CropRecommendation]
    transition: TransitionInfo | None
    farm_plan: FarmPlan | None
    is_high_risk: bool
    warnings: list[str]
    soil_data: SoilData
    data_source: Literal["soilgrids", "farmer_measured", "mixed"]
    data_freshness: DataFreshness


class ProvinceOut(BaseModel):
    key: str
    name: str
    name_vi: str
    region: str
    dominant_crop: str
    lat: float
    lon: float


class MarketHistoricalPoint(BaseModel):
    month: str   # "YYYY-MM"
    price: int   # VND/tonne
    source: str


class MarketForecastPoint(BaseModel):
    month: str
    price: int
    lower_bound: int
    upper_bound: int
    confidence: str  # "high" | "medium" | "low"


class MarketPricesResponse(BaseModel):
    crop: str
    currency: str
    unit: str
    historical: list[MarketHistoricalPoint]
    forecast: list[MarketForecastPoint]
    volatility_index: float
    volatility_label: str
    key_drivers: list[str]
    best_selling_months: list[str]
    avoid_selling_months: list[str]


# ---------------------------------------------------------------------------
# Recommendation-building helpers
# ---------------------------------------------------------------------------

def _build_harvest_timing(raw: dict) -> HarvestTiming:
    return HarvestTiming(
        estimated_planting_date=str(raw["estimated_planting_date"]),
        earliest_harvest_date=str(raw["earliest_harvest_date"]),
        latest_harvest_date=str(raw["latest_harvest_date"]),
        optimal_harvest_window=str(raw["optimal_harvest_window"]),
        recommended_harvest_date=str(raw["recommended_harvest_date"]),
        reason=str(raw["reason"]),
        climate_risks=[
            ClimateRisk(
                risk=str(cr["risk"]),
                severity=str(cr["severity"]),
                action=str(cr["action"]),
            )
            for cr in raw.get("climate_risks", [])
        ],
        harvest_tips=[str(t) for t in raw.get("harvest_tips", [])],
        data_basis=str(raw.get("data_basis", "")),
    )


def _build_fertiliser_schedule(raw: dict) -> FertiliserSchedule:
    return FertiliserSchedule(
        applications=[
            FertiliserApplication(
                timing=str(a["timing"]),
                N_kg_per_ha=int(a["N_kg_per_ha"]),
                P2O5_kg_per_ha=int(a["P2O5_kg_per_ha"]),
                K2O_kg_per_ha=int(a["K2O_kg_per_ha"]),
                method=str(a["method"]),
                product_examples=list(a["product_examples"]),
                warnings=list(a["warnings"]),
            )
            for a in raw["applications"]
        ],
        total_N_kg_per_ha=int(raw["total_N_kg_per_ha"]),
        total_P2O5_kg_per_ha=int(raw["total_P2O5_kg_per_ha"]),
        total_K2O_kg_per_ha=int(raw["total_K2O_kg_per_ha"]),
        general_notes=list(raw["general_notes"]),
    )


def _build_crop_recommendations(raw_recs: list[dict]) -> list[CropRecommendation]:
    result: list[CropRecommendation] = []
    for r in raw_recs:
        pf = r["price_forecast_vnd_per_tonne"]
        fr = r["fertiliser_recommendation"]
        fm = r["farming_methods"]
        result.append(
            CropRecommendation(
                crop=str(r["crop"]),
                probability=float(r["probability"]),
                predicted_yield_t_ha=float(r["predicted_yield_t_ha"]),
                expected_revenue_vnd_per_ha=int(r["expected_revenue_vnd_per_ha"]),
                confidence=str(r["confidence"]),
                price_forecast_vnd_per_tonne=PriceForecast(
                    month_1=int(pf["month_1"]),
                    month_2=int(pf["month_2"]),
                    month_3=int(pf["month_3"]),
                    month_4=int(pf["month_4"]),
                    month_5=int(pf["month_5"]),
                    month_6=int(pf["month_6"]),
                ),
                price_trend=r["price_trend"],  # type: ignore[arg-type]
                fertiliser_recommendation=FertiliserRecommendation(
                    N_kg_per_ha=int(fr["N_kg_per_ha"]),
                    P2O5_kg_per_ha=int(fr["P2O5_kg_per_ha"]),
                    K2O_kg_per_ha=int(fr["K2O_kg_per_ha"]),
                    lime_tonnes_per_ha=float(fr["lime_tonnes_per_ha"]),
                    notes=list(fr["notes"]),
                    schedule=_build_fertiliser_schedule(fr["schedule"]) if fr.get("schedule") else None,
                ),
                farming_methods=FarmingMethods(
                    land_preparation=list(fm["land_preparation"]),
                    planting=list(fm["planting"]),
                    water_management=list(fm["water_management"]),
                    pest_watch=list(fm["pest_watch"]),
                    irrigation_schedule=[
                        IrrigationStage(
                            stage=str(s["stage"]),
                            days=str(s["days"]),
                            moisture_target=str(s["moisture_target"]),
                            frequency=str(s["frequency"]),
                            note=str(s["note"]),
                        )
                        for s in fm["irrigation_schedule"]
                    ],
                ),
                harvest_timing=_build_harvest_timing(r["harvest_timing"]),
            )
        )
    return result


def _build_soil_data(raw_soil: dict[str, object], province_key: str) -> SoilData:
    from agri_sense.recommendations.soil_summary import soil_health_summary  # noqa: PLC0415

    health_dict = soil_health_summary(raw_soil)
    return SoilData(
        ph=_nan_to_none(raw_soil.get("ph"), ndigits=2),
        soc_pct=_nan_to_none(raw_soil.get("soc_g_per_kg"), scale=0.1, ndigits=2),
        nitrogen_g_per_kg=_nan_to_none(raw_soil.get("nitrogen_cg_per_kg"), scale=0.01, ndigits=2),
        texture_class=str(raw_soil.get("soil_texture_class") or "loam"),
        cec_mmol_per_kg=_nan_to_none(raw_soil.get("cec_mmol_per_kg"), ndigits=1),
        salinity_risk=_derive_salinity_risk(province_key),
        health=SoilHealthSummary(**health_dict),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", models_loaded=_models_loaded)


@app.get("/provinces", response_model=list[ProvinceOut])
async def list_provinces() -> list[ProvinceOut]:
    return [
        ProvinceOut(
            key=key,
            name=info.name,
            name_vi=info.name_vi,
            region=info.region,
            dominant_crop=info.dominant_crop,
            lat=info.capital_lat,
            lon=info.capital_lon,
        )
        for key, info in PROVINCES.items()
    ]


@app.get("/soil", response_model=SoilData)
async def get_soil(lat: float, lon: float) -> SoilData:
    """Return SoilGrids soil properties and health summary for a lat/lon point."""
    if not (_VN_LAT[0] <= lat <= _VN_LAT[1] and _VN_LON[0] <= lon <= _VN_LON[1]):
        raise HTTPException(
            status_code=400,
            detail=f"Coordinates ({lat}, {lon}) are outside Vietnam's bounding box.",
        )
    from agri_sense.ingestion.soilgrids import fetch_soil_properties  # noqa: PLC0415
    from agri_sense.models.predict import _nearest_province  # noqa: PLC0415

    province_key = _nearest_province(lat, lon)
    province_info = PROVINCES[province_key]
    raw_soil: dict[str, object] = await asyncio.to_thread(
        fetch_soil_properties, province_info.farm_lat, province_info.farm_lon
    )
    return _build_soil_data(raw_soil, province_key)


# ---------------------------------------------------------------------------
# Data-freshness helpers
# ---------------------------------------------------------------------------

_OPEN_METEO_CACHE_TTL_S = 6 * 3600


def _build_data_freshness(farm_lat: float, farm_lon: float) -> DataFreshness:
    import json  # noqa: PLC0415

    from agri_sense.utils.config import config  # noqa: PLC0415

    # --- Weather (Open-Meteo) ---
    cache = config.raw_dir / "open_meteo" / f"{farm_lat:.4f}_{farm_lon:.4f}_forecast.json"
    weather_fetched_at: str | None = None
    weather_is_live = False
    weather_note = "not yet fetched"

    if cache.exists():
        try:
            cached = json.loads(cache.read_text())
            fetched_ts = float(cached.get("_fetched_at", 0))
            age_s = time.time() - fetched_ts
            dt = datetime.datetime.fromtimestamp(fetched_ts, tz=datetime.timezone.utc)
            weather_fetched_at = dt.strftime("%Y-%m-%dT%H:%MZ")
            if age_s < _OPEN_METEO_CACHE_TTL_S:
                weather_is_live = True
                hours = int(age_s // 3600)
                minutes = int((age_s % 3600) // 60)
                weather_note = f"updated {hours}h {minutes}m ago" if hours else f"updated {minutes}m ago"
            else:
                weather_note = "cache stale — will refresh on next request"
        except Exception:  # noqa: BLE001
            weather_note = "cache unreadable"

    # --- NDVI (Sentinel-2) — estimate latest image date from cache if present ---
    sentinel_dir = config.raw_dir / "sentinel"
    ndvi_image_date: str | None = None
    if sentinel_dir.exists():
        parquets = sorted(sentinel_dir.glob(f"{farm_lat:.4f}_{farm_lon:.4f}_*.parquet"), reverse=True)
        if parquets:
            # Mtime of the most recent cache file approximates the latest fetch
            try:
                mtime = parquets[0].stat().st_mtime
                dt2 = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
                ndvi_image_date = dt2.strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                pass
    if ndvi_image_date is None:
        # Conservative estimate: Sentinel-2 has a 5-day revisit; cloud cover adds lag
        ndvi_image_date = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()

    return DataFreshness(
        weather_forecast=DataFreshnessLayer(
            source="Open-Meteo",
            is_live=weather_is_live,
            fetched_at=weather_fetched_at,
            horizon_days=14,
            note=weather_note,
        ),
        soil_data=DataFreshnessLayer(
            source="SoilGrids 2.0",
            is_live=False,
            vintage="2023",
            note="Updated annually",
        ),
        market_prices=DataFreshnessLayer(
            source="Hardcoded GSO baseline + seasonal model",
            is_live=False,
            note="Live price scraping coming in v2",
        ),
        ndvi=DataFreshnessLayer(
            source="Sentinel-2 via Planetary Computer",
            is_live=False,
            latest_image_date=ndvi_image_date,
            note=f"Latest scene est. {ndvi_image_date} — 5–14 day revisit",
        ),
    )


# ---------------------------------------------------------------------------
# Market price constants
# ---------------------------------------------------------------------------

_BASE_PRICES_VND_PER_KG: dict[str, float] = {
    "rice_paddy":   7_200.0,
    "coffee_green": 63_000.0,
    "cashew_raw":   31_500.0,
    "pepper_black": 75_000.0,
    "maize":        7_300.0,
}

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_MARKET_KEY_DRIVERS: dict[str, list[str]] = {
    "rice_paddy": [
        "Seasonal post-harvest surplus expected Mar–Apr (Đông Xuân)",
        "Export demand from Philippines historically peaks Jan–Feb",
        "El Niño conditions may reduce Mekong Delta yield by 8–12%",
        "Salinity intrusion in delta provinces elevates production risk Feb–Apr",
    ],
    "coffee_green": [
        "Global Robusta supply tightens Jun–Aug; Vietnam export window opens",
        "Brazil frost risk in Jul–Aug historically supports global benchmark prices",
        "Central Highlands harvest glut Oct–Dec creates short-term surplus",
        "VND depreciation risk can increase export revenue in domestic terms",
    ],
    "cashew_raw": [
        "Peak harvest Apr–Jun drives seasonal surplus; farm-gate prices soften",
        "Côte d'Ivoire and India compete on export markets in Q2–Q3",
        "US and EU import demand strongest in Q4 (holiday season)",
        "Processing bottlenecks at Bình Phước facilities support farm-gate floor price",
    ],
    "pepper_black": [
        "Global supply tightness from reduced Cambodia and Indonesia output",
        "Export demand peaks Jan–Mar; buyers stock ahead of Lunar New Year",
        "Central Highlands drought risk reduces flowering set in dry season",
        "India import demand provides year-round price floor support",
    ],
    "maize": [
        "Domestic feed-grade demand peaks Jan–Mar (poultry and aquaculture cycle)",
        "Import competition from US and Argentina limits price upside",
        "Ethanol feedstock crossover ties price ceiling to fuel market movements",
        "Flood risk in Red River Delta can depress Jun–Aug crop quality",
    ],
}


def _add_months_offset(base_year: int, base_month: int, offset: int) -> tuple[int, int]:
    total = base_month - 1 + offset
    return base_year + total // 12, total % 12 + 1


@app.get("/market/prices", response_model=MarketPricesResponse)
async def market_prices(
    crop: str = Query(..., description="Canonical crop name"),
    months_back: int = Query(default=12, ge=1, le=24),
    months_forward: int = Query(default=6, ge=1, le=12),
) -> MarketPricesResponse:
    if crop not in _BASE_PRICES_VND_PER_KG:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown crop '{crop}'. Valid: {sorted(_BASE_PRICES_VND_PER_KG.keys())}",
        )

    from agri_sense.market.price_forecast import SEASONAL_MULTIPLIERS  # noqa: PLC0415

    base_kg = _BASE_PRICES_VND_PER_KG[crop]
    multipliers = SEASONAL_MULTIPLIERS.get(crop, {m: 1.0 for m in range(1, 13)})

    today = datetime.date.today()
    cur_y, cur_m = today.year, today.month

    def _price(month: int) -> int:
        return round(base_kg * multipliers.get(month, 1.0) * 1_000)

    # Historical: months_back months ending with the current month (inclusive)
    historical: list[MarketHistoricalPoint] = []
    for k in range(-(months_back - 1), 1):
        y, m = _add_months_offset(cur_y, cur_m, k)
        historical.append(MarketHistoricalPoint(month=f"{y:04d}-{m:02d}", price=_price(m), source="hardcoded_gso"))

    # Compute volatility from historical price changes
    hist_prices = [h.price for h in historical]
    if len(hist_prices) >= 2:
        changes = [abs(hist_prices[i] - hist_prices[i - 1]) for i in range(1, len(hist_prices))]
        mean_price = sum(hist_prices) / len(hist_prices)
        n = len(changes)
        mean_chg = sum(changes) / n
        std_chg = (sum((c - mean_chg) ** 2 for c in changes) / n) ** 0.5
        vix = std_chg / mean_price if mean_price > 0 else 0.0
    else:
        vix = 0.0

    if vix < 0.08:
        vlabel = "Low"
    elif vix <= 0.15:
        vlabel = "Moderate"
    else:
        vlabel = "High"

    band_factor = max(vix * 2.0, 0.05)  # minimum ±5 % confidence band
    conf_str = "high" if vix < 0.08 else ("medium" if vix <= 0.15 else "low")

    # Forecast: months_forward months after current
    forecast: list[MarketForecastPoint] = []
    for k in range(1, months_forward + 1):
        y, m = _add_months_offset(cur_y, cur_m, k)
        price = _price(m)
        forecast.append(MarketForecastPoint(
            month=f"{y:04d}-{m:02d}",
            price=price,
            lower_bound=round(price * (1 - band_factor)),
            upper_bound=round(price * (1 + band_factor)),
            confidence=conf_str,
        ))

    # Best/avoid months from seasonal multipliers
    sorted_by_mult = sorted(multipliers.items(), key=lambda x: x[1], reverse=True)
    best_months = [_MONTH_NAMES[m - 1] for m, _ in sorted_by_mult[:2]]
    avoid_months = [_MONTH_NAMES[m - 1] for m, _ in sorted_by_mult[-2:]]

    return MarketPricesResponse(
        crop=crop,
        currency="VND",
        unit="per_tonne",
        historical=historical,
        forecast=forecast,
        volatility_index=round(vix, 4),
        volatility_label=vlabel,
        key_drivers=_MARKET_KEY_DRIVERS.get(crop, []),
        best_selling_months=best_months,
        avoid_selling_months=avoid_months,
    )


@app.post("/recommend", response_model=RecommendResponse)
async def recommend_endpoint(req: RecommendRequest) -> RecommendResponse:
    # Validate Vietnam bounding box
    if not (_VN_LAT[0] <= req.lat <= _VN_LAT[1] and _VN_LON[0] <= req.lon <= _VN_LON[1]):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Coordinates ({req.lat}, {req.lon}) are outside Vietnam's bounding box "
                f"(lat {_VN_LAT[0]}–{_VN_LAT[1]}, lon {_VN_LON[0]}–{_VN_LON[1]})."
            ),
        )

    if req.mode == "forecast" and req.target_month is None:
        raise HTTPException(
            status_code=422,
            detail="target_month (1–12) is required when mode='forecast'.",
        )

    # Attempt lazy recovery if startup load failed
    if not _models_loaded and not await asyncio.to_thread(_try_load_models):
        raise HTTPException(
            status_code=503,
            detail="Model artefacts are unavailable. Run scripts/train.py first.",
        )

    from agri_sense.models.predict import _nearest_province, recommend  # noqa: PLC0415
    from agri_sense.utils.seasons import (  # noqa: PLC0415
        PROVINCE_REGION_TYPE,
        resolve_season,
        season_for_month,
    )

    province_key = _nearest_province(req.lat, req.lon)
    province = PROVINCES[province_key]

    # Resolve season from mode
    if req.mode == "today":
        ref_date = datetime.date.today()
        resolution = resolve_season(province_key, ref_date, province.name_vi)
    else:
        # forecast: probe the 15th of the target month to find its season
        ref_date = datetime.date(2024, req.target_month, 15)  # type: ignore[arg-type]
        resolution = resolve_season(
            province_key, ref_date, province.name_vi, forecast_mode=True
        )

    season_internal = "main" if resolution.season == "annual" else resolution.season

    # Serialise soil overrides to a plain dict for the sync recommend() call
    soil_overrides_dict: dict[str, object] | None = (
        req.soil_overrides.model_dump(exclude_none=True) if req.soil_overrides else None
    )

    # Compute expected planting date for harvest timing
    today = datetime.date.today()
    if req.mode == "today":
        planting_date = today + datetime.timedelta(days=7)
    else:
        # Forecast mode: next occurrence of target_month's 15th
        candidate = datetime.date(today.year, req.target_month, 15)  # type: ignore[arg-type]
        if candidate < today:
            candidate = datetime.date(today.year + 1, req.target_month, 15)  # type: ignore[arg-type]
        planting_date = candidate

    # Primary inference
    try:
        result = await asyncio.to_thread(
            recommend,
            req.lat,
            req.lon,
            season_internal,
            req.top_k,
            req.farm_size_ha,
            soil_overrides_dict,
            planting_date,
        )
    except Exception as exc:
        logger.exception("Inference failed for (%s, %s): %s", req.lat, req.lon, exc)
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}") from exc

    raw_recs: list[dict] = result["recommendations"]  # type: ignore[assignment]
    farm_plan_data: dict | None = result.get("farm_plan")  # type: ignore[assignment]
    is_high_risk: bool = bool(result.get("is_high_risk", False))
    raw_soil: dict[str, object] = result.get("raw_soil", {})  # type: ignore[assignment]
    data_source: str = str(result.get("data_source", "soilgrids"))

    # Transition inference — only for "today" mode within 14-day window
    transition: TransitionInfo | None = None
    if req.mode == "today" and resolution.in_transition and resolution.next_season and resolution.days_until_next_season is not None:
        next_season_internal = "main" if resolution.next_season == "annual" else resolution.next_season
        try:
            transition_planting_date = today + datetime.timedelta(
                days=resolution.days_until_next_season + 7
            )
            t_result = await asyncio.to_thread(
                recommend,
                req.lat,
                req.lon,
                next_season_internal,
                req.top_k,
                req.farm_size_ha,
                soil_overrides_dict,
                transition_planting_date,
            )
            transition = TransitionInfo(
                next_season=resolution.next_season,
                days_until=resolution.days_until_next_season,
                recommendations=_build_crop_recommendations(t_result["recommendations"]),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Transition inference failed: %s", exc)

    # Derive warnings
    warnings: list[str] = []
    if raw_recs:
        top_prob: float = float(raw_recs[0]["probability"])
        if top_prob < 0.5:
            warnings.append(
                f"Low model confidence (top probability {top_prob:.0%}) — "
                "this location/season may be outside the training distribution."
            )
    if any(r["confidence"] == "low" for r in raw_recs):
        warnings.append(
            "One or more recommendations have very low confidence (< 35%); "
            "treat yield estimates with caution."
        )
    if is_high_risk:
        warnings.append(
            "Extreme weather forecast (>3 heavy-rain days or heat anomaly) detected — "
            "price estimates include a supply-shock uplift."
        )

    # Build typed farm plan
    farm_plan: FarmPlan | None = None
    if farm_plan_data is not None:
        farm_plan = FarmPlan(
            farm_size_ha=float(farm_plan_data["farm_size_ha"]),
            reserve_ha=float(farm_plan_data["reserve_ha"]),
            plantable_ha=float(farm_plan_data["plantable_ha"]),
            allocations=[
                CropAllocation(
                    crop=str(a["crop"]),
                    area_ha=float(a["area_ha"]),
                    share_pct=int(a["share_pct"]),
                    expected_revenue_vnd=int(a["expected_revenue_vnd"]),
                )
                for a in farm_plan_data["allocations"]
            ],
            total_expected_revenue_vnd=int(farm_plan_data["total_expected_revenue_vnd"]),
            weather_hedge_applied=bool(farm_plan_data["weather_hedge_applied"]),
            notes=list(farm_plan_data["notes"]),
        )

    return RecommendResponse(
        location=LocationInfo(lat=req.lat, lon=req.lon, nearest_province=province.name),
        season_info=SeasonInfo(
            season=resolution.season,
            region_type=resolution.region_type,
            in_transition=resolution.in_transition,
            next_season=resolution.next_season,
            days_until_next_season=resolution.days_until_next_season,
            banner_message=resolution.banner_message,
        ),
        recommendations=_build_crop_recommendations(raw_recs),
        transition=transition,
        farm_plan=farm_plan,
        is_high_risk=is_high_risk,
        warnings=warnings,
        soil_data=_build_soil_data(raw_soil, province_key),
        data_source=data_source,  # type: ignore[arg-type]
        data_freshness=_build_data_freshness(province.farm_lat, province.farm_lon),
    )
