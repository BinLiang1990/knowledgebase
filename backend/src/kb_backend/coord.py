"""Coord normalization + hashing shared by the write path (issue #4) and the
future resolve engine (issue #5) — both must agree on what makes two coord
dicts "the same condition combination" (docs/PRD.md §6 rule #1).
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from decimal import Decimal, InvalidOperation
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


# MySQL JSON's exact-integer ceiling (BIGINT UNSIGNED max). Verified
# empirically against the real instance: beyond this, MySQL either raises
# "Number too big to be stored in double" on INSERT, or — for magnitudes
# past roughly 1e308 — silently demotes the value to a lossy double instead
# of erroring. Reject before either happens. Found by the Codex outer-gate
# review on PR #20 (originally reported as "'1e309' overflows to Infinity";
# a Decimal-based parse doesn't actually overflow to Infinity, but the
# underlying concern — an accepted value MySQL can't store exactly — still
# applies at this real boundary).
_MAX_SAFE_NUMBER_MAGNITUDE = 2**64 - 1


def _reject_if_unsafe_magnitude(key: str, value: int | float) -> None:
    # math.isfinite() would raise OverflowError on an arbitrary-precision
    # int far outside float range, before it ever gets to compare
    # magnitudes — check int magnitude with plain integer comparison first.
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_NUMBER_MAGNITUDE:
            raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值")
        return
    if not math.isfinite(value) or abs(value) > _MAX_SAFE_NUMBER_MAGNITUDE:
        raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值")


def _normalize_number(key: str, raw_value: Any) -> int | float:
    # bool is an int subclass in Python — float(True) == 1.0 would silently
    # accept a boolean as a number. Reject explicitly before any conversion.
    if isinstance(raw_value, bool):
        raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值")

    if isinstance(raw_value, int):
        _reject_if_unsafe_magnitude(key, raw_value)
        return raw_value
    if isinstance(raw_value, float):
        _reject_if_unsafe_magnitude(key, raw_value)
        return int(raw_value) if raw_value.is_integer() else raw_value
    if isinstance(raw_value, str):
        # Parse via Decimal, not int()-then-float(): an integer-valued
        # decimal STRING like "9007199254740993.0" isn't accepted by int()
        # (it has a '.') and would silently lose precision through a plain
        # float() round-trip. Decimal parses the digits exactly, so an
        # integral result converts to an exact-precision Python int instead.
        text = raw_value.strip()
        try:
            decimal_value = Decimal(text)
        except InvalidOperation as exc:
            raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值") from exc
        if not decimal_value.is_finite():
            raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值")
        if decimal_value == decimal_value.to_integral_value():
            int_value = int(decimal_value)
            _reject_if_unsafe_magnitude(key, int_value)
            return int_value
        float_value = float(decimal_value)
        _reject_if_unsafe_magnitude(key, float_value)
        return float_value

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
