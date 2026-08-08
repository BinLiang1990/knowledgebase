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


def test_normalize_number_integer_valued_decimal_string_preserves_precision() -> None:
    """Found by the Codex outer-gate review on PR #20: a plain float()
    round-trip rounds "9007199254740993.0" down to 9007199254740992."""
    out = normalize_coord({"priority": "9007199254740993.0"}, DIM_TYPES)
    assert out["priority"] == 9007199254740993


def test_normalize_number_rejects_magnitude_mysql_json_cannot_store_exactly() -> None:
    """"1e309" parses exactly via Decimal (no Infinity involved) but is a
    ~310-digit integer — verified empirically against the real instance that
    MySQL's JSON type rejects a value this large outright. Found by the
    Codex outer-gate review on PR #20 (originally reported as an Infinity
    overflow; the real failure mode turned out to be MySQL's own JSON
    numeric ceiling, not a Python float overflow)."""
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": "1e309"}, DIM_TYPES)


def test_normalize_number_rejects_huge_int_without_crashing() -> None:
    """A raw Python int far outside float range must be rejected cleanly —
    math.isfinite() raises OverflowError on an int this large, so the
    magnitude check must not route through it for the int branch."""
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": 10**400}, DIM_TYPES)


def test_normalize_number_rejects_non_finite_float() -> None:
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": float("inf")}, DIM_TYPES)


def test_normalize_number_accepts_uint64_max_boundary() -> None:
    boundary = 2**64 - 1
    assert normalize_coord({"priority": boundary}, DIM_TYPES) == {"priority": boundary}


def test_normalize_number_rejects_just_above_uint64_max_boundary() -> None:
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": 2**64}, DIM_TYPES)


def test_normalize_number_rejects_huge_exponential_string_cheaply() -> None:
    """Found by the Codex outer-gate review on PR #20 (round 3): a compact
    string like "1e1000000000" is finite and integral, so int() on it would
    materialize a billion-digit Python int before any magnitude check ran —
    a tiny request triggering an expensive allocation. Must reject via
    Decimal.adjusted() before ever calling int()."""
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": "1e1000000000"}, DIM_TYPES)


def test_normalize_number_rejects_negative_below_signed_min() -> None:
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": -(2**63) - 1}, DIM_TYPES)


def test_normalize_number_accepts_signed_min_boundary() -> None:
    boundary = -(2**63)
    assert normalize_coord({"priority": boundary}, DIM_TYPES) == {"priority": boundary}


def test_normalize_number_rejects_fractional_precision_beyond_float() -> None:
    """Found by the Codex outer-gate review on PR #20 (round 3): a plain
    float() conversion silently collapses distinct high-precision decimal
    strings onto the same nearest-representable float, which would corrupt
    coord_hash's exact-match guarantee. Reject instead of silently merging."""
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": "1.0000000000000000000000001"}, DIM_TYPES)


def test_normalize_number_distinct_high_precision_decimals_are_both_rejected_not_merged() -> None:
    a_raises = b_raises = False
    try:
        normalize_coord({"priority": "1.0000000000000000000000001"}, DIM_TYPES)
    except CoordValueError:
        a_raises = True
    try:
        normalize_coord({"priority": "1.0000000000000000000000002"}, DIM_TYPES)
    except CoordValueError:
        b_raises = True
    assert a_raises and b_raises


def test_normalize_number_accepts_ordinary_fractional_value() -> None:
    assert normalize_coord({"priority": "1.5"}, DIM_TYPES) == {"priority": 1.5}


def test_normalize_number_rejects_bare_float_beyond_exact_integer_range() -> None:
    """Found by the Codex outer-gate review on PR #20 (round 4): a bare JSON
    number (not a quoted string) is already a lossy float by the time this
    function sees it. Use 2**54 (exactly representable, unambiguously past
    the 2**53 safe boundary) rather than e.g. 9007199254740993.0 — that
    literal is itself rounded by Python's own source parsing down to
    exactly 2**53 before this test even runs, which would defeat the point."""
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": 2.0**54}, DIM_TYPES)


def test_normalize_number_accepts_bare_float_at_exact_integer_boundary() -> None:
    boundary = float(2**53)
    assert normalize_coord({"priority": boundary}, DIM_TYPES) == {"priority": 2**53}


def test_normalize_number_rejects_overlong_string_before_parsing_as_decimal() -> None:
    """Found by the Kimi review gate on PR #20: "1." + "0" * N has
    adjusted() == 0 (it's just 1.0 with excess trailing zeros), so it sails
    past the exponent guard — but Decimal(text) still has to process every
    character, so a tiny request body could still force an expensive parse
    without a length bound checked first."""
    with pytest.raises(CoordValueError):
        normalize_coord({"priority": "1." + "0" * 1_000_000}, DIM_TYPES)


def test_normalize_number_string_form_still_exact_beyond_bare_float_boundary() -> None:
    """The str/Decimal path is unaffected — it has the original text and can
    verify exactness, so large integers are still supported via strings."""
    out = normalize_coord({"priority": "9007199254740993"}, DIM_TYPES)
    assert out["priority"] == 9007199254740993


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


def test_normalize_coord_drops_empty_string_text_value() -> None:
    """frontend-mock treats coord[k] === "" as equivalent to unset
    everywhere (coordKeyOf/coordSpec/coordWeight/coordCompatible). Found
    during issue #5 design review; fixed in this shared module since both
    the write and query paths need the same equivalence."""
    assert normalize_coord({"tenant": ""}, DIM_TYPES) == {}
    assert normalize_coord({"tenant": "  "}, DIM_TYPES) == {}


def test_normalize_coord_empty_string_alongside_real_value() -> None:
    out = normalize_coord({"tenant": "", "priority": 1}, DIM_TYPES)
    assert out == {"priority": 1}
