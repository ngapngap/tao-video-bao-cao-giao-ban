"""Chunk processor dùng cho các bước AI có cache/resume theo từng chunk."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable


class ChunkProcessor:
    """Xử lý chunks với cache/resume, hỗ trợ tuần tự hoặc parallel.

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
        parallel: bool = True,
        max_workers: int | None = None,
    ) -> list[dict[str, Any]]:
        """Xử lý chunks, hỗ trợ parallel. max_workers=None = không giới hạn."""
        if max_workers is None:
            max_workers = len(chunks) if parallel else 1
        if not parallel:
            return self._process_sequential(chunks, processor, max_retry, on_progress)
        return self._process_parallel(chunks, processor, max_retry, on_progress, max_workers)

    def _process_sequential(
        self,
        chunks: list[Any],
        processor: Callable[[int, Any], dict[str, Any]],
        max_retry: int,
        on_progress: Callable[[int, int, str], None] | None,
    ) -> list[dict[str, Any]]:
        """Chạy tuần tự, giữ cache/resume/retry như hành vi cũ."""
        total_chunks = len(chunks)
        results: list[dict[str, Any] | None] = [None] * total_chunks
        for i, chunk in enumerate(chunks):
            if self.is_chunk_done(i):
                cached = self.load_chunk_result(i)
                if cached is not None:
                    results[i] = cached
                    if on_progress:
                        on_progress(i, total_chunks, "cached")
                    continue

            results[i] = self._process_one_chunk(i, chunk, total_chunks, processor, max_retry, on_progress)

        return [result for result in results if result is not None]

    def _process_parallel(
        self,
        chunks: list[Any],
        processor: Callable[[int, Any], dict[str, Any]],
        max_retry: int,
        on_progress: Callable[[int, int, str], None] | None,
        max_workers: int,
    ) -> list[dict[str, Any]]:
        """Chạy nhiều chunk đồng thời bằng ThreadPoolExecutor."""
        total_chunks = len(chunks)
        results: list[dict[str, Any] | None] = [None] * total_chunks
        pending_indices: list[int] = []

        for i in range(total_chunks):
            if self.is_chunk_done(i):
                cached = self.load_chunk_result(i)
                if cached is not None:
                    results[i] = cached
                    if on_progress:
                        on_progress(i, total_chunks, "cached")
            else:
                pending_indices.append(i)

        if not pending_indices:
            return [result for result in results if result is not None]

        worker_count = max(1, min(max_workers, len(pending_indices)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    self._process_one_chunk,
                    i,
                    chunks[i],
                    total_chunks,
                    processor,
                    max_retry,
                    on_progress,
                ): i
                for i in pending_indices
            }
            for future in as_completed(futures):
                index = futures[future]
                results[index] = future.result()

        return [result for result in results if result is not None]

    def _process_one_chunk(
        self,
        chunk_index: int,
        chunk: Any,
        total_chunks: int,
        processor: Callable[[int, Any], dict[str, Any]],
        max_retry: int,
        on_progress: Callable[[int, int, str], None] | None,
    ) -> dict[str, Any]:
        """Xử lý một chunk với retry/backoff và ghi cache ngay khi thành công."""
        for attempt in range(1, max_retry + 1):
            try:
                if on_progress:
                    on_progress(chunk_index, total_chunks, f"attempt {attempt}")
                result = processor(chunk_index, chunk)
                if not isinstance(result, dict):
                    raise ValueError("Chunk processor phải trả JSON object/dict")
                self.save_chunk_result(chunk_index, result)
                return result
            except Exception as exc:
                if attempt == max_retry:
                    raise
                if on_progress:
                    on_progress(chunk_index, total_chunks, f"retry after error: {exc}")
                time.sleep(min(30, 5 * attempt))

        raise RuntimeError(f"Không xử lý được chunk {chunk_index}")

    def clear_cache(self) -> None:
        """Xóa tất cả chunk cache."""
        for f in self.chunk_dir.glob("chunk_*.json"):
            f.unlink()
