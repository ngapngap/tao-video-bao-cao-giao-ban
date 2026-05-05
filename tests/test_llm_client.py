"""Tests cho JSON extraction của LLMClient."""

from __future__ import annotations

import pytest

from app.ai.llm_client import LLMClient


def _client() -> LLMClient:
    return LLMClient("https://example.test/v1", "test-key", "test-model")


def test_extract_json_from_direct_json() -> None:
    result = _client()._extract_json_from_content('{"ok": true, "value": 1}')

    assert result == {"ok": True, "value": 1}


def test_extract_json_from_markdown_wrapper() -> None:
    result = _client()._extract_json_from_content('```json\n{"ok": true, "value": 2}\n```')

    assert result == {"ok": True, "value": 2}


def test_extract_json_from_text_with_embedded_object() -> None:
    result = _client()._extract_json_from_content('Dưới đây là JSON:\n{"ok": true, "value": 3}\nCảm ơn')

    assert result == {"ok": True, "value": 3}


def test_extract_json_empty_string_raises_value_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        _client()._extract_json_from_content("   ")


def test_extract_json_html_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Cannot extract JSON"):
        _client()._extract_json_from_content("<html><body>Gateway error</body></html>")
