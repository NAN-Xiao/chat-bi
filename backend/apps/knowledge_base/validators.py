from __future__ import annotations

from apps.knowledge_base.schemas import (
    DocumentPayload,
    KnowledgePayload,
    ValidationIssue,
    ValidationReport,
)


def validate_payload(payload: KnowledgePayload) -> ValidationReport:
    """Validate only the structure produced by splitting an uploaded Markdown file."""
    errors: list[ValidationIssue] = []
    if isinstance(payload, DocumentPayload):
        _validate_document(payload, errors)
    return ValidationReport(valid=not errors, errors=errors, warnings=[])


def _validate_document(payload: DocumentPayload, errors: list[ValidationIssue]) -> None:
    if not payload.blocks:
        _error(
            errors,
            "KNOWLEDGE_DOCUMENT_BLOCK_REQUIRED",
            "blocks",
            "知识文档至少需要一个知识块。",
            "请检查 Markdown 格式并重新上传。",
        )
        return
    if not any(block.enabled for block in payload.blocks):
        _error(
            errors,
            "KNOWLEDGE_DOCUMENT_ENABLED_BLOCK_REQUIRED",
            "blocks",
            "至少需要启用一个知识块。",
            "请启用一个有效知识块后重新校验。",
        )
        return
    for index, block in enumerate(payload.blocks):
        if not block.title.strip():
            _error(
                errors,
                "KNOWLEDGE_DOCUMENT_BLOCK_TITLE_REQUIRED",
                f"blocks[{index}].title",
                "知识块标题不能为空。",
                "请填写知识块标题。",
            )
        if block.enabled and not block.markdown.strip():
            _error(
                errors,
                "KNOWLEDGE_DOCUMENT_BLOCK_MARKDOWN_REQUIRED",
                f"blocks[{index}].markdown",
                "已启用知识块的正文不能为空。",
                "请填写正文或停用该知识块。",
            )


def _error(
    errors: list[ValidationIssue],
    code: str,
    field_path: str | None,
    message: str,
    suggestion: str,
) -> None:
    errors.append(
        ValidationIssue(
            code=code,
            message=message,
            field_path=field_path,
            error_type="ERROR",
            suggestion=suggestion,
        )
    )
