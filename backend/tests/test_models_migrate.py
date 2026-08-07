import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError

EXPECTED_TABLES = {
    "knowledge_base",
    "dimension_definition",
    "knowledge_base_enabled_dimension",
    "knowledge_point",
    "answer",
}


@pytest.fixture
def migrated_schema(alembic_cfg: AlembicConfig, db_engine: Engine):
    """Bring the real test database to a known state: clean -> head, and always
    clean up back to base afterwards so this test never leaves data behind for
    other issues/tests."""
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    try:
        yield
    finally:
        command.downgrade(alembic_cfg, "base")


def _index_rows(engine: Engine, table: str, index: str) -> list:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT NON_UNIQUE FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND INDEX_NAME = :index"
                ),
                {"table": table, "index": index},
            )
        )


def test_migration_creates_all_expected_tables(migrated_schema, db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")
        )
        actual = {r[0] for r in rows}
    assert EXPECTED_TABLES <= actual


@pytest.mark.parametrize(
    ("table", "index"),
    [
        ("knowledge_base", "uq_knowledge_base_name"),
        ("knowledge_point", "uq_kp_kb_title"),
        ("knowledge_point", "uq_kp_id_kb"),
    ],
)
def test_unique_indexes_exist_and_are_actually_unique(
    migrated_schema, db_engine: Engine, table: str, index: str
) -> None:
    rows = _index_rows(db_engine, table, index)
    assert rows, f"expected index {index} on {table} to exist"
    assert all(r[0] == 0 for r in rows), f"{index} on {table} exists but is NOT a unique index"


def test_answer_resolve_index_exists(migrated_schema, db_engine: Engine) -> None:
    rows = _index_rows(db_engine, "answer", "ix_answer_resolve")
    assert rows, "expected ix_answer_resolve on answer to exist"


def test_duplicate_knowledge_base_name_is_rejected(migrated_schema, db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("INSERT INTO knowledge_base (name) VALUES ('dup-kb')"))
    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(text("INSERT INTO knowledge_base (name) VALUES ('dup-kb')"))


def test_duplicate_knowledge_point_title_in_same_kb_is_rejected(
    migrated_schema, db_engine: Engine
) -> None:
    with db_engine.begin() as conn:
        kb_id = conn.execute(
            text("INSERT INTO knowledge_base (name) VALUES ('kb-for-kp-dup')")
        ).lastrowid
        conn.execute(
            text("INSERT INTO knowledge_point (knowledge_base_id, title) VALUES (:kb, 'dup-title')"),
            {"kb": kb_id},
        )
    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO knowledge_point (knowledge_base_id, title) VALUES (:kb, 'dup-title')"),
                {"kb": kb_id},
            )


def test_weight_check_constraint_rejects_out_of_range(migrated_schema, db_engine: Engine) -> None:
    # MySQL 8.0 reports CHECK-constraint violations as errno 3819, which
    # PyMySQL/SQLAlchemy surface as OperationalError rather than
    # IntegrityError (unlike UNIQUE/FK violations) — both mean "the
    # constraint did its job", so accept either.
    with pytest.raises((IntegrityError, OperationalError)):
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO dimension_definition (`key`, label, field_type, weight) "
                    "VALUES ('bad_weight', 'Bad', 'text', 999)"
                )
            )


def test_upgrade_head_is_idempotent(migrated_schema, alembic_cfg: AlembicConfig) -> None:
    # migrated_schema fixture already brought the DB to head; running it again
    # must be a no-op, not an error.
    command.upgrade(alembic_cfg, "head")


def test_enabled_dimension_join_table_rejects_unknown_dimension_key(
    migrated_schema, db_engine: Engine
) -> None:
    """The whole point of modeling enabled-dimensions as a join table (design
    doc §3, deviation 1) instead of a bare JSON array is that the database
    enforces the dimension actually exists. Prove it does."""
    with db_engine.begin() as conn:
        kb_id = conn.execute(
            text("INSERT INTO knowledge_base (name) VALUES ('kb-for-dim-fk')")
        ).lastrowid
    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO knowledge_base_enabled_dimension (knowledge_base_id, dimension_key) "
                    "VALUES (:kb, 'does_not_exist')"
                ),
                {"kb": kb_id},
            )


def test_enabled_dimension_join_table_accepts_valid_pair(migrated_schema, db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        kb_id = conn.execute(
            text("INSERT INTO knowledge_base (name) VALUES ('kb-for-dim-ok')")
        ).lastrowid
        conn.execute(
            text(
                "INSERT INTO dimension_definition (`key`, label, field_type) "
                "VALUES ('tenant', '租户', 'text')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO knowledge_base_enabled_dimension (knowledge_base_id, dimension_key) "
                "VALUES (:kb, 'tenant')"
            ),
            {"kb": kb_id},
        )
    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_base_enabled_dimension "
                "WHERE knowledge_base_id = :kb AND dimension_key = 'tenant'"
            ),
            {"kb": kb_id},
        ).scalar_one()
    assert count == 1


def test_answer_rejects_knowledge_base_id_mismatched_from_its_knowledge_point(
    migrated_schema, db_engine: Engine
) -> None:
    """`answer.knowledge_base_id` is a deliberate denormalization for cheap
    cross-KB stats (design doc §3, deviation-adjacent fix 6). The composite FK
    to knowledge_point(id, knowledge_base_id) must reject an answer whose
    knowledge_base_id disagrees with the knowledge_point it points to."""
    with db_engine.begin() as conn:
        kb_a = conn.execute(text("INSERT INTO knowledge_base (name) VALUES ('kb-a')")).lastrowid
        kb_b = conn.execute(text("INSERT INTO knowledge_base (name) VALUES ('kb-b')")).lastrowid
        kp_id = conn.execute(
            text("INSERT INTO knowledge_point (knowledge_base_id, title) VALUES (:kb, 'kp-1')"),
            {"kb": kb_a},
        ).lastrowid

    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO answer "
                    "(knowledge_base_id, knowledge_point_id, coord, coord_hash, content, effective_time) "
                    "VALUES (:kb_wrong, :kp, '{}', :hash, 'x', '2026-08-07')"
                ),
                {"kb_wrong": kb_b, "kp": kp_id, "hash": "0" * 64},
            )

    # sanity: the matching (correct) knowledge_base_id is accepted
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO answer "
                "(knowledge_base_id, knowledge_point_id, coord, coord_hash, content, effective_time) "
                "VALUES (:kb_right, :kp, '{}', :hash, 'x', '2026-08-07')"
            ),
            {"kb_right": kb_a, "kp": kp_id, "hash": "0" * 64},
        )
