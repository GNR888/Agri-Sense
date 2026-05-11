# Agri-Sense — Claude Context

## Project goal

Agri-Sense is an MVP crop recommendation system for Vietnamese farmers and
agricultural extension workers. A user clicks a location on an interactive
map of Vietnam, selects a planting season, and receives the top 3 recommended
crops with predicted yield (tonnes/ha) and a confidence score. The system
integrates public remote-sensing and climate APIs (no paid data for MVP) and
exposes results through a FastAPI backend consumed by a map-based frontend.

---

## Domain primer — Vietnam agriculture

**Rice seasons (ba vụ lúa):**
- **Đông Xuân** (Winter–Spring): Oct/Nov transplant → Jan/Feb harvest; highest yields, cool-dry weather
- **Hè Thu** (Summer–Autumn): Apr/May transplant → Jul/Aug harvest; hot and wet, higher pest pressure
- **Mùa** (Rainy season / Main season): Jun/Jul transplant → Oct/Nov harvest; traditional season, lower yield potential

**Regional crop profiles:**
- **Mekong River Delta** (ĐBSCL): Vietnam's rice bowl — 50 %+ of national rice output; also catfish, shrimp, coconut, and longân
- **Red River Delta** (ĐBSH): Intensive double/triple rice cropping; vegetables, maize
- **Central Highlands** (Tây Nguyên — Đắk Lắk, Lâm Đồng, Gia Lai): Robusta coffee (world's #2 exporter), black pepper, tea, avocado
- **South-East** (Đông Nam Bộ): Rubber, cashew, dragon fruit, industrial crops
- **North-Central Coast / Central Coast**: Cassava, groundnut, sesame; drought-prone

**Key soil concerns:**
- **Salinity intrusion** in the Mekong Delta (tidal + sea-level rise) — top constraint for rice south of Cần Thơ
- **Acid sulfate soils** widespread in delta lowlands — affects nutrient availability
- **Degraded ferralsols** in the Central Highlands after decades of coffee monoculture
- **Slope erosion** in northern uplands — terracing common for rice

---

## Data sources

| Layer | Source | Access |
|---|---|---|
| Weather (temp, rain, solar) | NASA POWER daily API | Public, no key |
| Soil properties (pH, texture, CEC, OC) | SoilGrids 2.0 REST API | Public, no key |
| NDVI / crop cover | Sentinel-2 L2A via Microsoft Planetary Computer | Anonymous STAC |
| Ground-truth yield | GSO (General Statistics Office of Vietnam) — scraped tabular data | Manual download for MVP |
| Market prices | Hardcoded lookup table (USD/tonne) | Static for MVP |

---

## Critical modeling notes

- **Imputation strategy**: use subset-mean imputation — group by `(province_code, soil_texture_class)` before computing fill values. Never use global mean; Vietnam's soil and climate variation is too large.
- **Feature normalisation**: normalise all continuous features to [0, 1] using per-feature min/max derived from training data only (no leakage). Store scaler params in `data/processed/scaler_params.json`.
- **Model choice**: XGBoost for both tasks — `XGBClassifier` (which crop, multi-class) and `XGBRegressor` (yield in t/ha). Use `early_stopping_rounds` to avoid overfitting on small data.
- **MVP philosophy**: chase a *working end-to-end pipeline*, not accuracy. A pipeline that returns a plausible answer for any clicked point beats a perfectly tuned model that crashes on edge cases.
- **Confidence proxy**: use the classifier's `predict_proba` max score as the displayed confidence. Flag to users when confidence < 0.5.

---

## Canonical crop vocabulary

All crop names throughout the codebase **must** use the canonical form defined in
`src/agri_sense/utils/crops.py`. Use `normalise_crop_name(name)` whenever reading
crop names from raw data or external input.

| Canonical name | Represents | Common aliases in raw data |
|---|---|---|
| `rice_paddy` | Paddy rice (all varieties) | `rice`, `paddy` |
| `coffee_green` | Green (unroasted) Robusta/Arabica bean | `coffee` |
| `cashew_raw` | Raw cashew nut | `cashew` |
| `pepper_black` | Dried black pepper | `pepper` |
| `maize` | Maize / field corn | `corn` |

---

## Coding conventions

- **Type hints everywhere** — no untyped function signatures; mypy strict mode
- **Formatter**: `ruff format` (line length 100) — run before every commit
- **All file I/O through `pathlib.Path`** — no raw string paths
- **No hardcoded paths outside `config.py`** — everything flows from `Config` (pydantic-settings, reads `.env`)
- **Packages**: all source under `src/agri_sense/`; sub-packages are `ingestion`, `processing`, `models`, `api`, `utils`
- **Tests**: `pytest` in `tests/`; mirror the `src/` layout
- **Notebooks**: exploratory only, never import from notebooks into src
