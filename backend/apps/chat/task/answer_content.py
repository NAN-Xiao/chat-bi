"""Extract the explicitly user-facing part of a structured model response."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.utils.json import parse_json_markdown, parse_partial_json

ANSWER_CONTENT_KEY = "answer_content"


def extract_answer_content(text: str | None, *, partial: bool = False) -> str | None:
    """Return only the top-level ``answer_content`` string from a model envelope."""
    if not text:
        return None
    try:
        parser = parse_partial_json if partial else json.loads
        value: Any = parse_json_markdown(text, parser=parser)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    content = value.get(ANSWER_CONTENT_KEY)
    return content if isinstance(content, str) and content else None


class AnswerContentStream:
    """Collect model chunks and return a new cumulative body when it grows."""

    def __init__(self, source: str):
        self.source = source
        self._buffer = ""
        self._content = ""

    def push(self, chunk: str | None) -> dict[str, str] | None:
        if not chunk:
            return None
        self._buffer += chunk
        content = extract_answer_content(self._buffer, partial=True)
        if not content or len(content) <= len(self._content) or not content.startswith(self._content):
            return None
        # Do not emit a half-decoded Unicode escape/surrogate to JSON clients.
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            return None
        self._content = content
        return {"type": "answer-content", "source": self.source, "content": content}

    @property
    def content(self) -> str:
        return self._content
