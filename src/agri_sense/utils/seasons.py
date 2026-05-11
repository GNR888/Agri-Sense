"""Season detection utilities for the Agri-Sense recommendation system."""
from __future__ import annotations

import datetime
from dataclasses import dataclass

# Season windows: (name, (start_month, start_day), (end_month, end_day))
# Windows where start_month > end_month cross the Dec→Jan year boundary.
SEASON_WINDOWS: dict[str, list[tuple[str, tuple[int, int], tuple[int, int]]]] = {
    "mekong_delta": [
        ("Đông Xuân", (11, 15), (3, 15)),   # Nov 15 – Mar 15
        ("Hè Thu",    (3,  16), (7, 31)),    # Mar 16 – Jul 31
        ("Mùa",       (8,   1), (11, 14)),   # Aug 1  – Nov 14
    ],
    "red_river_delta": [
        ("Đông Xuân", (11, 15), (5, 31)),    # Nov 15 – May 31
        ("Mùa",       (6,   1), (11, 14)),   # Jun 1  – Nov 14
    ],
    "central_highlands": [
        ("annual",    (1,   1), (12, 31)),   # Year-round perennial crops
    ],
}

# Maps each province key to its season-calendar region type.
PROVINCE_REGION_TYPE: dict[str, str] = {
    "can_tho":    "mekong_delta",
    "kien_giang": "mekong_delta",
    "an_giang":   "mekong_delta",
    "dong_thap":  "mekong_delta",
    "soc_trang":  "mekong_delta",
    "thai_binh":  "red_river_delta",
    "nam_dinh":   "red_river_delta",
    "nghe_an":    "red_river_delta",
    "quang_nam":  "mekong_delta",
    "dak_lak":    "central_highlands",
    "lam_dong":   "central_highlands",
    "gia_lai":    "central_highlands",
    "dong_nai":   "central_highlands",
}

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_TRANSITION_DAYS = 14


def _dv(month: int, day: int) -> int:
    return month * 100 + day


def _in_window(d: datetime.date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    """True if date d falls within [start, end], handling year wrap-around."""
    v = _dv(d.month, d.day)
    sv = _dv(*start)
    ev = _dv(*end)
    if sv <= ev:
        return sv <= v <= ev
    # Wrap-around (e.g. Nov 15 – Mar 15): active if v ≥ sv OR v ≤ ev
    return v >= sv or v <= ev


@dataclass
class SeasonResolution:
    season: str
    region_type: str
    in_transition: bool
    next_season: str | None
    days_until_next_season: int | None
    banner_message: str


def resolve_season(
    province_key: str,
    ref_date: datetime.date,
    province_name_vi: str = "",
    *,
    forecast_mode: bool = False,
) -> SeasonResolution:
    """Resolve the current (or target) season for a province on a given date.

    Parameters
    ----------
    province_key:
        Short snake_case province identifier from ``geo.PROVINCES``.
    ref_date:
        Reference date (today for "today" mode; 15th of target month for forecast).
    province_name_vi:
        Vietnamese display name for the banner; falls back to formatted key.
    forecast_mode:
        When True, suppresses transition detection and adjusts banner wording.
    """
    region_type = PROVINCE_REGION_TYPE.get(province_key, "mekong_delta")
    windows = SEASON_WINDOWS[region_type]

    current_season: str | None = None
    for name, start, end in windows:
        if _in_window(ref_date, start, end):
            current_season = name
            break

    # Find the soonest upcoming season start strictly after ref_date.
    candidates: list[tuple[int, str]] = []
    for name, start, _ in windows:
        sm, sd = start
        for year in (ref_date.year, ref_date.year + 1):
            try:
                start_date = datetime.date(year, sm, sd)
            except ValueError:
                continue
            if start_date > ref_date:
                candidates.append(((start_date - ref_date).days, name))
                break
    candidates.sort()

    days_until: int | None = None
    next_season_name: str | None = None
    if candidates:
        days_until, next_season_name = candidates[0]

    # Transition only applies in "today" mode and for multi-season regions.
    in_transition = (
        not forecast_mode
        and len(windows) > 1
        and days_until is not None
        and days_until <= _TRANSITION_DAYS
    )
    effective_season = current_season or (next_season_name or "annual")

    month_name = _MONTH_NAMES[ref_date.month - 1]
    province_display = province_name_vi or province_key.replace("_", " ").title()

    if forecast_mode:
        banner = (
            f"Forecast for {month_name}: In {province_display}, "
            f"this will be the {effective_season} season. "
            "Forecast data is based on historical climate averages for this region."
        )
    elif in_transition and next_season_name and days_until is not None:
        banner = (
            f"It is currently {month_name}. In {province_display}, "
            f"you are in the {effective_season} season, transitioning to "
            f"{next_season_name} in {days_until} day{'s' if days_until != 1 else ''}."
        )
    else:
        banner = (
            f"It is currently {month_name}. In {province_display}, "
            f"this is the {effective_season} season. "
            "The best time to plant is now — here are your recommendations."
        )

    return SeasonResolution(
        season=effective_season,
        region_type=region_type,
        in_transition=in_transition,
        next_season=next_season_name if in_transition else None,
        days_until_next_season=days_until if in_transition else None,
        banner_message=banner,
    )


def season_for_month(region_type: str, month: int) -> str:
    """Return the season that covers the 15th of *month* for *region_type*.

    Used in forecast mode to map a target calendar month to its season.
    """
    windows = SEASON_WINDOWS.get(region_type, SEASON_WINDOWS["mekong_delta"])
    probe = datetime.date(2024, month, 15)
    for name, start, end in windows:
        if _in_window(probe, start, end):
            return name
    return windows[0][0]
