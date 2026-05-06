"""Tests cho JSON extraction của LLMClient."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.ai.llm_client import LLMClient


def _client() -> LLMClient:
    return LLMClient("https://example.test/v1", "test-key", "test-model")


class _MockHTTPClient:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.request_json: dict[str, Any] | None = None

    def __enter__(self) -> "_MockHTTPClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> httpx.Response:
        self.request_json = json
        return self.response


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


def test_parse_sse_response_concatenates_content_chunks() -> None:
    response_text = """data: {"choices":[{"delta":{"content":"{\\\"ok\\\":"}}]}

data: {"choices":[{"delta":{"content":" true}"}}]}

data: [DONE]
"""

    result = _client()._parse_sse_response(response_text)

    assert result == '{"ok": true}'


def test_strip_thinking_tags_before_json_extraction() -> None:
    result = _client()._extract_json_from_content("<think>Đang suy nghĩ</think>{\"ok\": true}")

    assert result == {"ok": True}


def test_chat_parses_regular_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "{\"ok\": true}"}}]},
        request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
    )
    mock_client = _MockHTTPClient(response)
    monkeypatch.setattr("app.ai.llm_client.httpx.Client", lambda timeout: mock_client)

    result = _client().chat("system", "user")

    assert result == {"ok": True}
    assert mock_client.request_json is not None
    assert mock_client.request_json["stream"] is False


def test_chat_parses_sse_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='data: {"choices":[{"delta":{"content":"{\\\"ok\\\": true}"}}]}\n\ndata: [DONE]\n',
        request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
    )
    mock_client = _MockHTTPClient(response)
    monkeypatch.setattr("app.ai.llm_client.httpx.Client", lambda timeout: mock_client)

    result = _client().chat("system", "user")

    assert result == {"ok": True}
    assert mock_client.request_json is not None
    assert mock_client.request_json["stream"] is False
