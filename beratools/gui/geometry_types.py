"""Geometry subtype parsing and geometry-family matching helpers."""

from __future__ import annotations

from typing import Iterable

GEOMETRY_FAMILIES = {"line", "polygon", "point"}

_GEOMETRY_NAME_TO_FAMILY = {
    "point": "point",
    "multipoint": "point",
    "3d point": "point",
    "3d multipoint": "point",
    "linestring": "line",
    "multilinestring": "line",
    "3d linestring": "line",
    "3d multilinestring": "line",
    "polygon": "polygon",
    "multipolygon": "polygon",
    "3d polygon": "polygon",
    "3d multipolygon": "polygon",
}


def parse_subtype_tokens(subtype_value) -> list[str]:
    """Normalize subtype input to a flat, lowercase token list."""
    if subtype_value is None:
        return []

    values: list[str] = []
    if isinstance(subtype_value, str):
        values = [subtype_value]
    elif isinstance(subtype_value, (list, tuple, set)):
        for item in subtype_value:
            if isinstance(item, str):
                values.append(item)
            elif item is not None:
                values.append(str(item))
    else:
        values = [str(subtype_value)]

    tokens: list[str] = []
    for value in values:
        for token in value.split("|"):
            normalized = token.strip().lower()
            if normalized and normalized not in tokens:
                tokens.append(normalized)

    return tokens


def get_allowed_geometry_families(subtype_tokens: Iterable[str]) -> set[str]:
    """Return allowed geometry families from subtype tokens."""
    return {token for token in subtype_tokens if token in GEOMETRY_FAMILIES}


def normalize_geometry_family(geometry_name: str | None) -> str | None:
    """Map concrete geometry names to point/line/polygon family."""
    if not geometry_name:
        return None

    key = str(geometry_name).strip().lower()
    if not key:
        return None

    if key in _GEOMETRY_NAME_TO_FAMILY:
        return _GEOMETRY_NAME_TO_FAMILY[key]

    compact = key.replace(" ", "")
    if compact in _GEOMETRY_NAME_TO_FAMILY:
        return _GEOMETRY_NAME_TO_FAMILY[compact]

    if "line" in compact:
        return "line"
    if "polygon" in compact:
        return "polygon"
    if "point" in compact:
        return "point"

    return None


def is_geometry_compatible(geometry_name: str | None, allowed_families: set[str]) -> bool:
    """Check if a geometry name matches one of the allowed families."""
    if not allowed_families:
        return True

    family = normalize_geometry_family(geometry_name)
    if family is None:
        return False

    return family in allowed_families


def format_expected_families(allowed_families: set[str]) -> str:
    """Format allowed geometry families for user-facing messages."""
    if not allowed_families:
        return "any vector geometry"
    return "/".join(sorted(allowed_families))
