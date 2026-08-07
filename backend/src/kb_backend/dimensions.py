from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.dimension import DimensionDefinition, KnowledgeBaseEnabledDimension


def get_enabled_dimension_types(db: Session, knowledge_base_id: int) -> dict[str, str]:
    """key -> field_type, for every dimension this KB has enabled that is
    also still globally active. INNER JOIN (see routers/knowledge_base.py's
    enabled-dimensions endpoint, issue #3): a globally-deprecated dimension
    must not be usable in a new coord even if the join-table row survives."""
    rows = db.execute(
        select(DimensionDefinition.key, DimensionDefinition.field_type)
        .join(
            KnowledgeBaseEnabledDimension,
            KnowledgeBaseEnabledDimension.dimension_key == DimensionDefinition.key,
        )
        .where(
            KnowledgeBaseEnabledDimension.knowledge_base_id == knowledge_base_id,
            DimensionDefinition.status == "active",
        )
    ).all()
    return dict(rows)
