from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath

ObjectType = Literal["SCHEMA", "TABLE", "FIELD", "JSON_PATH", "EVENT", "EVENT_PROPERTY"]


class SemanticObjectReferenceInput(BaseModel):
    """Payload DTO compatible with the catalog's DeclaredObjectPath."""

    model_config = ConfigDict(populate_by_name=True)

    object_type: ObjectType
    catalog: str | None = None
    schema_name: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    table: str | None = None
    field: str | None = None
    json_path: str | None = None
    event_name: str | None = None
    event_property_key: str | None = None

    @property
    def schema(self) -> str | None:
        return self.schema_name

    def as_declared_path(self) -> DeclaredObjectPath:
        return DeclaredObjectPath(
            object_type=self.object_type,
            catalog=self.catalog,
            schema=self.schema_name,
            table=self.table,
            field=self.field,
            json_path=self.json_path,
            event_name=self.event_name,
            event_property_key=self.event_property_key,
        )


class DocumentPayload(BaseModel):
    knowledge_type: Literal["DOCUMENT"]
    markdown: str
    tags: list[str] = Field(default_factory=list)
    datasource_neutral: bool = True
    object_references: list[SemanticObjectReferenceInput] = Field(default_factory=list)


class BusinessSqlExample(BaseModel):
    name: str
    question: str
    sql: str
    dialect: str | None = None
    notes: str = ""


class BusinessKnowledgePayload(BaseModel):
    knowledge_type: Literal["BUSINESS"]
    term: str | None = None
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""
    formula: str = ""
    constraints: list[str] = Field(default_factory=list)
    related_objects: list[SemanticObjectReferenceInput] = Field(default_factory=list)
    examples: list[BusinessSqlExample] = Field(default_factory=list)


class EventParameter(BaseModel):
    name: str
    display_name: str = ""
    data_type: str
    required: bool = False
    description: str = ""
    value_mappings: dict[str, str] = Field(default_factory=dict)


class EventKnowledgePayload(BaseModel):
    knowledge_type: Literal["EVENT"]
    event_name: str
    display_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    table_name: str
    event_name_field: str
    event_time_field: str | None = None
    parameters: list[EventParameter] = Field(default_factory=list)


class JsonFieldKnowledgePayload(BaseModel):
    knowledge_type: Literal["JSON_FIELD"]
    schema_name: str | None = None
    table_name: str
    source_field: str
    json_path: str
    field_name: str
    display_name: str = ""
    data_type: str
    expression: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    value_mappings: dict[str, str] = Field(default_factory=dict)


KnowledgePayload = Annotated[
    DocumentPayload | BusinessKnowledgePayload | EventKnowledgePayload | JsonFieldKnowledgePayload,
    Field(discriminator="knowledge_type"),
]
KnowledgePayloadAdapter = TypeAdapter(KnowledgePayload)


class ValidationIssue(BaseModel):
    code: str
    message: str
    field_path: str | None = None
    error_type: Literal["ERROR", "WARNING"]
    suggestion: str = ""


class ValidationReport(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
