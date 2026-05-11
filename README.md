# Agri-Sense

MVP crop recommendation system for Vietnamese farmers.

Click a location on the map → pick a season → get the top 3 recommended
crops with predicted yield (t/ha), expected revenue (VND/ha), and
confidence score.

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| ML models | XGBoost (classifier + regressor), sklearn fallback |
| Weather data | NASA POWER daily API (public, no key) |
| Soil data | SoilGrids 2.0 REST API (public, no key) |
| Vegetation index | Sentinel-2 L2A via Microsoft Planetary Computer (anonymous) |
| Frontend | Next.js 16, react-leaflet, TanStack Query, Tailwind |

---

## Quick Start

### 1. Prerequisites

```bash
# Python package manager
curl -Ls https://astral.sh/uv/install.sh | sh

# Node.js ≥ 20 (for the frontend)
# macOS: brew install node
# or: https://nodejs.org
```

### 2. Clone and install

```bash
git clone <repo-url>
cd agri-sense

# Create virtual env and install all Python dependencies
uv sync

# Configure environment (all defaults work for MVP — no API keys needed)
cp .env.example .env
```

> **macOS note — XGBoost:** if you see an XGBoost import warning, run
> `brew install libomp`. The pipeline falls back to scikit-learn automatically,
> so training still works without it.

### 3. Bootstrap the ML pipeline

This single command fetches data from the public APIs, engineers features,
trains both models, and prints a summary:

```bash
uv run python scripts/bootstrap.py
```

Expected output (times vary — Sentinel-2 NDVI fetches are the bottleneck):

```
──────────────────────────────────────────────────────────────
  STEP 1 / 3 — Build dataset (ingestion + feature engineering)
──────────────────────────────────────────────────────────────
...
  master.parquet:  270 rows × 22 columns

──────────────────────────────────────────────────────────────
  STEP 2 / 3 — Processing pipeline (clean → impute → normalise)
──────────────────────────────────────────────────────────────
...
  training.parquet: 263 rows × 28 columns
  NaN check: OK — no NaNs in numeric columns.

──────────────────────────────────────────────────────────────
  STEP 3 / 3 — Train models (XGBoost classifier + regressor)
──────────────────────────────────────────────────────────────
...
════════════════════════════════════════════════════════════════
  BOOTSTRAP COMPLETE
════════════════════════════════════════════════════════════════
  Total time:         12.3 min  (738 s)
  Dataset:            270 rows × 22 columns
  Training set:       263 rows × 28 columns
  Classifier acc:     0.812
  Regressor RMSE:     0.431 t/ha

  Artefacts saved to data/processed/
    classifier.json                          12.4 KB
    classifier_meta.json                      1.2 KB
    feature_columns.json                      0.8 KB
    regressor.json                           18.7 KB
    regressor_meta.json                       0.6 KB
    scaler.pkl                                2.1 KB
    scaler_params.json                        3.4 KB
    training.parquet                        124.0 KB
```

If `data/interim/master.parquet` already exists (e.g. re-running after a
code change), skip the slow API fetches:

```bash
uv run python scripts/bootstrap.py --skip-ingestion
```

### 4. Start the backend

```bash
uv run python scripts/serve.py
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### 5. Start the frontend

```bash
cd app
npm install
npm run dev
# → http://localhost:3000
```

---

## Running individual pipeline steps

| Step | Command |
|---|---|
| Build dataset only | `uv run python scripts/build_dataset.py` |
| Process pipeline only | `uv run python scripts/process.py` |
| Train models only | `uv run python scripts/train.py` |
| Demo a single prediction | `uv run python scripts/demo_predict.py` |

---

## Project layout

```
src/agri_sense/
  ingestion/   – fetch from NASA POWER, SoilGrids, Planetary Computer, GSO
  processing/  – feature engineering, imputation, normalisation
  models/      – XGBoost training + inference
  api/         – FastAPI routes (/provinces, /recommend, /health)
  utils/       – config, crop vocabulary, geo helpers

scripts/
  bootstrap.py   – one-shot setup: build → process → train
  build_dataset.py
  process.py
  train.py
  serve.py
  demo_*.py      – standalone API demos

app/             – Next.js 16 frontend (map + recommendation panel)

data/
  raw/         – source downloads (not committed)
  interim/     – intermediate outputs, e.g. master.parquet (not committed)
  processed/   – model artefacts + training data (not committed)

tests/           – pytest suite mirroring src/ layout
notebooks/       – exploratory analysis only (never imported by src/)
```

---

## Notes

- **Accuracy expectations**: the MVP dataset is small (~270 rows, 5 crops, 9 provinces).
  Classifier accuracy of 0.6–0.9 is normal; the goal is a working end-to-end pipeline,
  not production-grade accuracy.
- **Confidence scores**: the API uses `predict_proba` max as the confidence proxy.
  Scores < 0.5 trigger a warning in the response.
- **No paid data**: all data sources are public and require no API keys for the MVP scope.
