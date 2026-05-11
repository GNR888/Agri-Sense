"""Canonical crop vocabulary and name normalisation for Agri-Sense."""

CANONICAL_CROPS: frozenset[str] = frozenset(
    {
        "rice_paddy",
        "coffee_green",
        "cashew_raw",
        "pepper_black",
        "maize",
    }
)

# Maps every known variant (lowercased, stripped) to its canonical name.
_ALIASES: dict[str, str] = {
    # canonical forms map to themselves
    "rice_paddy": "rice_paddy",
    "coffee_green": "coffee_green",
    "cashew_raw": "cashew_raw",
    "pepper_black": "pepper_black",
    "maize": "maize",
    # short forms used in gso/yields.csv
    "rice": "rice_paddy",
    "coffee": "coffee_green",
    "cashew": "cashew_raw",
    "pepper": "pepper_black",
    # common English alternatives
    "paddy": "rice_paddy",
    "corn": "maize",
}


def normalise_crop_name(name: str) -> str:
    """Return the canonical crop name for *name*, raising ValueError if unknown."""
    key = name.strip().lower()
    try:
        return _ALIASES[key]
    except KeyError:
        raise ValueError(f"Unknown crop name {name!r}. Known aliases: {sorted(_ALIASES)}")
