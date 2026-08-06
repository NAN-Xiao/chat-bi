from __future__ import annotations

from apps.knowledge_base.schemas import ValidationIssue


class KnowledgeBusinessError(Exception):
    """Expected management error that can be returned without leaking internals."""

    def __init__(self, *, code: str, message: str, status_code: int = 400, field_path: str | None = None, error_type: str = "VALIDATION", suggestion: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field_path = field_path
        self.error_type = error_type
        self.suggestion = suggestion

    def as_validation_issue(self) -> ValidationIssue:
        return ValidationIssue(code=self.code, message=self.message, field_path=self.field_path, error_type="ERROR", suggestion=self.suggestion)
