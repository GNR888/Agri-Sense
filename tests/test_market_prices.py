"""Tests for the market_prices ingestion module."""

from agri_sense.ingestion.market_prices import load_prices

_EXPECTED_CROPS = {"rice_paddy", "coffee_green", "cashew_raw", "pepper_black", "maize"}
_CRITICAL_COLS = ["crop", "price_vnd_per_kg", "year"]


def test_nonempty() -> None:
    df = load_prices()
    assert len(df) > 0


def test_no_nulls_in_critical_columns() -> None:
    df = load_prices()
    assert df[_CRITICAL_COLS].isna().sum().sum() == 0


def test_prices_positive() -> None:
    df = load_prices()
    assert (df["price_vnd_per_kg"] > 0).all()


def test_all_expected_crops_present() -> None:
    df = load_prices()
    assert _EXPECTED_CROPS.issubset(set(df["crop"].unique()))


def test_rice_price_plausible_range() -> None:
    df = load_prices()
    rice = df.loc[df["crop"] == "rice_paddy", "price_vnd_per_kg"]
    assert (rice >= 5000).all(), "Rice paddy price below 5,000 VND/kg"
    assert (rice <= 10000).all(), "Rice paddy price above 10,000 VND/kg"
