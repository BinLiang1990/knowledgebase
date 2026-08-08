from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..envelope import BusinessError, envelope
from ..models.answer import Answer
from ..models.dimension import DimensionDefinition
from ..schemas.dimension import DimensionAdminOut, DimensionCreate, DimensionOut, DimensionUpdate

router = APIRouter(tags=["dimension"])

_DUPLICATE_KEY_MSG = "维度已存在，请使用其他名称"
_NOT_FOUND_MSG = "维度不存在"
_MYSQL_ER_DUP_ENTRY = 1062


def _raise_if_duplicate_key(exc: IntegrityError) -> None:
    # Mirrors knowledge_base.py's _raise_if_duplicate_name — only translate
    # an actual "duplicate entry" violation; any other integrity error
    # re-raises as-is.
    orig_args = getattr(exc.orig, "args", ())
    if orig_args and orig_args[0] == _MYSQL_ER_DUP_ENTRY:
        raise BusinessError(_DUPLICATE_KEY_MSG, status_code=400) from exc
    raise exc


def _get_or_404(db: Session, key: str) -> DimensionDefinition:
    dim = db.get(DimensionDefinition, key)
    if dim is None:
        raise BusinessError(_NOT_FOUND_MSG, status_code=404)
    return dim


def _answer_count_for_key(db: Session, key: str) -> int:
    # One-key slice of the same Python-side counting approach as
    # list_dimensions_admin below (design doc §4.4) — avoids building a
    # JSON path expression from arbitrary admin-typed text for what would
    # otherwise be a single-dimension count on every create/update/
    # activate/deactivate response.
    coords = db.execute(select(Answer.coord).where(Answer.revoked.is_(False))).scalars().all()
    return sum(1 for coord in coords if key in coord)


def _to_admin_out(dim: DimensionDefinition, answer_count: int) -> DimensionAdminOut:
    return DimensionAdminOut(
        key=dim.key,
        label=dim.label,
        field_type=dim.field_type,
        weight=dim.weight,
        default_value=dim.default_value,
        status=dim.status,
        answer_count=answer_count,
    )


def _set_status(db: Session, key: str, status: str) -> dict:
    dim = _get_or_404(db, key)
    # Mirrors knowledge_base.py's own _set_status: skip the write entirely
    # when already at the target status, instead of committing a no-op on
    # every idempotent activate/deactivate call. Kimi 终审 finding on PR #25.
    if dim.status != status:
        dim.status = status
        db.commit()
        db.refresh(dim)
    # dim.key (the canonical stored spelling), not the raw `key` path
    # param — dimension_definition.key's collation is case/accent
    # insensitive (same as knowledge_base.name), so _get_or_404 can
    # resolve e.g. "region" to a row actually stored as "Region". Answers'
    # coord always uses the canonical spelling; counting against the raw
    # URL spelling would silently report 0 for any request that used a
    # collation-equivalent but differently-spelled key. Codex outer-gate
    # finding on PR #25.
    out = _to_admin_out(dim, _answer_count_for_key(db, dim.key))
    return envelope(out.model_dump(mode="json"))


@router.get("/dimensions")
def list_dimensions(db: Session = Depends(get_db)) -> dict:
    rows = (
        db.execute(
            select(DimensionDefinition)
            .where(DimensionDefinition.status == "active")
            .order_by(DimensionDefinition.key)
        )
        .scalars()
        .all()
    )
    out = [DimensionOut.model_validate(row) for row in rows]
    return envelope([o.model_dump(mode="json") for o in out])


@router.get("/admin/dimensions")
def list_dimensions_admin(db: Session = Depends(get_db)) -> dict:
    """Internal management view (design doc §2/§4.6) — every dimension
    regardless of status, plus `default_value`/`status`/`answer_count`,
    unlike the external, active-only /dimensions above. Deliberately a
    separate path (not /dimensions/admin) so it can never collide with a
    future /dimensions/{key} lookup, given `key` is arbitrary admin-typed
    text with no reserved words (design doc §4.1/§4.6)."""
    rows = db.execute(select(DimensionDefinition).order_by(DimensionDefinition.key)).scalars().all()

    # One pass over every non-revoked answer's coord, counted in Python
    # rather than one JSON_CONTAINS_PATH query per dimension — `key` is
    # arbitrary admin-typed text (could contain '.', '"', '$', etc., all
    # meaningful in JSON path syntax), so building a path expression by
    # string interpolation is fragile at best. Design doc §4.4.
    answer_counts: dict[str, int] = {}
    coords = db.execute(select(Answer.coord).where(Answer.revoked.is_(False))).scalars().all()
    for coord in coords:
        for key in coord:
            answer_counts[key] = answer_counts.get(key, 0) + 1

    out = [_to_admin_out(row, answer_counts.get(row.key, 0)) for row in rows]
    return envelope([o.model_dump(mode="json") for o in out])


@router.post("/dimensions")
def create_dimension(payload: DimensionCreate, db: Session = Depends(get_db)) -> dict:
    # design doc §4.1: whatever the admin types as `label` becomes `key`
    # verbatim, unchanged, forever — no slugify/transliteration.
    dim = DimensionDefinition(
        key=payload.label,
        label=payload.label,
        field_type=payload.field_type,
        weight=payload.weight,
        default_value=payload.default_value,
        status="active",
    )
    db.add(dim)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_key(exc)
    db.refresh(dim)

    # A brand-new dimension has never been referenced by any answer —
    # genuinely 0, not a placeholder, so no count query is needed here.
    out = _to_admin_out(dim, answer_count=0)
    return envelope(out.model_dump(mode="json"))


@router.patch("/dimensions/{key}")
def update_dimension(key: str, payload: DimensionUpdate, db: Session = Depends(get_db)) -> dict:
    dim = _get_or_404(db, key)

    if payload.label is not None:
        dim.label = payload.label
    if payload.weight is not None:
        dim.weight = payload.weight
    # "default_value omitted" (keep unchanged) and "default_value explicitly
    # null" (clear it) are both meaningful and distinct — check
    # model_fields_set, not the value, mirroring update_knowledge_base's
    # own handling of `description`.
    if "default_value" in payload.model_fields_set:
        dim.default_value = payload.default_value

    db.commit()
    db.refresh(dim)

    out = _to_admin_out(dim, _answer_count_for_key(db, dim.key))
    return envelope(out.model_dump(mode="json"))


@router.post("/dimensions/{key}/activate")
def activate_dimension(key: str, db: Session = Depends(get_db)) -> dict:
    return _set_status(db, key, "active")


@router.post("/dimensions/{key}/deactivate")
def deactivate_dimension(key: str, db: Session = Depends(get_db)) -> dict:
    return _set_status(db, key, "deprecated")
