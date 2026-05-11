FROM python:3.11-slim

WORKDIR /app

# Install uv for fast, reproducible dependency installation
RUN pip install --no-cache-dir uv

# Dependency files first — layer cached unless pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock ./

# Source code + runtime data (models, prices, cached soil responses)
COPY src/ src/
COPY data/processed/ data/processed/
COPY data/raw/market/ data/raw/market/
COPY data/raw/gso/ data/raw/gso/
COPY data/raw/soilgrids/ data/raw/soilgrids/

# Install exact versions from the lock file; skip dev extras
RUN uv sync --no-dev --frozen

# Railway injects $PORT at runtime; default 8000 for local docker run
# CORS_ORIGINS=* lets the Vercel frontend reach this service.
# Override with a comma-separated list to lock down to specific origins.
ENV CORS_ORIGINS=*

CMD ["sh", "-c", "uv run uvicorn agri_sense.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
