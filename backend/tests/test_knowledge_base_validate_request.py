from __future__ import annotations

from apps.knowledge_base.api.versions import ValidateDraftRequest


def test_validate_draft_request_does_not_define_datasource_id() -> None:
    assert "datasource_id" not in ValidateDraftRequest.model_fields

    request = ValidateDraftRequest(
        version_id=10,
        revision=2,
        content_hash="hash",
    )

    assert "datasource_id" not in request.model_dump()
