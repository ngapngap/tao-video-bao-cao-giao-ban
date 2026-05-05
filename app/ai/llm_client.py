"""LLM HTTP client cho OpenAI-compatible API."""

from __future__ import annotations

import json

import httpx


class LLMClient:
    """Client gọi OpenAI-compatible API."""

    def __init__(self, url: str, api_key: str, model: str, timeout: float = 120.0):
        self.url = url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.1) -> dict:
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
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                return True, "OK"
        except Exception as exc:
            return False, str(exc)
