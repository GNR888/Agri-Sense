const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type Confidence = 'high' | 'medium' | 'low';
export type PriceTrend = 'rising' | 'falling' | 'stable';
export type PlanningMode = 'today' | 'forecast';
export type DataSource = 'soilgrids' | 'farmer_measured' | 'mixed';
export type NutrientStatus = 'adequate' | 'deficient' | 'excess';

export interface SoilOverrides {
  ph?: number;
  soc_pct?: number;
  nitrogen_g_per_kg?: number;
  texture_class?: string;
}

export interface SoilHealthSummary {
  health_score: number;                           // 1–10
  nutrient_status: Record<string, NutrientStatus>;
  issues: string[];                               // top-2 plain-language fix suggestions
}

export interface SoilData {
  ph: number | null;
  soc_pct: number | null;            // organic carbon %
  nitrogen_g_per_kg: number | null;  // total N g/kg
  texture_class: string;
  cec_mmol_per_kg: number | null;
  salinity_risk: string;
  source: string;
  health: SoilHealthSummary;
}

export interface Province {
  key: string;
  name: string;
  name_vi: string;
  region: string;
  dominant_crop: string;
  lat: number;
  lon: number;
}

export interface SeasonInfo {
  season: string;
  region_type: string;
  in_transition: boolean;
  next_season: string | null;
  days_until_next_season: number | null;
  banner_message: string;
}

export interface PriceForecast {
  month_1: number;
  month_2: number;
  month_3: number;
  month_4: number;
  month_5: number;
  month_6: number;
}

export interface FertiliserApplication {
  timing: string;
  N_kg_per_ha: number;
  P2O5_kg_per_ha: number;
  K2O_kg_per_ha: number;
  method: string;
  product_examples: string[];
  warnings: string[];
}

export interface FertiliserSchedule {
  applications: FertiliserApplication[];
  total_N_kg_per_ha: number;
  total_P2O5_kg_per_ha: number;
  total_K2O_kg_per_ha: number;
  general_notes: string[];
}

export interface FertiliserRecommendation {
  N_kg_per_ha: number;
  P2O5_kg_per_ha: number;
  K2O_kg_per_ha: number;
  lime_tonnes_per_ha: number;
  notes: string[];
  schedule: FertiliserSchedule | null;
}

export interface IrrigationStage {
  stage: string;
  days: string;
  moisture_target: string;
  frequency: string;
  note: string;
}

export interface FarmingMethods {
  land_preparation: string[];
  planting: string[];
  water_management: string[];
  pest_watch: string[];
  irrigation_schedule: IrrigationStage[];
}

export interface CropAllocation {
  crop: string;
  area_ha: number;
  share_pct: number;
  expected_revenue_vnd: number;
}

export interface FarmPlan {
  farm_size_ha: number;
  reserve_ha: number;
  plantable_ha: number;
  allocations: CropAllocation[];
  total_expected_revenue_vnd: number;
  weather_hedge_applied: boolean;
  notes: string[];
}

export interface ClimateRisk {
  risk: string;
  severity: 'high' | 'medium' | 'low';
  action: string;
}

export interface HarvestTiming {
  estimated_planting_date: string;
  earliest_harvest_date: string;
  latest_harvest_date: string;
  optimal_harvest_window: string;       // "YYYY-MM-DD to YYYY-MM-DD"
  recommended_harvest_date: string;
  reason: string;
  climate_risks: ClimateRisk[];
  harvest_tips: string[];
  data_basis: string;
}

export interface CropRecommendation {
  crop: string;
  probability: number;
  predicted_yield_t_ha: number;
  expected_revenue_vnd_per_ha: number;
  confidence: Confidence;
  price_forecast_vnd_per_tonne: PriceForecast;
  price_trend: PriceTrend;
  fertiliser_recommendation: FertiliserRecommendation;
  farming_methods: FarmingMethods;
  harvest_timing: HarvestTiming;
}

export interface TransitionInfo {
  next_season: string;
  days_until: number;
  recommendations: CropRecommendation[];
}

export interface LocationInfo {
  lat: number;
  lon: number;
  nearest_province: string;
}

export interface RecommendResponse {
  location: LocationInfo;
  season_info: SeasonInfo;
  recommendations: CropRecommendation[];
  transition: TransitionInfo | null;
  farm_plan: FarmPlan | null;
  is_high_risk: boolean;
  warnings: string[];
  soil_data: SoilData;
  data_source: DataSource;
  data_freshness: DataFreshness;
}

export interface DataFreshnessLayer {
  source: string;
  is_live: boolean;
  fetched_at: string | null;
  horizon_days: number | null;
  vintage: string | null;
  latest_image_date: string | null;
  note: string;
}

export interface DataFreshness {
  weather_forecast: DataFreshnessLayer;
  soil_data: DataFreshnessLayer;
  market_prices: DataFreshnessLayer;
  ndvi: DataFreshnessLayer;
}

export interface RecommendRequest {
  lat: number;
  lon: number;
  mode: PlanningMode;
  target_month?: number | null;
  top_k?: number;
  farm_size_ha?: number | null;
  soil_overrides?: SoilOverrides | null;
}

export async function fetchProvinces(): Promise<Province[]> {
  const res = await fetch(`${BASE_URL}/provinces`);
  if (!res.ok) throw new Error(`Failed to fetch provinces: ${res.status}`);
  return res.json() as Promise<Province[]>;
}

export async function fetchSoilData(lat: number, lon: number): Promise<SoilData> {
  const res = await fetch(`${BASE_URL}/soil?lat=${lat}&lon=${lon}`);
  if (!res.ok) throw new Error(`Failed to fetch soil data: ${res.status}`);
  return res.json() as Promise<SoilData>;
}

export interface MarketHistoricalPoint {
  month: string;
  price: number;
  source: string;
}

export interface MarketForecastPoint {
  month: string;
  price: number;
  lower_bound: number;
  upper_bound: number;
  confidence: 'high' | 'medium' | 'low';
}

export interface MarketPricesResponse {
  crop: string;
  currency: string;
  unit: string;
  historical: MarketHistoricalPoint[];
  forecast: MarketForecastPoint[];
  volatility_index: number;
  volatility_label: string;
  key_drivers: string[];
  best_selling_months: string[];
  avoid_selling_months: string[];
}

export async function fetchMarketPrices(
  crop: string,
  monthsBack = 12,
  monthsForward = 6,
): Promise<MarketPricesResponse> {
  const res = await fetch(
    `${BASE_URL}/market/prices?crop=${encodeURIComponent(crop)}&months_back=${monthsBack}&months_forward=${monthsForward}`,
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText })) as { detail?: string };
    throw new Error(err.detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<MarketPricesResponse>;
}

export async function fetchRecommendations(req: RecommendRequest): Promise<RecommendResponse> {
  const res = await fetch(`${BASE_URL}/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ top_k: 3, ...req }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText })) as { detail?: string };
    throw new Error(err.detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<RecommendResponse>;
}
