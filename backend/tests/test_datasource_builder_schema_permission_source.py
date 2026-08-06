from pathlib import Path


def test_builder_schema_list_apis_use_datasource_permission_without_admin_gate():
    source = (Path(__file__).resolve().parents[1] / "apps/datasource/api/datasource.py").read_text(
        encoding="utf-8"
    )

    table_section = source[
        source.index('@router.post("/tableList/{id}"'):
        source.index('@router.post("/fieldList/{id}"')
    ]
    field_section = source[
        source.index('@router.post("/fieldList/{id}"'):
        source.index('@router.post("/editLocalComment"')
    ]
    schema_metadata_section = source[
        source.index('@router.get("/schema-metadata/{id}"'):
        source.index('@router.get("/schema-change/{id}"')
    ]

    assert "AppPermission(type='ds', keyExpression=\"id\")" in table_section
    assert "AppPermission(role=['admin']" not in table_section
    assert "_require_schema_metadata_admin(current_user)" not in table_section

    assert "AppPermission(type='table', keyExpression=\"id\")" in field_section
    assert "AppPermission(role=['admin']" not in field_section
    assert "_require_schema_metadata_admin(current_user)" not in field_section

    assert "_require_schema_metadata_admin(user)" in schema_metadata_section
