"""reset_database.TRUNCATION_ORDER vs the ORM (#1077): every model table is reset, and a dependent
table is listed before the table it references. ccd_school_staffing and the three lea_* tables have no
FK to districts, so nothing cascades them; PR #1068's review found a reset leaving their rows (and
dropping their lineage) with verify_empty_state still True.
"""
from infrastructure.database.models import Base
from infrastructure.scripts.reset_database import TRUNCATION_ORDER


def test_every_model_table_is_in_the_truncation_order_exactly_once():
    assert set(Base.metadata.tables) - set(TRUNCATION_ORDER) == set()
    assert len(TRUNCATION_ORDER) == len(set(TRUNCATION_ORDER))


def test_dependents_are_truncated_before_what_they_reference():
    position = {t: i for i, t in enumerate(TRUNCATION_ORDER)}
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            referred = fk.column.table.name
            if referred != table.name:
                assert position[table.name] < position[referred], f"{table.name} references {referred}"
