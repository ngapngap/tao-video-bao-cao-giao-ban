"""LLM HTTP client cho OpenAI-compatible API."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """Client gọi OpenAI-compatible API."""

    def __init__(self, url: str, api_key: str, model: str, timeout: float = 120.0, supports_json_mode: bool = False):
        base_url = url.rstrip("/")
        self.url = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._supports_json_mode = supports_json_mode

    def _parse_sse_response(self, response_text: str) -> str:
        """Parse SSE stream, concatenate all content chunks."""
        content_parts: list[str] = []
        for line in response_text.split("\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if "content" in delta and delta["content"]:
                    content_parts.append(delta["content"])
            except json.JSONDecodeError:
                continue
        return "".join(content_parts)

    def _strip_thinking_tags(self, content: str) -> str:
        """Remove ...</think> tags from response."""
        return re.sub(r".*?</think>", "", content, flags=re.DOTALL).strip()

    def _extract_json_from_content(self, content: str | dict[str, Any] | list[Any]) -> dict[str, Any]:
        """Extract JSON từ response content, handle nhiều format."""
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            return {"items": content}
        if not isinstance(content, str):
            raise ValueError(f"LLM response content has unsupported type: {type(content).__name__}")

        stripped_content = self._strip_thinking_tags(content)

        if not stripped_content:
            raise ValueError("LLM response content is empty")

        try:
            parsed = json.loads(stripped_content)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
            raise ValueError(f"LLM JSON response is not object/list: {type(parsed).__name__}")
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", stripped_content, re.DOTALL | re.IGNORECASE)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1).strip())
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {"items": parsed}
                raise ValueError(f"LLM JSON code block is not object/list: {type(parsed).__name__}")
            except json.JSONDecodeError:
                pass

        brace_start = stripped_content.find("{")
        brace_end = stripped_content.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                parsed = json.loads(stripped_content[brace_start : brace_end + 1])
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {"items": parsed}
                raise ValueError(f"LLM embedded JSON object is not object/list: {type(parsed).__name__}")
            except json.JSONDecodeError:
                pass

        bracket_start = stripped_content.find("[")
        bracket_end = stripped_content.rfind("]")
        if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
            try:
                parsed = json.loads(stripped_content[bracket_start : bracket_end + 1])
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {"items": parsed}
                raise ValueError(f"LLM embedded JSON array is not object/list: {type(parsed).__name__}")
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Cannot extract JSON from LLM response. First 500 chars: {stripped_content[:500]}")

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.1) -> dict[str, Any]:
        """Gọi LLM, trả về parsed JSON response."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        enhanced_prompt = (
            system_prompt
            + "\n\nIMPORTANT: You MUST respond with valid JSON only. No markdown, no explanation, just the JSON object."
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": enhanced_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "stream": False,
        }
        if self._supports_json_mode:
            payload["response_format"] = {"type": "json_object"}

        raw_content: str | dict[str, Any] | list[Any] | None = None
        response: httpx.Response | None = None
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    raw_content = self._parse_sse_response(response.text)
                else:
                    data = response.json()
                    raw_content = data["choices"][0]["message"]["content"]
                logger.debug("Raw LLM response content preview: %s", str(raw_content)[:500])
                return self._extract_json_from_content(raw_content)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            raw_preview = str(raw_content)[:500] if raw_content is not None else "N/A"
            if raw_preview == "N/A" and response is not None:
                raw_preview = response.text[:500]
            error_detail = {
                "error": str(exc),
                "raw_content_preview": raw_preview,
                "response_status": response.status_code if response is not None else "N/A",
                "response_headers": dict(response.headers) if response is not None else {},
            }
            raise ValueError(f"LLM response parse failed: {error_detail}") from exc

    def chat_with_retry_parse(self, system_prompt: str, user_content: str, max_parse_retries: int = 2, temperature: float = 0.1) -> dict[str, Any]:
        """Gọi LLM và retry khi response không parse được thành JSON."""
        retry_prompt = system_prompt
        for attempt in range(max_parse_retries + 1):
            try:
                return self.chat(retry_prompt, user_content, temperature=temperature)
            except ValueError:
                if attempt >= max_parse_retries:
                    raise
                retry_prompt = (
                    retry_prompt
                    + "\n\nCRITICAL: Your previous response was not valid JSON. You MUST respond with ONLY a valid JSON object. No text before or after."
                )
        raise RuntimeError("Unreachable LLM parse retry state")

    def fetch_models(self) -> list[str]:
        """Gọi GET {base_url}/models để lấy danh sách model IDs."""
        models_url = self.url.replace("/chat/completions", "/models")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=15.0) as client:
            response = client.get(models_url, headers=headers)
            response.raise_for_status()
            data = response.json()
            models = data.get("data", [])
            return sorted([m.get("id", "") for m in models if m.get("id")])

    def test_connection(self) -> tuple[bool, str]:
        """Test kết nối, trả (ok, message)."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Trả lời đúng một chữ: OK"}],
                "max_tokens": 8,
                "stream": False,
            }
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                returned_model = data.get("model") or self.model
                return True, f"Kết nối thành công! Model: {returned_model}"
        except httpx.TimeoutException:
            return False, "Không kết nối được: timeout khi gọi API"
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            return False, f"Không kết nối được: HTTP {exc.response.status_code} - {detail}"
        except Exception as exc:  # noqa: BLE001 - hiển thị lỗi cụ thể cho người dùng
            return False, f"Không kết nối được: {exc}"
