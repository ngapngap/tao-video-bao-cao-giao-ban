"""LLM HTTP client cho OpenAI-compatible API."""

from __future__ import annotations

import json
from typing import Any

import httpx


class LLMClient:
    """Client gọi OpenAI-compatible API."""

    def __init__(self, url: str, api_key: str, model: str, timeout: float = 120.0):
        base_url = url.rstrip("/")
        self.url = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.1) -> dict[str, Any]:
        """Gọi LLM, trả về parsed JSON response."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, dict):
                return content
            return json.loads(content)

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
