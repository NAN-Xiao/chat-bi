"""Regression tests for Data Skill semantic-object projection parsing."""

from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, Integer, create_engine
from sqlmodel import Session, SQLModel, select

from apps.chat.curd.skill_object_projection import (
    SKILL_PROJECTION_ERROR,
    project_skill_references,
    rebuild_skill_object_projection,
)
from apps.chat.curd.skill_object_references import skill_source_hash
from apps.chat.models.custom_prompt_model import CustomPrompt
from apps.knowledge_base.object_projection_models import (
    DataSkillObjectProjection,
    SemanticObjectReference,
    SemanticObjectResolution,
)
from apps.knowledge_base.object_sql import SqlObjectExtractionError


def test_required_tables_and_sql_ast_are_projected_without_changing_skill_selection() -> None:
    skill = SimpleNamespace(
        prompt=(
            '<!-- data-skill-requires-tables:["event"] -->\n'
            "```sql\n"
            "SELECT uid, personal->>'$.ed_money' AS money FROM event\n"
            "```"
        )
    )

    references = project_skill_references(skill)

    assert {(item.object_type, item.table_name, item.source_kind) for item in references} >= {
        ("TABLE", "event", "SKILL_RULE"),
        ("TABLE", "event", "SQL_AST"),
        ("FIELD", "event", "SQL_AST"),
        ("JSON_PATH", "event", "SQL_AST"),
    }


def test_skill_without_object_declarations_is_ready_with_zero_references() -> None:
    assert project_skill_references(SimpleNamespace(prompt="只描述业务口径，不包含 SQL。")) == []


def test_invalid_sql_returns_the_existing_safe_parser_error() -> None:
    with pytest.raises(SqlObjectExtractionError) as error:
        project_skill_references(SimpleNamespace(prompt="```sql\nSELECT FROM\n```"))

    assert error.value.code == "KNOWLEDGE_SQL_PARSE_FAILED"
    assert SKILL_PROJECTION_ERROR in "DATA_SKILL_OBJECT_PROJECTION_FAILED"


def test_projection_rebuild_is_idempotent_and_delete_cleans_derived_rows() -> None:
    temporary_types = {
        CustomPrompt.__table__.c.id: Integer(),
        CustomPrompt.__table__.c.datasource_ids: JSON(),
        DataSkillObjectProjection.__table__.c.id: Integer(),
        SemanticObjectReference.__table__.c.id: Integer(),
        SemanticObjectResolution.__table__.c.id: Integer(),
        SemanticObjectResolution.__table__.c.report: JSON(),
    }
    original_types = {column: column.type for column in temporary_types}
    for column, column_type in temporary_types.items():
        column.type = column_type
    engine = create_engine("sqlite://")
    try:
        SQLModel.metadata.create_all(
            engine,
            tables=[
                CustomPrompt.__table__,
                DataSkillObjectProjection.__table__,
                SemanticObjectReference.__table__,
                SemanticObjectResolution.__table__,
            ],
        )
        with Session(engine) as session:
            skill = CustomPrompt(
                id=1,
                tenant_id=9,
                type="DATA_SKILL",
                name="订单规则",
                prompt='<!-- data-skill-requires-tables:["orders"] -->',
                specific_ds=True,
                datasource_ids=[3],
            )
            session.add(skill)
            session.commit()

            first = rebuild_skill_object_projection(session, 1)
            second = rebuild_skill_object_projection(session, 1)
            session.commit()

            projection = session.exec(select(DataSkillObjectProjection)).one()
            references = session.exec(select(SemanticObjectReference)).all()
            assert first.status == second.status == "READY"
            assert projection.source_hash == skill_source_hash(skill)
            assert projection.reference_count == 1
            assert len(references) == 1
            assert references[0].datasource_id == 3

            skill.prompt = "```sql\nSELECT FROM\n```"
            session.add(skill)
            session.flush()
            failed = rebuild_skill_object_projection(session, 1)
            session.commit()
            projection = session.exec(select(DataSkillObjectProjection)).one()
            assert failed.status == projection.status == "FAILED"
            assert projection.error_code == "KNOWLEDGE_SQL_PARSE_FAILED"
            assert projection.reference_count == 0
            assert session.exec(select(SemanticObjectReference)).all() == []

            session.delete(skill)
            session.flush()
            deleted = rebuild_skill_object_projection(session, 1)
            session.commit()

            assert deleted.status == "DELETED"
            assert session.exec(select(DataSkillObjectProjection)).all() == []
            assert session.exec(select(SemanticObjectReference)).all() == []
    finally:
        for column, column_type in original_types.items():
            column.type = column_type
        engine.dispose()
