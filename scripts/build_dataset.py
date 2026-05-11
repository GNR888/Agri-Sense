"""Entry point for building data/interim/master.parquet.

Usage:
    uv run python scripts/build_dataset.py          # skip if already exists
    uv run python scripts/build_dataset.py --force  # rebuild from scratch
"""

from agri_sense.processing.build_dataset import main

if __name__ == "__main__":
    main()
