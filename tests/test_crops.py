"""Tests for crop name normalisation."""

import pytest

from agri_sense.utils.crops import CANONICAL_CROPS, normalise_crop_name


# --- normalise_crop_name ---


@pytest.mark.parametrize(
    "variant,expected",
    [
        # Short forms from yields.csv
        ("rice", "rice_paddy"),
        ("coffee", "coffee_green"),
        ("cashew", "cashew_raw"),
        ("pepper", "pepper_black"),
        ("maize", "maize"),
        # Canonical forms pass through unchanged
        ("rice_paddy", "rice_paddy"),
        ("coffee_green", "coffee_green"),
        ("cashew_raw", "cashew_raw"),
        ("pepper_black", "pepper_black"),
        # Whitespace and case tolerance
        ("  Rice  ", "rice_paddy"),
        ("MAIZE", "maize"),
        ("Corn", "maize"),
        ("Paddy", "rice_paddy"),
    ],
)
def test_normalise_known_variants(variant: str, expected: str) -> None:
    assert normalise_crop_name(variant) == expected


def test_normalise_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown crop name"):
        normalise_crop_name("durian")


# --- CANONICAL_CROPS ---


def test_canonical_crops_is_frozenset() -> None:
    assert isinstance(CANONICAL_CROPS, frozenset)


def test_all_canonical_names_normalise_to_themselves() -> None:
    for crop in CANONICAL_CROPS:
        assert normalise_crop_name(crop) == crop


# --- Integration: loaders emit only canonical names ---


def test_load_yields_crop_column_is_canonical() -> None:
    from agri_sense.ingestion.gso_yields import load_yields

    df = load_yields()
    non_canonical = set(df["crop"].unique()) - CANONICAL_CROPS
    assert not non_canonical, f"Non-canonical crop names in yields: {non_canonical}"


def test_load_prices_crop_column_is_canonical() -> None:
    from agri_sense.ingestion.market_prices import load_prices

    df = load_prices()
    non_canonical = set(df["crop"].unique()) - CANONICAL_CROPS
    assert not non_canonical, f"Non-canonical crop names in prices: {non_canonical}"
