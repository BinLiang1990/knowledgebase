import pytest

from kb_backend.coord import CoordValueError, compute_coord_hash, normalize_coord

DIM_TYPES = {
    "tenant": "text",
    "priority": "number",
    "valid_from": "date",
    "is_vip": "boolean",
}


def test_normalize_text_strips_whitespace() -> None:
    assert normalize_coord({"tenant": "  acme  "}, DIM_TYPES) == {"tenant": "acme"}


def test_normalize_text_rejects_non_string() -> None:
    with pytest.raises(CoordValueError):
        normalize_coord({"tenant": 123}, DIM_TYPES)


@pytest.mark.parametrize("raw", [1, 1.0, "1"])
def test_normalize_number_equivalent_representations_match(raw) -> None:
    assert normalize_coord({"priority": raw}, DIM_TYPES) == {"priority": 1}


def test_normalize_number_rejects_boolean() -> None:
    """bool is an int subclass in Python — float(True) == 1.0 would silently
    accept it as a number without this explicit check."""
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": True}, DIM_TYPES)


def test_normalize_number_preserves_large_integer_precision() -> None:
    big_a = 9007199254740993
    big_b = 9007199254740992
    out_a = normalize_coord({"priority": big_a}, DIM_TYPES)
    out_b = normalize_coord({"priority": big_b}, DIM_TYPES)
    assert out_a["priority"] == big_a
    assert out_b["priority"] == big_b
    assert compute_coord_hash(out_a) != compute_coord_hash(out_b)


def test_normalize_number_string_large_integer_preserves_precision() -> None:
    out = normalize_coord({"priority": "9007199254740993"}, DIM_TYPES)
    assert out["priority"] == 9007199254740993


def test_normalize_number_keeps_fractional_as_float() -> None:
    assert normalize_coord({"priority": 1.5}, DIM_TYPES) == {"priority": 1.5}


def test_normalize_number_rejects_unparseable_string() -> None:
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": "not-a-number"}, DIM_TYPES)


def test_normalize_date_canonicalizes_iso_format() -> None:
    assert normalize_coord({"valid_from": "2026-08-08"}, DIM_TYPES) == {"valid_from": "2026-08-08"}


def test_normalize_date_rejects_invalid_date() -> None:
    with pytest.raises(CoordValueError):
        normalize_coord({"valid_from": "not-a-date"}, DIM_TYPES)


def test_normalize_boolean_accepts_only_json_literal() -> None:
    assert normalize_coord({"is_vip": True}, DIM_TYPES) == {"is_vip": True}
    assert normalize_coord({"is_vip": False}, DIM_TYPES) == {"is_vip": False}


def test_normalize_boolean_rejects_string_true() -> None:
    """PRD: 布尔必须是 true/false — interpreted strictly, not "truthy" strings."""
    with pytest.raises(CoordValueError):
        normalize_coord({"is_vip": "true"}, DIM_TYPES)


def test_normalize_rejects_unknown_dimension_key() -> None:
    with pytest.raises(CoordValueError):
        normalize_coord({"not_enabled": "x"}, DIM_TYPES)


def test_compute_coord_hash_ignores_key_order() -> None:
    a = normalize_coord({"tenant": "acme", "priority": 1}, DIM_TYPES)
    b = normalize_coord({"priority": 1, "tenant": "acme"}, DIM_TYPES)
    assert compute_coord_hash(a) == compute_coord_hash(b)


def test_compute_coord_hash_differs_for_different_values() -> None:
    a = normalize_coord({"tenant": "acme"}, DIM_TYPES)
    b = normalize_coord({"tenant": "other"}, DIM_TYPES)
    assert compute_coord_hash(a) != compute_coord_hash(b)


def test_compute_coord_hash_empty_coord_is_stable() -> None:
    assert compute_coord_hash({}) == compute_coord_hash(normalize_coord({}, DIM_TYPES))
