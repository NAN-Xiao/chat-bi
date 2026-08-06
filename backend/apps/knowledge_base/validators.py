from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from apps.knowledge_base.schemas import (
    BusinessKnowledgePayload,
    BusinessSqlExample,
    DocumentPayload,
    EventKnowledgePayload,
    JsonFieldKnowledgePayload,
    KnowledgePayload,
    SemanticObjectReferenceInput,
    ValidationIssue,
    ValidationReport,
)
from common.sql_json_paths import extract_json_accesses, normalize_json_path

_SQL_BLOCK = re.compile(r"```sql\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_VALID_JSON_DATA_TYPES = {"boolean", "category", "date", "datetime", "decimal", "float", "identifier", "integer", "json", "number", "string", "text", "timestamp"}
_WRITE_EXPRESSIONS = (exp.Alter, exp.Command, exp.Create, exp.Delete, exp.Drop, exp.Insert, exp.Merge, exp.Update)


@dataclass(frozen=True)
class _CatalogTable:
    catalog: str | None
    schema: str | None
    table: str


@dataclass(frozen=True)
class ValidationContext:
    """Authoritative catalog and tracking values for one validation request."""

    dialect: str = "postgres"
    tables: Mapping[str, Iterable[str]] = field(default_factory=dict)
    json_paths: Mapping[str, Iterable[str]] = field(default_factory=dict)
    event_names: Iterable[str] = field(default_factory=tuple)

    def table_fields(self, *, schema: str | None, table: str) -> frozenset[str] | None:
        if not self.tables:
            return None
        target, schema_target = _key(table), _key(schema)
        for raw_table, raw_fields in self.tables.items():
            parts = [_key(part) for part in str(raw_table).split(".")]
            if parts[-1] == target and (not schema_target or (len(parts) > 1 and parts[-2] == schema_target)):
                return frozenset(_key(item) for item in raw_fields)
        return frozenset()

    def has_event_name(self, name: str) -> bool:
        return any(_key(item) == _key(name) for item in self.event_names)


def validate_payload(payload: KnowledgePayload, *, context: ValidationContext | None = None) -> ValidationReport:
    context = context or ValidationContext()
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    if isinstance(payload, DocumentPayload):
        _validate_document(payload, context, errors)
    elif isinstance(payload, BusinessKnowledgePayload):
        _validate_business(payload, context, errors, warnings)
    elif isinstance(payload, EventKnowledgePayload):
        _validate_event(payload, context, errors)
    elif isinstance(payload, JsonFieldKnowledgePayload):
        _validate_json(payload, context, errors)
    return ValidationReport(valid=not errors, errors=errors, warnings=warnings)


def _validate_document(payload: DocumentPayload, context: ValidationContext, errors: list[ValidationIssue]) -> None:
    if not payload.markdown.strip():
        _error(errors, "KNOWLEDGE_DOCUMENT_MARKDOWN_REQUIRED", "markdown", "知识文档正文不能为空。", "请填写或重新解析文档正文。")
        return
    blocks = _SQL_BLOCK.findall(payload.markdown)
    if payload.datasource_neutral and (blocks or payload.object_references or _document_has_physical_identifier(payload.markdown, context)):
        _error(errors, "KNOWLEDGE_DOCUMENT_NOT_NEUTRAL", "datasource_neutral", "数据源无关文档不能包含 SQL 或确定性物理对象引用。", "请取消数据源无关标记，并声明引用对象。")
        return
    if not payload.datasource_neutral:
        valid_declarations = _validate_related_objects(
            payload.object_references,
            context,
            errors,
            field_prefix="object_references",
        )
        declared = {
            _key(item.table)
            for index, item in enumerate(payload.object_references)
            if item.table and index in valid_declarations
        }
        if any(_key(item) not in declared for item in _document_tables(payload.markdown, context)):
            _error(errors, "KNOWLEDGE_DOCUMENT_OBJECT_NOT_DECLARED", "object_references", "文档中的物理对象必须显式声明。", "请声明文档引用的物理对象。")
        for index, sql in enumerate(blocks):
            _validate_sql(BusinessSqlExample(name=f"document-{index}", question="", sql=sql), payload.object_references, context, errors, f"markdown.sql_blocks[{index}]", valid_declarations=valid_declarations)


def _validate_business(payload: BusinessKnowledgePayload, context: ValidationContext, errors: list[ValidationIssue], warnings: list[ValidationIssue]) -> None:
    has_definition = bool((payload.term or "").strip() and payload.definition.strip())
    has_example = any(item.question.strip() and item.sql.strip() for item in payload.examples)
    if not has_definition and not has_example:
        _error(errors, "KNOWLEDGE_BUSINESS_CONTENT_REQUIRED", None, "业务知识必须填写术语和定义，或至少提供一条问题与 SQL 示例。", "请补充业务定义或完整 SQL 示例。")
    valid_declarations = _validate_related_objects(payload.related_objects, context, errors)
    used: set[int] = set()
    for index, item in enumerate(payload.examples):
        _validate_sql(item, payload.related_objects, context, errors, f"examples[{index}].sql", used, valid_declarations)
    for index, reference in enumerate(payload.related_objects):
        if reference.object_type == "TABLE" and index not in used:
            warnings.append(ValidationIssue(code="KNOWLEDGE_RELATED_OBJECT_UNUSED", message="声明的关联对象未被 SQL 示例使用。", field_path=f"related_objects[{index}]", error_type="WARNING", suggestion="确认该对象确有业务用途，或删除无用声明。"))


def _validate_event(payload: EventKnowledgePayload, context: ValidationContext, errors: list[ValidationIssue]) -> None:
    if not payload.event_name.strip():
        _error(errors, "KNOWLEDGE_EVENT_NAME_REQUIRED", "event_name", "事件名称不能为空。", "请填写工作空间内唯一的事件名称。")
    elif context.has_event_name(payload.event_name):
        _error(errors, "KNOWLEDGE_EVENT_NAME_DUPLICATE", "event_name", "同一工作空间内事件名称必须唯一。", "请使用不同的事件名称。")
    if not payload.event_name_field.strip():
        _error(errors, "KNOWLEDGE_EVENT_FIELD_REQUIRED", "event_name_field", "事件名称字段不能为空。", "请从当前数据源目录选择事件名称字段。")
    _validate_table_fields(context, None, payload.table_name, [("event_name_field", payload.event_name_field), ("event_time_field", payload.event_time_field)], errors, "KNOWLEDGE_EVENT_TABLE_NOT_FOUND", "KNOWLEDGE_EVENT_FIELD_NOT_FOUND")
    seen: set[str] = set()
    for index, parameter in enumerate(payload.parameters):
        name = _key(parameter.name)
        if not name:
            _error(errors, "KNOWLEDGE_EVENT_PARAMETER_REQUIRED", f"parameters[{index}].name", "事件参数名称不能为空。", "请填写参数名称。")
        elif name in seen:
            _error(errors, "KNOWLEDGE_EVENT_PARAMETER_DUPLICATE", f"parameters[{index}].name", "同一事件内参数名称必须唯一。", "请删除或重命名重复参数。")
        seen.add(name)
        if not parameter.data_type.strip():
            _error(errors, "KNOWLEDGE_EVENT_PARAMETER_TYPE_REQUIRED", f"parameters[{index}].data_type", "事件参数类型不能为空。", "请填写参数数据类型。")


def _validate_json(payload: JsonFieldKnowledgePayload, context: ValidationContext, errors: list[ValidationIssue]) -> None:
    if not payload.source_field.strip():
        _error(errors, "KNOWLEDGE_JSON_HOST_FIELD_REQUIRED", "source_field", "JSON 宿主字段不能为空。", "请从当前数据源目录选择 JSON 宿主字段。")
    if not payload.field_name.strip():
        _error(errors, "KNOWLEDGE_JSON_FIELD_NAME_REQUIRED", "field_name", "JSON 字段名称不能为空。", "请填写 JSON 字段名称。")
    _validate_table_fields(context, payload.schema_name, payload.table_name, [("source_field", payload.source_field)], errors, "KNOWLEDGE_JSON_TABLE_NOT_FOUND", "KNOWLEDGE_JSON_HOST_FIELD_NOT_FOUND")
    json_path = normalize_json_path(payload.json_path)
    if not json_path:
        _error(errors, "KNOWLEDGE_JSON_PATH_INVALID", "json_path", "JSON Path 必须是静态合法路径。", "请使用形如 $.field 或 $[0] 的静态路径。")
    if _key(payload.data_type) not in _VALID_JSON_DATA_TYPES:
        _error(errors, "KNOWLEDGE_JSON_DATA_TYPE_INVALID", "data_type", "JSON 字段目标类型不受支持。", "请使用已支持的语义类型。")
    if json_path:
        _validate_json_expression(payload, json_path, context, errors)


def _validate_table_fields(context: ValidationContext, schema: str | None, table: str, fields: list[tuple[str, str | None]], errors: list[ValidationIssue], table_code: str, field_code: str) -> None:
    if not table.strip():
        _error(errors, table_code, "table_name", "物理表不能为空。", "请从当前数据源目录选择物理表。")
        return
    known = context.table_fields(schema=schema, table=table)
    if known == frozenset():
        _error(errors, table_code, "table_name", "当前数据源目录中不存在指定物理表。", "请重新选择已同步的物理表。")
        return
    if known is not None:
        for path, field_name in fields:
            if field_name and field_name.strip() and _key(field_name) not in known:
                _error(errors, field_code, path, "当前数据源目录中不存在指定字段。", "请重新选择已同步的字段。")


def _validate_related_objects(
    declarations: list[SemanticObjectReferenceInput],
    context: ValidationContext,
    errors: list[ValidationIssue],
    *,
    field_prefix: str = "related_objects",
) -> set[int]:
    valid: set[int] = set()
    for index, declaration in enumerate(declarations):
        field_path = f"{field_prefix}[{index}]"
        if declaration.object_type not in {"TABLE", "FIELD", "JSON_PATH"} or not declaration.table:
            _error(errors, "KNOWLEDGE_RELATED_OBJECT_INCOMPLETE", field_path, "关联对象必须声明完整的物理表身份。", "请声明 Catalog、Schema 和表名。")
            continue
        if not context.tables:
            _error(errors, "KNOWLEDGE_RELATED_OBJECT_CONTEXT_REQUIRED", field_path, "当前校验上下文缺少物理对象目录。", "请在已绑定数据源的工作空间中校验该知识。")
            continue
        candidates = [item for item in _catalog_tables(context) if _key(item.table) == _key(declaration.table)]
        if not candidates:
            _error(errors, "KNOWLEDGE_RELATED_OBJECT_NOT_FOUND", field_path, "关联对象不在当前数据源目录中。", "请重新选择已同步的物理表。")
            continue
        if any(
            (candidate.catalog and not _key(declaration.catalog))
            or (candidate.schema and not _key(declaration.schema))
            for candidate in candidates
        ):
            _error(errors, "KNOWLEDGE_RELATED_OBJECT_INCOMPLETE", field_path, "关联对象必须声明目录中的完整 Catalog、Schema 和表名。", "请补齐 Catalog、Schema 和表名。")
            continue
        if not any(_catalog_table_matches(candidate, declaration) for candidate in candidates):
            _error(errors, "KNOWLEDGE_RELATED_OBJECT_NOT_FOUND", field_path, "关联对象不在当前数据源目录中。", "请重新选择已同步的完整对象。")
            continue
        if declaration.object_type in {"FIELD", "JSON_PATH"}:
            if not declaration.field:
                _error(errors, "KNOWLEDGE_RELATED_OBJECT_INCOMPLETE", field_path, "字段对象必须声明宿主字段。", "请补齐字段名。")
                continue
            fields = _fields_for_declaration(context, declaration)
            if fields is None or _key(declaration.field) not in fields:
                _error(errors, "KNOWLEDGE_RELATED_OBJECT_NOT_FOUND", field_path, "关联字段不在当前数据源目录中。", "请重新选择已同步的字段。")
                continue
        if declaration.object_type == "JSON_PATH" and not normalize_json_path(declaration.json_path):
            _error(errors, "KNOWLEDGE_RELATED_OBJECT_INCOMPLETE", field_path, "JSON Path 对象必须声明静态合法路径。", "请补齐 JSON Path。")
            continue
        valid.add(index)
    return valid


def _validate_sql(
    example: BusinessSqlExample,
    declarations: list[SemanticObjectReferenceInput],
    context: ValidationContext,
    errors: list[ValidationIssue],
    field_path: str,
    used: set[int] | None = None,
    valid_declarations: set[int] | None = None,
) -> None:
    statement = _read_only_statement(example.sql, example.dialect or context.dialect)
    if statement is None:
        _error(errors, "KNOWLEDGE_SQL_NOT_READ_ONLY", field_path, "SQL 示例必须是一条可解析的只读查询。", "请改为单条 SELECT 或 WITH 查询。")
        return
    declared = [
        (index, item)
        for index, item in enumerate(declarations)
        if item.table and (valid_declarations is None or index in valid_declarations)
    ]
    for table in _tables(statement):
        matched = [index for index, item in declared if _table_matches(table, item)]
        if not matched:
            _error(errors, "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED", field_path, "SQL 示例引用的物理对象必须显式声明。", "请在关联对象中声明 SQL 使用的表、Schema 或 Catalog。")
        elif used is not None:
            used.update(matched)
    _validate_declared_sql_objects(statement, declared, example.dialect or context.dialect, errors, field_path, used)


def _validate_json_expression(payload: JsonFieldKnowledgePayload, json_path: str, context: ValidationContext, errors: list[ValidationIssue]) -> None:
    try:
        statements = [item for item in sqlglot.parse(f"SELECT {payload.expression}", read=context.dialect) if item is not None]
    except Exception:
        statements = []
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        _error(errors, "KNOWLEDGE_JSON_EXPRESSION_INVALID", "expression", "JSON 表达式无法按当前数据源方言解析。", "请使用当前方言支持的确定性 JSON 表达式。")
        return
    extraction = extract_json_accesses(statements[0], dialect=context.dialect)
    expected = [item for item in extraction.accesses if _key(item.source_field) == _key(payload.source_field) and item.json_path == json_path]
    unexpected = [item for item in extraction.accesses if _key(item.source_field) != _key(payload.source_field) or item.json_path != json_path]
    columns = list(statements[0].find_all(exp.Column))
    has_only_host_column = (
        len(columns) == 1
        and _key(columns[0].name) == _key(payload.source_field)
        and not columns[0].table
    )
    has_disallowed_function = any(
        isinstance(node, exp.Func) and not _is_json_expression_function(node, context.dialect)
        for node in statements[0].walk()
    )
    if (
        extraction.issues
        or not expected
        or unexpected
        or any(statements[0].find_all(exp.Subquery))
        or any(statements[0].find_all(exp.Table))
        or not has_only_host_column
        or has_disallowed_function
    ):
        _error(errors, "KNOWLEDGE_JSON_EXPRESSION_INVALID", "expression", "JSON 表达式必须引用声明的宿主字段和静态 JSON Path。", "请使用当前方言的静态 JSON 提取表达式。")


def _read_only_statement(sql: str, dialect: str) -> exp.Expression | None:
    try:
        statements = [item for item in sqlglot.parse(sql, read=dialect) if item is not None]
    except Exception:
        return None
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return None
    if any(isinstance(node, (*_WRITE_EXPRESSIONS, exp.Into, exp.Lock)) for node in statements[0].walk()):
        return None
    return statements[0]


def _tables(statement: exp.Expression) -> list[SemanticObjectReferenceInput]:
    return [reference for reference, _ in _table_entries(statement)]


def _table_entries(statement: exp.Expression) -> list[tuple[SemanticObjectReferenceInput, str]]:
    ctes = {_key(item.alias_or_name) for item in statement.find_all(exp.CTE)}
    result: list[tuple[SemanticObjectReferenceInput, str]] = []
    for item in statement.find_all(exp.Table):
        name = str(item.name or "").strip()
        if name and (item.db or item.catalog or _key(name) not in ctes):
            reference = SemanticObjectReferenceInput(object_type="TABLE", catalog=str(item.catalog or "").strip() or None, schema=str(item.db or "").strip() or None, table=name)
            result.append((reference, _key(item.alias_or_name)))
    return result


def _table_matches(reference: SemanticObjectReferenceInput, declaration: SemanticObjectReferenceInput) -> bool:
    return _key(reference.table) == _key(declaration.table) and _key(reference.catalog) == _key(declaration.catalog) and _key(reference.schema) == _key(declaration.schema)


def _catalog_tables(context: ValidationContext) -> list[_CatalogTable]:
    tables: list[_CatalogTable] = []
    for raw_table in context.tables:
        parts = [part.strip() for part in str(raw_table).split(".") if part.strip()]
        if not parts:
            continue
        catalog = parts[-3] if len(parts) >= 3 else None
        schema = parts[-2] if len(parts) >= 2 else None
        tables.append(_CatalogTable(catalog=catalog, schema=schema, table=parts[-1]))
    return tables


def _catalog_table_matches(candidate: _CatalogTable, declaration: SemanticObjectReferenceInput) -> bool:
    return (
        _key(candidate.catalog) == _key(declaration.catalog)
        and _key(candidate.schema) == _key(declaration.schema)
        and _key(candidate.table) == _key(declaration.table)
    )


def _fields_for_declaration(
    context: ValidationContext,
    declaration: SemanticObjectReferenceInput,
) -> frozenset[str] | None:
    for raw_table, raw_fields in context.tables.items():
        parts = [part.strip() for part in str(raw_table).split(".") if part.strip()]
        if not parts:
            continue
        candidate = _CatalogTable(
            catalog=parts[-3] if len(parts) >= 3 else None,
            schema=parts[-2] if len(parts) >= 2 else None,
            table=parts[-1],
        )
        if _catalog_table_matches(candidate, declaration):
            return frozenset(_key(field) for field in raw_fields)
    return None


def _document_tables(markdown: str, context: ValidationContext) -> set[str]:
    return {
        table.table
        for table in _catalog_tables(context)
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(table.table)}(?![A-Za-z0-9_])", markdown)
    }


def _document_has_physical_identifier(markdown: str, context: ValidationContext) -> bool:
    identifiers = {table.table for table in _catalog_tables(context)}
    identifiers.update(
        str(field).strip()
        for fields in context.tables.values()
        for field in fields
        if str(field).strip()
    )
    identifiers.update(
        str(json_path).strip()
        for paths in context.json_paths.values()
        for json_path in paths
        if str(json_path).strip()
    )
    identifiers.update(str(event_name).strip() for event_name in context.event_names if str(event_name).strip())
    normalized_markdown = markdown.casefold()
    return any(
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(identifier.casefold())}(?![A-Za-z0-9_])",
            normalized_markdown,
        )
        for identifier in identifiers
    )


def _validate_declared_sql_objects(
    statement: exp.Expression,
    declarations: list[tuple[int, SemanticObjectReferenceInput]],
    dialect: str,
    errors: list[ValidationIssue],
    field_path: str,
    used: set[int] | None,
) -> None:
    field_accesses = _sql_field_accesses(statement)
    json_accesses = _sql_json_accesses(statement, dialect)
    for index, declaration in declarations:
        if declaration.object_type == "FIELD":
            matches = any(
                _table_matches(table, declaration) and _key(field) == _key(declaration.field)
                for table, field in field_accesses
            )
        elif declaration.object_type == "JSON_PATH":
            matches = any(
                _table_matches(table, declaration)
                and _key(field) == _key(declaration.field)
                and json_path == normalize_json_path(declaration.json_path)
                for table, field, json_path in json_accesses
            )
        else:
            continue
        if not matches:
            _error(errors, "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED", field_path, "SQL 示例未使用声明的字段或 JSON Path 对象。", "请让声明对象与 SQL 实际访问的对象一致。")
        elif used is not None:
            used.add(index)


def _sql_field_accesses(statement: exp.Expression) -> list[tuple[SemanticObjectReferenceInput, str]]:
    entries = _table_entries(statement)
    accesses: list[tuple[SemanticObjectReferenceInput, str]] = []
    for column in statement.find_all(exp.Column):
        table = _resolve_column_table(str(column.table or ""), entries)
        if table is not None and column.name:
            accesses.append((table, str(column.name)))
    return accesses


def _sql_json_accesses(statement: exp.Expression, dialect: str) -> list[tuple[SemanticObjectReferenceInput, str, str]]:
    entries = _table_entries(statement)
    accesses: list[tuple[SemanticObjectReferenceInput, str, str]] = []
    for access in extract_json_accesses(statement, dialect=dialect).accesses:
        table = _resolve_column_table(access.table_alias, entries)
        if table is not None:
            accesses.append((table, access.source_field, access.json_path))
    return accesses


def _resolve_column_table(
    qualifier: str,
    entries: list[tuple[SemanticObjectReferenceInput, str]],
) -> SemanticObjectReferenceInput | None:
    if not qualifier and len(entries) == 1:
        return entries[0][0]
    for reference, alias in entries:
        if _key(qualifier) in {_key(reference.table), alias}:
            return reference
    return None


def _is_json_expression_function(node: exp.Func, dialect: str) -> bool:
    if isinstance(node, exp.Cast):
        return True
    if type(node).__name__ in {"JSONExtract", "JSONExtractScalar", "JSONBExtract", "JSONBExtractScalar"}:
        return True
    if not isinstance(node, exp.Anonymous):
        return False
    names_by_dialect = {
        "postgres": {"JSON_VALUE", "JSON_EXTRACT", "JSON_EXTRACT_SCALAR", "JSONB_EXTRACT_PATH", "JSONB_EXTRACT_PATH_TEXT"},
        "mysql": {"JSON_VALUE", "JSON_EXTRACT", "JSON_UNQUOTE"},
        "clickhouse": {"JSON_VALUE", "JSONEXTRACT", "JSONEXTRACTSTRING", "JSONEXTRACTRAW"},
    }
    return str(node.name or "").upper() in names_by_dialect.get(_key(dialect), set())


def _key(value: object) -> str:
    return str(value or "").strip().strip('`"[]').casefold()


def _error(errors: list[ValidationIssue], code: str, field_path: str | None, message: str, suggestion: str) -> None:
    errors.append(ValidationIssue(code=code, message=message, field_path=field_path, error_type="ERROR", suggestion=suggestion))
