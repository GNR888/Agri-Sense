"""Tests for agri_sense.utils.seasons — season detection and resolution."""
from __future__ import annotations

import datetime

import pytest

from agri_sense.utils.seasons import (
    PROVINCE_REGION_TYPE,
    SEASON_WINDOWS,
    SeasonResolution,
    _in_window,
    resolve_season,
    season_for_month,
)


class TestInWindow:
    def test_simple_range_inside(self) -> None:
        d = datetime.date(2024, 5, 15)
        assert _in_window(d, (3, 16), (7, 31)) is True

    def test_simple_range_outside(self) -> None:
        d = datetime.date(2024, 8, 1)
        assert _in_window(d, (3, 16), (7, 31)) is False

    def test_simple_range_boundary_start(self) -> None:
        assert _in_window(datetime.date(2024, 3, 16), (3, 16), (7, 31)) is True

    def test_simple_range_boundary_end(self) -> None:
        assert _in_window(datetime.date(2024, 7, 31), (3, 16), (7, 31)) is True

    def test_wrap_around_dec_side(self) -> None:
        # Đông Xuân: Nov 15 – Mar 15; Dec should be inside
        assert _in_window(datetime.date(2024, 12, 1), (11, 15), (3, 15)) is True

    def test_wrap_around_jan_side(self) -> None:
        # Jan should be inside
        assert _in_window(datetime.date(2025, 1, 20), (11, 15), (3, 15)) is True

    def test_wrap_around_boundary_start(self) -> None:
        assert _in_window(datetime.date(2024, 11, 15), (11, 15), (3, 15)) is True

    def test_wrap_around_boundary_end(self) -> None:
        assert _in_window(datetime.date(2025, 3, 15), (11, 15), (3, 15)) is True

    def test_wrap_around_outside(self) -> None:
        # Aug should not be inside Đông Xuân
        assert _in_window(datetime.date(2024, 8, 15), (11, 15), (3, 15)) is False


class TestSeasonForMonth:
    @pytest.mark.parametrize("month,expected", [
        (1, "Đông Xuân"), (2, "Đông Xuân"), (3, "Đông Xuân"),
        (4, "Hè Thu"),    (7, "Hè Thu"),
        (8, "Mùa"),       (10, "Mùa"),
        (11, "Đông Xuân"), (12, "Đông Xuân"),
    ])
    def test_mekong_delta(self, month: int, expected: str) -> None:
        assert season_for_month("mekong_delta", month) == expected

    @pytest.mark.parametrize("month,expected", [
        (1, "Đông Xuân"), (5, "Đông Xuân"),
        (6, "Mùa"),       (10, "Mùa"),
        (11, "Đông Xuân"), (12, "Đông Xuân"),
    ])
    def test_red_river_delta(self, month: int, expected: str) -> None:
        assert season_for_month("red_river_delta", month) == expected

    def test_central_highlands_all_annual(self) -> None:
        for m in range(1, 13):
            assert season_for_month("central_highlands", m) == "annual"


class TestResolveSeasonToday:
    def test_mekong_may(self) -> None:
        r = resolve_season("can_tho", datetime.date(2025, 5, 15), "Cần Thơ")
        assert r.season == "Hè Thu"
        assert r.region_type == "mekong_delta"
        assert not r.in_transition
        assert r.next_season is None
        assert "Hè Thu" in r.banner_message
        assert "Cần Thơ" in r.banner_message

    def test_transition_window(self) -> None:
        # Mar 8 is 8 days before Hè Thu starts Mar 16
        r = resolve_season("can_tho", datetime.date(2025, 3, 8), "Cần Thơ")
        assert r.season == "Đông Xuân"
        assert r.in_transition is True
        assert r.next_season == "Hè Thu"
        assert r.days_until_next_season == 8

    def test_no_transition_outside_window(self) -> None:
        # Mar 1 is 15 days before Hè Thu — just outside the 14-day window
        r = resolve_season("can_tho", datetime.date(2025, 3, 1), "Cần Thơ")
        assert not r.in_transition

    def test_central_highlands_never_transitions(self) -> None:
        # Central Highlands has only one window (annual); no transition possible
        r = resolve_season("dak_lak", datetime.date(2025, 3, 10), "Đắk Lắk")
        assert r.season == "annual"
        assert not r.in_transition

    def test_banner_contains_month_name(self) -> None:
        r = resolve_season("can_tho", datetime.date(2025, 8, 15), "Cần Thơ")
        assert "August" in r.banner_message


class TestResolveSeasonForecast:
    def test_forecast_mode_no_transition(self) -> None:
        r = resolve_season(
            "can_tho",
            datetime.date(2024, 3, 8),  # Would be a transition day in today mode
            "Cần Thơ",
            forecast_mode=True,
        )
        assert not r.in_transition
        assert r.next_season is None

    def test_forecast_banner_wording(self) -> None:
        r = resolve_season("can_tho", datetime.date(2024, 9, 15), "Cần Thơ", forecast_mode=True)
        assert "Forecast for" in r.banner_message
        assert "historical" in r.banner_message


class TestProvinceMapping:
    def test_all_provinces_have_region_type(self) -> None:
        from agri_sense.utils.geo import PROVINCES

        for key in PROVINCES:
            assert key in PROVINCE_REGION_TYPE, f"{key!r} missing from PROVINCE_REGION_TYPE"

    def test_region_types_are_valid(self) -> None:
        valid = set(SEASON_WINDOWS)
        for key, region in PROVINCE_REGION_TYPE.items():
            assert region in valid, f"{key!r} maps to unknown region {region!r}"
