"""Coord normalization + hashing shared by the write path (issue #4) and the
future resolve engine (issue #5) — both must agree on what makes two coord
dicts "the same condition combination" (docs/PRD.md §6 rule #1).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

_FIELD_TYPES = ("text", "number", "date", "boolean")


class CoordValueError(ValueError):
    def __init__(self, dimension_key: str, message: str) -> None:
        super().__init__(message)
        self.dimension_key = dimension_key


def _normalize_text(key: str, raw_value: Any) -> str:
    if not isinstance(raw_value, str):
        raise CoordValueError(key, f"维度 {key} 取值类型错误，应为文本")
    return raw_value.strip()


def _normalize_number(key: str, raw_value: Any) -> int | float:
    # bool is an int subclass in Python — float(True) == 1.0 would silently
    # accept a boolean as a number. Reject explicitly before any conversion.
    if isinstance(raw_value, bool):
        raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值")

    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value) if raw_value.is_integer() else raw_value
    if isinstance(raw_value, str):
        text = raw_value.strip()
        try:
            # Try int first so large integer-valued IDs (> 2**53) keep exact
            # precision instead of being rounded by a float() round-trip.
            return int(text)
        except ValueError:
            pass
        try:
            parsed = float(text)
        except ValueError as exc:
            raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值") from exc
        return int(parsed) if parsed.is_integer() else parsed

    raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值")


def _normalize_date(key: str, raw_value: Any) -> str:
    if not isinstance(raw_value, str):
        raise CoordValueError(key, f"维度 {key} 取值类型错误，应为合法日期")
    try:
        return date.fromisoformat(raw_value.strip()).isoformat()
    except ValueError as exc:
        raise CoordValueError(key, f"维度 {key} 取值类型错误，应为合法日期") from exc


def _normalize_boolean(key: str, raw_value: Any) -> bool:
    # Deliberately strict: only the JSON literals true/false, never the
    # strings "true"/"false" — see design doc §3.5.
    if isinstance(raw_value, bool):
        return raw_value
    raise CoordValueError(key, f"维度 {key} 取值类型错误，应为布尔值(true/false)")


_NORMALIZERS = {
    "text": _normalize_text,
    "number": _normalize_number,
    "date": _normalize_date,
    "boolean": _normalize_boolean,
}


def normalize_coord(coord: dict[str, Any], dimension_types: dict[str, str]) -> dict[str, Any]:
    """`dimension_types` maps every dimension key the caller is allowed to use
    (already filtered to this KB's enabled + active dimensions) to its
    `field_type`. Raises `CoordValueError` for an unknown key or a value that
    fails its field_type's validation."""
    normalized: dict[str, Any] = {}
    for key, raw_value in coord.items():
        field_type = dimension_types.get(key)
        if field_type is None:
            raise CoordValueError(key, f"维度 {key} 未在本知识库启用")
        normalized[key] = _NORMALIZERS[field_type](key, raw_value)
    return normalized


def compute_coord_hash(normalized_coord: dict[str, Any]) -> str:
    canonical = json.dumps(normalized_coord, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
