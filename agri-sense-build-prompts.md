# Agri-Sense Build Runbook

Sequential prompts for Claude Code. Paste each one in order. Wait until each completes successfully and you've verified the checkpoint before moving on.

**Setup once before starting:**
1. Create empty folder: `mkdir agri-sense && cd agri-sense`
2. Initialise git: `git init`
3. Open in your editor and run `claude` in that directory

---

## Prompt 1 — Repo scaffold + CLAUDE.md + tooling

```
We're building Agri-Sense, an MVP crop recommendation system for Vietnamese
farmers. End goal: a farmer (or extension worker) clicks a location on a map
of Vietnam, picks a season, and gets the top 3 recommended crops with
predicted yield and confidence.

Architecture overview (build this scaffold now, no logic yet):

agri-sense/
├── CLAUDE.md
├── README.md
├── pyproject.toml            # use uv or poetry, your pick — uv preferred
├── .gitignore
├── .env.example
├── data/
│   ├── raw/.gitkeep
│   ├── interim/.gitkeep
│   └── processed/.gitkeep
├── src/agri_sense/
│   ├── __init__.py
│   ├── ingestion/__init__.py
│   ├── processing/__init__.py
│   ├── models/__init__.py
│   ├── api/__init__.py
│   └── utils/__init__.py
├── app/                      # leave empty for now, dashboard comes later
├── notebooks/.gitkeep
├── tests/__init__.py
└── scripts/.gitkeep

Tasks:
1. Create the structure above.
2. Set up pyproject.toml with these deps: requests, httpx, pandas, numpy,
   scikit-learn, xgboost, pyarrow, fastapi, uvicorn, python-dotenv,
   pydantic, geopandas, shapely, rasterio, pystac-client, planetary-computer
   (we'll use Microsoft Planetary Computer for Sentinel-2 — no auth headache
   for an MVP). Dev deps: pytest, ruff, mypy, ipykernel.
3. .gitignore should cover python, data/raw, data/interim, data/processed,
   .env, .venv, __pycache__, .ipynb_checkpoints.
4. Write CLAUDE.md with the following sections — DO NOT skip this, future
   sessions depend on it:
   - Project goal (one paragraph)
   - Domain primer for Vietnam agriculture (rice seasons: Đông Xuân /
     Hè Thu / Mùa, regional crops: rice in Mekong & Red River deltas,
     coffee/pepper in Central Highlands, key soil concerns including
     salinity in the Mekong Delta)
   - Data sources we use (NASA POWER for weather, SoilGrids 2.0 for soil,
     Sentinel-2 via Planetary Computer for NDVI, GSO for ground-truth
     yields, hardcoded market prices for MVP)
   - Critical modeling notes: subset-mean imputation (group by province +
     soil texture class, NOT global mean), normalise continuous features
     to 0-1, use XGBoost for both classifier (which crop) and regressor
     (yield), don't chase accuracy on MVP — chase a working pipeline
   - Coding conventions: type hints everywhere, ruff format, all I/O
     through pathlib, no hardcoded paths outside config
5. README.md: a short "what this is + how to run" — keep it minimal, we'll
   expand later.
6. Create a config module at src/agri_sense/utils/config.py with a Config
   pydantic settings class that reads from .env (data dirs, API keys
   placeholder for later).
7. Verify everything imports: `uv run python -c "import agri_sense"`

Don't write any business logic yet. This prompt is purely scaffolding.
Show me the final tree and confirm the import works.
```

**✅ Checkpoint:** `uv run python -c "import agri_sense"` runs with no error. CLAUDE.md exists and has the domain primer.

---

## Prompt 2 — NASA POWER weather ingestion

```
Implement src/agri_sense/ingestion/nasa_power.py.

NASA POWER API gives free historical daily weather for any lat/lon globally.
No auth required. Endpoint:
https://power.larc.nasa.gov/api/temporal/daily/point

Required behavior:
- Function `fetch_daily_weather(lat: float, lon: float, start: date, end: date) -> pd.DataFrame`
- Pull these parameters: T2M (mean temp), T2M_MAX, T2M_MIN, PRECTOTCORR
  (precipitation), RH2M (humidity), ALLSKY_SFC_SW_DWN (solar radiation),
  WS2M (wind)
- community=AG (agroclimatology)
- Return a DataFrame indexed by date, columns named clearly (temp_mean_c,
  temp_max_c, temp_min_c, precip_mm, humidity_pct, solar_mj, wind_ms)
- Cache responses to data/raw/nasa_power/{lat}_{lon}_{start}_{end}.parquet
  so repeated calls don't hit the API. Cache hit should skip the request.
- Handle missing values: NASA POWER uses -999 for missing — convert to NaN.
- Add basic retry with backoff on HTTP errors (use httpx + tenacity, add
  tenacity to pyproject if needed).
- Type hints everywhere. Logging via stdlib logging at INFO.

Add a tests/test_nasa_power.py with one integration test that pulls 30 days
for a Mekong Delta coordinate (lat=10.0341, lon=105.7880 — Cần Thơ) and
asserts the DataFrame is non-empty, has the expected columns, no -999s,
and dates are continuous.

Add scripts/demo_weather.py that I can run to see it working: pulls 1 year
of weather for Cần Thơ and prints summary stats.

After implementing, run the demo script and show me the output.
```

**✅ Checkpoint:** `uv run python scripts/demo_weather.py` prints a year of weather stats. A parquet file appears in `data/raw/nasa_power/`.

---

## Prompt 3 — SoilGrids ingestion

```
Implement src/agri_sense/ingestion/soilgrids.py.

SoilGrids 2.0 (ISRIC) provides global soil property maps at 250m resolution.
REST API: https://rest.isric.org/soilgrids/v2.0/properties/query

Required behavior:
- Function `fetch_soil_properties(lat: float, lon: float) -> dict`
- Pull these properties at depth 0-30cm (the agricultural root zone):
  phh2o (pH in water), soc (soil organic carbon), nitrogen, sand, silt,
  clay, cec (cation exchange capacity), bdod (bulk density)
- Use the "mean" value from the API response (it returns multiple
  statistics — mean, Q0.05, median, etc.)
- Note SoilGrids returns values in mapped units (e.g., pH × 10) — convert
  to natural units in the return dict and document the conversion.
- Return a flat dict: {"ph": 5.8, "soc_g_per_kg": 12.3, "nitrogen_cg_per_kg":
  150, "sand_pct": 45, "silt_pct": 30, "clay_pct": 25, "cec_mmol_per_kg":
  90, "bulk_density_kg_per_dm3": 1.35}
- Cache to data/raw/soilgrids/{lat}_{lon}.json
- Add a derived field `soil_texture_class` using the USDA soil texture
  triangle from sand/silt/clay percentages. Implement this as a helper
  function — there's a standard 12-class system (sand, loamy sand, sandy
  loam, loam, silt loam, silt, sandy clay loam, clay loam, silty clay
  loam, sandy clay, silty clay, clay). This class is critical later for
  the subset-mean imputation grouping.
- Same retry/cache/logging pattern as nasa_power.

Add tests/test_soilgrids.py: integration test for Cần Thơ — assert all
expected keys present, pH between 3 and 10, percentages sum roughly to 100,
texture class is one of the valid 12.

Add scripts/demo_soil.py that prints soil for Cần Thơ + a Central Highlands
coffee location (lat=12.6797, lon=108.0377 — Buôn Ma Thuột) so we can see
they're meaningfully different.

Run the demo and show output.
```

**✅ Checkpoint:** Two locations show clearly different soil profiles (Mekong is likely high clay, acidic; Central Highlands is volcanic basalt-derived, different texture).

---

## Prompt 4 — Sentinel-2 NDVI ingestion

```
Implement src/agri_sense/ingestion/sentinel.py.

Use Microsoft Planetary Computer's STAC API to fetch Sentinel-2 L2A
imagery and compute NDVI. No auth needed for read access via
planetary-computer SDK (already in pyproject).

Required behavior:
- Function `fetch_ndvi_timeseries(lat: float, lon: float, start: date,
  end: date, buffer_m: int = 500) -> pd.DataFrame`
- Search the sentinel-2-l2a collection in the date range, filtered to
  cloud cover < 20%.
- For each scene, sample a buffer_m × buffer_m window around the point.
- Compute NDVI = (B08 - B04) / (B08 + B04), mean over the window.
- Mask cloud/shadow pixels using the SCL band (exclude SCL values 3, 8,
  9, 10, 11 = clouds/shadows/snow).
- Return DataFrame with columns: date, ndvi_mean, ndvi_std, valid_pixel_pct.
- Skip scenes where valid_pixel_pct < 50%.
- Cache the resulting timeseries to data/raw/sentinel/{lat}_{lon}_{start}_{end}.parquet.
- This one's slower than the others — add a progress indicator (tqdm) and
  log how many scenes were found vs used.

Add scripts/demo_ndvi.py: pull NDVI for Cần Thơ for the last 12 months,
print the dataframe, and save a quick matplotlib plot to data/raw/sentinel/cantho_ndvi.png
(add matplotlib to pyproject dev deps if not there).

Tests: a unit test for the NDVI math itself with a tiny synthetic array
(don't make a slow integration test required for CI — mark it with
@pytest.mark.slow if you do add an integration test).

Run the demo. The plot should clearly show seasonal vegetation cycles
(rice growth phases visible as NDVI peaks).
```

**✅ Checkpoint:** NDVI plot shows visible peaks corresponding to rice growing seasons. If it looks flat/noisy, debug before moving on — this signal is real and important.

---

## Prompt 5 — GSO yields + market prices (the ground truth + demand layer)

```
Two ingestion modules in this prompt — they're both small.

A) src/agri_sense/ingestion/gso_yields.py

For the MVP, we hardcode a curated dataset of Vietnamese crop yields by
province by year, sourced from GSO/FAOSTAT public data. Don't try to
scrape gso.gov.vn — it's painful and not necessary for MVP.

Create a CSV at data/raw/gso/yields.csv with this schema:
province,year,season,crop,area_ha,production_tonnes,yield_tonnes_per_ha

Populate it with realistic figures for at least:
- Provinces: Cần Thơ, An Giang, Đồng Tháp, Sóc Trăng (Mekong Delta);
  Đắk Lắk, Lâm Đồng, Gia Lai (Central Highlands); Thái Bình, Nam Định
  (Red River Delta) — 9 provinces total.
- Years: 2018–2023.
- Crops + seasons:
  - Rice: Đông Xuân, Hè Thu, Mùa (where applicable)
  - Coffee: annual (single "main" season)
  - Cashew: annual
  - Pepper: annual
  - Maize: Đông Xuân, Hè Thu

Use FAOSTAT national averages as a baseline and apply realistic regional
variation (e.g., Mekong Delta rice yields ~6 t/ha, Red River Delta ~5.5
t/ha, Central Highlands coffee ~2.5 t/ha green coffee). Mark all rows with
a 'source' column = 'curated_mvp_v1' so we know it's not raw scraped data.

Then write a function `load_yields() -> pd.DataFrame` that reads this CSV
into a typed DataFrame.

B) src/agri_sense/ingestion/market_prices.py

Hardcoded recent market prices for the MVP. Create
data/raw/market/prices.csv:
crop,price_vnd_per_kg,year,source

Populate with realistic 2023–2024 farmgate prices (rice paddy ~6,500-7,500
VND/kg, coffee ~50,000-65,000 VND/kg green, cashew ~30,000 VND/kg,
pepper ~70,000 VND/kg, maize ~7,000 VND/kg).

Function `load_prices() -> pd.DataFrame`.

Add a TODO at the top of market_prices.py noting that v2 should scrape
agromonitor.vn or partner with cooperatives for live data.

Tests: load both, assert non-empty, assert no nulls in critical columns,
assert yields are in plausible ranges (rice yield between 3 and 10 t/ha
sanity check).

No demo script needed for these — they're trivially loadable.
```

**✅ Checkpoint:** Both CSVs exist and load. The yields CSV should have ~100+ rows once you account for province × year × season × crop combinations.

---

## Prompt 6 — Joining it all: the master dataset builder

```
This is the spine of the project. Implement src/agri_sense/processing/build_dataset.py.

Goal: produce a single training DataFrame where each row = (province,
year, season, crop) and columns include all features needed for
modeling.

Pipeline:
1. Load yields (from gso_yields). This defines our row universe.
2. For each unique province, look up a representative lat/lon (create a
   helper src/agri_sense/utils/geo.py with a dict of province -> (lat, lon)
   centroids for the 9 provinces — use real coordinates for province
   capitals).
3. For each (province, year, season) row: compute the relevant date
   window for that season:
     - Đông Xuân: Nov(year-1) to Apr(year)
     - Hè Thu: May to Aug
     - Mùa: Sep to Dec
     - "annual" (coffee/cashew/pepper): full calendar year
   Pull NASA POWER data for that window and aggregate:
     - total precipitation (mm)
     - mean temp, max temp, min temp
     - growing degree days (base 10°C for most crops — implement a
       gdd(temp_series, base=10) helper)
     - mean solar radiation
     - mean humidity
     - precip variability (CV of monthly totals)
4. Pull SoilGrids for that lat/lon (province-level — same soil for all
   rows of that province; cache will make this cheap).
5. Pull Sentinel-2 NDVI for that window and aggregate:
     - peak NDVI
     - days from window-start to peak
     - mean NDVI
   Note: Sentinel-2 only goes back to 2017 reliably — for earlier years,
   leave NDVI as NaN and we'll handle in imputation.
6. Join market price (latest available) by crop.
7. Output: data/interim/master.parquet

Make this idempotent — if data/interim/master.parquet exists, skip unless
--force flag passed. Add a CLI via argparse.

Add tqdm progress bars on the per-row iteration. This script will take
several minutes the first time (Sentinel-2 is slow), seconds on rerun
(everything caches).

Add scripts/build_dataset.py that just calls into this module.

After implementation, run it and show me:
- The final DataFrame's shape
- df.head()
- df.dtypes
- A summary of NaN counts per column

Don't impute or normalise yet — that's the next prompt. We want to see
the raw joined data first.
```

**✅ Checkpoint:** `data/interim/master.parquet` exists. Shape is roughly (100–300, 25+). NaN counts make sense — NDVI columns will have NaNs for pre-2017 years; soil columns should be fully populated.

---

## Prompt 7 — Cleaning, imputation, normalisation

```
Implement src/agri_sense/processing/clean.py, impute.py, normalise.py.

A) clean.py
- Function `clean(df: pd.DataFrame) -> pd.DataFrame`
- Drop rows with missing target (yield_tonnes_per_ha)
- Cast types properly (categorical for province, season, crop; float for
  numeric)
- Clip obvious outliers (e.g., yield > 15 t/ha for rice is suspicious —
  log a warning and clip to plausible bounds per crop)
- Add an 'is_outlier_clipped' flag column

B) impute.py — THE IMPORTANT ONE. Read CLAUDE.md's modeling notes again.
- Function `impute(df: pd.DataFrame) -> pd.DataFrame`
- Implement subset-mean imputation:
  - For each missing numeric value, group by (province, soil_texture_class)
    and take the mean of available values in that group.
  - If that group has no available values, fall back to (region,
    soil_texture_class) — define region as: Mekong Delta = {Cần Thơ,
    An Giang, Đồng Tháp, Sóc Trăng}, Central Highlands = {Đắk Lắk,
    Lâm Đồng, Gia Lai}, Red River Delta = {Thái Bình, Nam Định}.
  - If still no value, fall back to global mean.
  - Add a column per imputed feature: '{feature}_imputed' = bool flag.
- Categorical missingness: fill with 'unknown' and warn.
- Log how many cells were imputed at each fallback level.

C) normalise.py
- Function `normalise(df: pd.DataFrame, fit: bool = True, scaler_path:
  Path | None = None) -> tuple[pd.DataFrame, dict]`
- Min-max scale all continuous features to 0-1.
- One-hot encode season (Đông Xuân / Hè Thu / Mùa / annual).
- One-hot encode crop (this is what the classifier predicts, so it's a
  target — be careful: crop should ONLY be one-hot when used as feature
  for the yield regressor, NOT when used as target for the classifier;
  return a dict with two views: 'classifier_view' and 'regressor_view').
- Save the fitted scaler/encoder to data/processed/scaler.pkl so we can
  apply the same transform at inference time.

D) Wire it all into a single processing pipeline:
src/agri_sense/processing/pipeline.py
- Function `run_pipeline() -> None` that reads master.parquet, runs clean
  → impute → normalise, writes data/processed/training.parquet and
  data/processed/scaler.pkl.

E) scripts/process.py — CLI that calls run_pipeline.

Tests:
- Unit test for the subset-mean imputation with a tiny synthetic df
  that has known missing values and checks the right group-mean is used
  AND the fallback chain works.
- Test that normalise + inverse gives back the original (within float
  tolerance).

Run the pipeline. Show me data/processed/training.parquet shape and
confirm no NaNs remain in numeric columns.
```

**✅ Checkpoint:** `data/processed/training.parquet` exists, no NaNs in numeric features, scaler.pkl saved. The imputation log clearly shows how many values were filled at each fallback level.

---

## Prompt 8 — Models: classifier + regressor

```
Implement src/agri_sense/models/.

A) crop_classifier.py
- Class `CropClassifier` wrapping XGBoost's XGBClassifier.
- Predicts: crop (multi-class) given province soil + climate + season +
  market prices.
- Features: all numeric features from training.parquet EXCEPT crop and
  yield_tonnes_per_ha. Include season one-hot.
- Methods: fit(X, y), predict(X), predict_proba(X), save(path),
  load(path).
- Use stratified train/test split (test_size=0.2, random_state=42).
- Hyperparams: keep simple for MVP — n_estimators=200, max_depth=6,
  learning_rate=0.1, eval_metric='mlogloss'. Don't tune yet.
- Log training metrics: accuracy, top-3 accuracy (since we'll
  recommend top-3), confusion matrix as a printed table.

B) yield_regressor.py
- Class `YieldRegressor` wrapping XGBRegressor.
- Predicts: yield_tonnes_per_ha given everything including crop one-hot
  (because yield is conditional on the crop being grown).
- train/test split (test_size=0.2).
- Hyperparams: n_estimators=300, max_depth=6, learning_rate=0.1,
  eval_metric='rmse'.
- Log: RMSE, MAE, R² on test set. Also log per-crop RMSE so we can see
  which crops the model handles well/poorly.

C) train.py
- Function `train_all() -> None` that loads training.parquet, trains both
  models, saves them to data/processed/classifier.json and
  data/processed/regressor.json (XGBoost native format).
- Also save feature_columns.json so we know what column order to use at
  inference.

D) predict.py
- Function `recommend(lat: float, lon: float, season: str, top_k: int = 3)
  -> list[dict]`
- This is the inference path the API will call.
- Steps:
  1. Find nearest province from lat/lon.
  2. Build a single-row feature vector by running the same ingestion
     pipeline for that location + season (use cached data where
     possible — first call for a new location will be slow).
  3. Apply the saved scaler/encoder.
  4. Run classifier → get top_k crops with probabilities.
  5. For each candidate crop, run regressor → get predicted yield.
  6. Compute expected revenue = predicted_yield × area_assumed (1 ha) ×
     market_price.
  7. Return list of dicts: [{"crop": "rice", "probability": 0.62,
     "predicted_yield_t_ha": 5.8, "expected_revenue_vnd_per_ha":
     40_600_000, "confidence": "high|medium|low"}, ...]
  8. Confidence rule of thumb: high if probability > 0.5, medium >
     0.3, else low.

E) scripts/train.py — CLI to run train_all().
F) scripts/demo_predict.py — CLI that runs recommend() for Cần Thơ in
   Đông Xuân and Buôn Ma Thuột annually, prints results nicely.

Tests:
- Smoke test: load training.parquet, fit a tiny model, predict, assert
  shape.
- Test recommend() returns valid structure (don't assert specific
  predictions — too brittle).

After training, show me:
- Classifier accuracy + top-3 accuracy
- Regressor RMSE per crop
- Output of demo_predict.py

Important: the dataset is small (~hundreds of rows). Don't be alarmed if
classifier accuracy is modest. The pipeline working end-to-end is the
goal. Note the limits clearly in the output.
```

**✅ Checkpoint:** `demo_predict.py` outputs sensible recommendations. Cần Thơ in Đông Xuân should likely return rice as top crop. Buôn Ma Thuột should likely return coffee. If it doesn't, the pipeline still works — but flag it for investigation.

---

## Prompt 9 — FastAPI service

```
Implement src/agri_sense/api/main.py.

FastAPI app with these endpoints:

GET /health
  → {"status": "ok", "models_loaded": true}

POST /recommend
  Body: {"lat": float, "lon": float, "season": "Đông Xuân"|"Hè Thu"|
         "Mùa"|"annual", "top_k": int = 3}
  Response: {
    "location": {"lat": ..., "lon": ..., "nearest_province": "..."},
    "season": "...",
    "recommendations": [
      {"crop": "rice", "probability": 0.62, "predicted_yield_t_ha": 5.8,
       "expected_revenue_vnd_per_ha": 40600000, "confidence": "high"},
      ...
    ],
    "warnings": ["..."]   // e.g., "predicted outside training distribution"
  }

GET /provinces
  → list of supported provinces with their centroid lat/lon (so the
  frontend can show pins).

Implementation notes:
- Use pydantic models for request/response.
- Load models once at startup using FastAPI lifespan context manager.
- Add CORS middleware allowing localhost:3000 for the dashboard.
- Add basic logging middleware that logs each request + duration.
- If /recommend is called for a lat/lon outside Vietnam's bounding box
  (roughly lat 8.5–23.5, lon 102–110), return 400 with a clear error.
- If model files don't exist, /health returns models_loaded: false and
  /recommend returns 503.

Add scripts/serve.py that runs uvicorn on port 8000 with reload=True.

Test by: running the server and curl-ing /health and /recommend with a
Cần Thơ payload. Show me the curl output.
```

**✅ Checkpoint:** `curl http://localhost:8000/recommend` with a real payload returns the same structure as the demo script.

---

## Prompt 10 — Dashboard (Next.js + Leaflet)

```
Build the farmer-facing dashboard in app/.

Stack: Next.js 14 (App Router), TypeScript, Tailwind, react-leaflet for
the map, react-query (TanStack Query) for API calls.

Setup in app/:
- Initialise a Next.js app (TypeScript, Tailwind, App Router, no src dir,
  no ESLint customisation)
- Install: react-leaflet, leaflet, @types/leaflet, @tanstack/react-query

Pages/components:

app/page.tsx — single-page dashboard, three sections vertically:

1. Header: "Agri-Sense Vietnam" + subtitle "Crop recommendations for
   Vietnamese farmers, powered by satellite, soil, and climate data."

2. Main content, two-column layout (stacks on mobile):
   LEFT (60%): Leaflet map of Vietnam, centred at lat=16, lon=107, zoom=6.
     - Markers for the 9 supported provinces, fetched from GET /provinces.
     - Click a marker OR click anywhere on the map → set selected location
       (lat/lon). Show a different-coloured marker at clicked point.
   RIGHT (40%): Recommendation panel.
     - Season selector (radio buttons or dropdown): Đông Xuân, Hè Thu,
       Mùa, Annual.
     - "Get recommendations" button — disabled until location + season
       are selected.
     - On click, call POST /recommend, show loading state.
     - Render the top 3 recommendations as cards, each with:
       - Crop name (with Vietnamese name if obvious — e.g., "Rice (Lúa)")
       - Probability as a horizontal bar
       - Predicted yield (t/ha)
       - Expected revenue (VND/ha, formatted with thousands separators)
       - Confidence badge (green/yellow/red)
     - Show any warnings from the API at the bottom of the panel.

3. Footer: "MVP demo — predictions are illustrative. Not a substitute
   for local agronomic advice."

API client: app/lib/api.ts with typed functions matching the FastAPI
schemas. Read API base URL from NEXT_PUBLIC_API_URL env var, default
http://localhost:8000.

Styling: clean, neutral, agricultural feel — use Tailwind's emerald/stone
palette, not the default blue. Cards have subtle shadows. Mobile-first
responsive.

Add a README in app/ explaining how to run: npm install && npm run dev
on port 3000.

Show me the final result by:
1. Listing the file structure under app/
2. Printing app/page.tsx
3. Printing app/lib/api.ts
```

**✅ Checkpoint:** Both servers running (`uvicorn` on 8000, `next dev` on 3000), you can click a Mekong Delta location, pick Đông Xuân, hit "Get recommendations", and see rice as a top result.

---

## Prompt 11 — End-to-end demo script + bootstrap

```
Final cleanup prompt. Two tasks:

A) scripts/bootstrap.py — a single command that runs the entire pipeline
   from scratch on a fresh checkout:
   1. Build the dataset (calls processing.build_dataset)
   2. Run the processing pipeline (clean → impute → normalise)
   3. Train both models
   4. Print a summary: dataset shape, classifier accuracy, regressor RMSE,
      where artifacts were saved.

   This is what someone runs after `git clone` to get a working system.
   Add a --skip-ingestion flag in case data/raw/ is already populated.

B) Update README.md with a proper "Quick Start" section:
   ```
   # Backend
   uv sync
   uv run python scripts/bootstrap.py
   uv run python scripts/serve.py

   # Frontend (separate terminal)
   cd app
   npm install
   npm run dev
   ```
   Plus a "Demo" section showing the screenshot/curl output, and a
   "Limitations" section honestly listing: small training set, hardcoded
   market prices, only 9 provinces, NDVI only for 2017+, MVP not for
   production farmer use.

   Include a "What's next" section listing the v2 work: live market
   price scraper, expand to all 63 provinces, add salinity feature for
   Mekong, swap XGBoost for LSTM/GNN once dataset is large enough,
   add Vietnamese language UI, add field-level (not just province-level)
   recommendations.

C) Make a final pass: run `ruff format && ruff check --fix` across the
   repo, run all tests, fix anything broken.

Show me:
- Full output of running scripts/bootstrap.py
- The updated README.md
- Test suite results
```

**✅ Final checkpoint:** Fresh `bootstrap.py` run produces models. Both servers run. Dashboard works end-to-end. README accurately describes the system.

---

## Notes on running this efficiently

- **Use `/clear` between prompts in Claude Code.** Each prompt is a fresh task. Carrying context across all 11 prompts will bloat and confuse the agent. The `CLAUDE.md` from prompt 1 carries the persistent context.
- **Review diffs before approving.** Don't auto-accept everything. Especially in prompts 6, 7, 8 where business logic lives.
- **If a prompt's checkpoint fails**, fix it before moving on. Don't paper over a broken upstream module — it'll bite you three prompts later.
- **Commit after each successful prompt.** `git commit -m "prompt N: <module>"`. If a later prompt makes a mess, you can revert cleanly.
- **Realistic time estimate:** 1–2 evenings per prompt for prompts 1–5 (mostly waiting on data + API responses), 2–4 evenings each for 6–10. Call it ~3 weeks of evenings for the full MVP if you're verifying carefully. Faster if you're skimming.

## When you'll need to come back to me

- **After prompt 6 if NaN counts look weird** — could be a coordinate issue, a date-window bug, or Sentinel cloud cover masking too aggressively.
- **After prompt 8 if the model is recommending coffee for the Mekong Delta** — that's a feature engineering or training data issue, not a model issue. Worth debugging together.
- **Before prompt 10 if you want to change the dashboard tech** — Next.js is a solid default but if you'd rather Streamlit (simpler, Python-only) or plain HTML, say so and I'll rewrite that prompt.
