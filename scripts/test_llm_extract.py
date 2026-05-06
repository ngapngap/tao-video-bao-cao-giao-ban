"""Test LLM extraction trực tiếp bằng httpx để so sánh với app.

Cách dùng trên Windows cmd.exe:
  set LLM_EXTRACT_URL=http://host:port/v1/chat/completions
  set LLM_EXTRACT_KEY=sk-...
  set LLM_EXTRACT_MODEL=model-id
  python scripts/test_llm_extract.py

Script không hard-code API key để tránh lộ secret trong repo/log.
"""

from __future__ import annotations

import glob
import json
import os
import sys

import httpx


def main() -> int:
    url = os.environ.get("LLM_EXTRACT_URL", "").strip()
    key = os.environ.get("LLM_EXTRACT_KEY", "").strip()
    model = os.environ.get("LLM_EXTRACT_MODEL", "").strip()

    if not url or not key or not model:
        print("Thiếu config. Cần set LLM_EXTRACT_URL, LLM_EXTRACT_KEY, LLM_EXTRACT_MODEL.")
        return 2

    parse_files = sorted(glob.glob("outputs/*/*/parsed/pdf-parse-result.json"), reverse=True)
    if parse_files:
        with open(parse_files[0], "r", encoding="utf-8") as f:
            parse_data = json.load(f)
        raw_text = str(parse_data.get("raw_text", ""))[:8000]
    else:
        raw_text = "Test text"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Trả về JSON hợp lệ. Không markdown, không giải thích."},
            {"role": "user", "content": f"Phân tích văn bản sau và trả JSON: {raw_text[:4000]}"},
        ],
        "stream": False,
        "temperature": 0.1,
    }

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    print(f"Gọi API: {url}")
    print(f"Model: {model}")
    print(f"Content length: {len(raw_text)}")

    resp = httpx.post(url, headers=headers, json=payload, timeout=180)
    print(f"Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type')}")

    resp.raise_for_status()
    content = resp.text
    if "data:" in content[:100]:
        parts: list[str] = []
        for line in content.split("\n"):
            if line.startswith("data: ") and line[6:] != "[DONE]":
                try:
                    chunk = json.loads(line[6:])
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        parts.append(delta["content"])
                except json.JSONDecodeError:
                    pass
        text = "".join(parts)
    else:
        data = resp.json()
        text = data["choices"][0]["message"]["content"]

    print(f"\nResponse length: {len(text)}")
    print(f"First 500 chars: {text[:500]}")

    try:
        result = json.loads(text)
        print(f"\nJSON keys: {list(result.keys())}")
    except json.JSONDecodeError:
        print("\nNot valid JSON, trying extract...")
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            result = json.loads(text[start : end + 1])
            print(f"Extracted JSON keys: {list(result.keys())}")
        else:
            raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
