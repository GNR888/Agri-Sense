"""Tests for the gso_yields ingestion module."""

import pytest

from agri_sense.ingestion.gso_yields import load_yields

_EXPECTED_PROVINCES = {
    "Cần Thơ",
    "An Giang",
    "Đồng Tháp",
    "Sóc Trăng",
    "Đắk Lắk",
    "Lâm Đồng",
    "Gia Lai",
    "Thái Bình",
    "Nam Định",
}
_CRITICAL_COLS = ["province", "year", "season", "crop", "yield_tonnes_per_ha"]


def test_nonempty() -> None:
    df = load_yields()
    assert len(df) > 0


def test_no_nulls_in_critical_columns() -> None:
    df = load_yields()
    assert df[_CRITICAL_COLS].isna().sum().sum() == 0


def test_rice_yield_plausible_range() -> None:
    df = load_yields()
    rice_yield = df.loc[df["crop"] == "rice", "yield_tonnes_per_ha"]
    assert (rice_yield >= 3.0).all(), "Rice yield below 3 t/ha detected"
    assert (rice_yield <= 10.0).all(), "Rice yield above 10 t/ha detected"


def test_all_expected_provinces_present() -> None:
    df = load_yields()
    assert _EXPECTED_PROVINCES.issubset(set(df["province"].unique()))


def test_year_range() -> None:
    df = load_yields()
    assert int(df["year"].min()) >= 2018
    assert int(df["year"].max()) <= 2023


def test_area_and_production_positive() -> None:
    df = load_yields()
    assert (df["area_ha"] > 0).all()
    assert (df["production_tonnes"] > 0).all()
