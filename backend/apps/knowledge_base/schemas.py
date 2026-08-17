from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.markdown_template import advance_markdown_fence

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

    @field_validator(
        "catalog",
        "schema_name",
        "table",
        "field",
        "json_path",
        "event_name",
        "event_property_key",
        mode="before",
    )
    @classmethod
    def normalize_optional_identifier(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

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


class DocumentBlock(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=255)
    markdown: str = ""
    enabled: bool = True
    block_revision: int = Field(default=1, ge=1)

    @field_validator("id", "title", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return str(value or "").strip()


class DocumentPayload(BaseModel):
    knowledge_type: Literal["DOCUMENT"]
    blocks: list[DocumentBlock]
    structure_revision: int = Field(default=1, ge=1)
    tags: list[str] = Field(default_factory=list)
    datasource_neutral: bool = True
    object_references: list[SemanticObjectReferenceInput] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_markdown(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("blocks") is not None:
            return value
        markdown = str(value.get("markdown") or "")
        migrated = dict(value)
        migrated.pop("markdown", None)
        normalized_markdown = _normalize_legacy_markdown(markdown)
        seed = hashlib.sha256(normalized_markdown.encode("utf-8")).hexdigest()[:24]
        migrated["blocks"] = [{
            "id": f"legacy-{seed}",
            "title": "正文",
            "markdown": markdown,
            "enabled": True,
            "block_revision": 1,
        }]
        migrated.setdefault("structure_revision", 1)
        return migrated

    @property
    def markdown(self) -> str:
        return document_markdown(self)


_DOCUMENT_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def new_document_block(*, title: str = "", markdown: str = "") -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "markdown": markdown,
        "enabled": True,
        "block_revision": 1,
    }


def _normalize_legacy_markdown(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    return f"{text.rstrip()}\n" if text.strip() else ""


def document_blocks_from_markdown(markdown: str, *, legacy: bool = False) -> list[dict[str, Any]]:
    text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    sections: list[tuple[str, list[str]]] = []
    title = "正文"
    lines: list[str] = []
    active_fence: str | None = None
    for line in text.splitlines():
        previous_fence = active_fence
        active_fence = advance_markdown_fence(line, active_fence)
        match = (
            _DOCUMENT_HEADING.match(line)
            if previous_fence is None and active_fence is None
            else None
        )
        if match:
            if lines and any(item.strip() for item in lines):
                sections.append((title, lines))
            title = match.group(2).strip() or "正文"
            lines = []
        else:
            lines.append(line)
    if lines and any(item.strip() for item in lines):
        sections.append((title, lines))
    if not sections:
        sections = [("正文", text.splitlines())]
    result: list[dict[str, Any]] = []
    for index, (section_title, section_lines) in enumerate(sections):
        body = "\n".join(section_lines).strip()
        seed = f"{index}\0{section_title}\0{body}".encode()
        block_id = f"legacy-{hashlib.sha256(seed).hexdigest()[:24]}" if legacy else uuid.uuid4().hex
        result.append({
            "id": block_id,
            "title": section_title,
            "markdown": body,
            "enabled": True,
            "block_revision": 1,
        })
    return result


def document_markdown(payload: DocumentPayload, *, enabled_only: bool = True) -> str:
    sections: list[str] = []
    for block in payload.blocks:
        if enabled_only and not block.enabled:
            continue
        title = block.title.strip() or "正文"
        body = block.markdown.strip()
        sections.append(body if title == "正文" else f"# {title}\n\n{body}".rstrip())
    return "\n\n".join(sections)


KnowledgePayload = DocumentPayload
KnowledgePayloadAdapter = TypeAdapter(DocumentPayload)


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
