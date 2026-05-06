"""Chunk processor dùng cho các bước AI có cache/resume theo từng chunk."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


class ChunkProcessor:
    """Xử lý chunks tuần tự với cache và resume.

    Mỗi chunk thành công được ghi ra file riêng để lần chạy sau có thể skip
    chunk đã hoàn tất và retry đúng chunk đang lỗi thay vì chạy lại toàn bộ step.
    """

    def __init__(self, output_dir: str, chunk_dir_name: str = "chunks"):
        self.output_dir = Path(output_dir)
        self.chunk_dir = self.output_dir / chunk_dir_name
        self.chunk_dir.mkdir(parents=True, exist_ok=True)

    def get_chunk_path(self, chunk_index: int) -> Path:
        return self.chunk_dir / f"chunk_{chunk_index:03d}.json"

    def is_chunk_done(self, chunk_index: int) -> bool:
        path = self.get_chunk_path(chunk_index)
        return path.exists() and path.stat().st_size > 0

    def load_chunk_result(self, chunk_index: int) -> dict[str, Any] | None:
        if not self.is_chunk_done(chunk_index):
            return None
        with self.get_chunk_path(chunk_index).open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Chunk cache không phải JSON object: {self.get_chunk_path(chunk_index)}")
        return data

    def save_chunk_result(self, chunk_index: int, data: dict[str, Any]) -> None:
        path = self.get_chunk_path(chunk_index)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def process_chunks(
        self,
        chunks: list[Any],
        processor: Callable[[int, Any], dict[str, Any]],
        max_retry: int = 3,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Xử lý tất cả chunks, skip chunk đã done, retry khi fail."""
        results: list[dict[str, Any]] = []
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            if self.is_chunk_done(i):
                cached = self.load_chunk_result(i)
                if cached is not None:
                    results.append(cached)
                    if on_progress:
                        on_progress(i, total_chunks, "cached")
                    continue

            for attempt in range(1, max_retry + 1):
                try:
                    if on_progress:
                        on_progress(i, total_chunks, f"attempt {attempt}")
                    result = processor(i, chunk)
                    if not isinstance(result, dict):
                        raise ValueError("Chunk processor phải trả JSON object/dict")
                    self.save_chunk_result(i, result)
                    results.append(result)
                    break
                except Exception as exc:
                    if attempt == max_retry:
                        raise
                    if on_progress:
                        on_progress(i, total_chunks, f"retry after error: {exc}")
                    time.sleep(min(30, 5 * attempt))

        return results

    def clear_cache(self) -> None:
        """Xóa tất cả chunk cache."""
        for f in self.chunk_dir.glob("chunk_*.json"):
            f.unlink()
