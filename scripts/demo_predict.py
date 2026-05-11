"""Demo: recommend crops for Cần Thơ (Đông Xuân) and Buôn Ma Thuột (annual)."""

import logging

from agri_sense.models.predict import recommend
from agri_sense.utils.geo import PROVINCES

_DEMO_QUERIES = [
    {
        "label": "Cần Thơ — Đông Xuân (Winter–Spring rice season)",
        "lat": PROVINCES["can_tho"].capital_lat,
        "lon": PROVINCES["can_tho"].capital_lon,
        "season": "Đông Xuân",
    },
    {
        "label": "Buôn Ma Thuột / Đắk Lắk — Annual (coffee/perennial season)",
        "lat": PROVINCES["dak_lak"].capital_lat,
        "lon": PROVINCES["dak_lak"].capital_lon,
        "season": "main",
    },
]


def _fmt_revenue(vnd: int | float) -> str:
    """Format VND value with thousands separator."""
    return f"{int(vnd):,} VND"


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")

    print("\n" + "=" * 70)
    print("AGRI-SENSE  —  CROP RECOMMENDATION DEMO")
    print("=" * 70)
    print("NOTE: Dataset is small (~200 rows across 12 provinces / 5 crops).")
    print("      Treat outputs as pipeline smoke-test, not agronomic advice.")
    print("=" * 70)

    for query in _DEMO_QUERIES:
        print(f"\n📍 {query['label']}")
        print(f"   coords=({query['lat']}, {query['lon']})  season={query['season']}")
        print("-" * 70)

        recs = recommend(
            lat=query["lat"],
            lon=query["lon"],
            season=query["season"],
            top_k=3,
        )

        if not recs:
            print("  (no recommendations returned)")
            continue

        for rank, rec in enumerate(recs, 1):
            prob_pct = f"{rec['probability'] * 100:.1f}%"
            conf_tag = f"[{rec['confidence']}]"
            print(
                f"  {rank}. {str(rec['crop']):<18} "
                f"prob={prob_pct:<7} {conf_tag:<8} "
                f"yield={rec['predicted_yield_t_ha']:.2f} t/ha  "
                f"revenue={_fmt_revenue(rec['expected_revenue_vnd_per_ha'])}/ha"
            )

    print("\n" + "=" * 70)
    print("Confidence thresholds: high >50%  medium >30%  low ≤30%")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
