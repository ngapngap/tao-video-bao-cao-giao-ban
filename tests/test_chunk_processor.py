"""Tests cho ChunkProcessor cache/resume/retry."""

from __future__ import annotations

import pytest

from app.core.chunk_processor import ChunkProcessor


def test_process_chunks_saves_cache_and_loads_cached_results(tmp_path):
    processor = ChunkProcessor(str(tmp_path), "extract_chunks")
    calls: list[int] = []

    def handle(index: int, chunk: str) -> dict:
        calls.append(index)
        return {"chunk_index": index, "text": chunk.upper()}

    first_results = processor.process_chunks(["a", "b"], handle, max_retry=1)
    second_results = processor.process_chunks(["a", "b"], handle, max_retry=1)

    assert calls == [0, 1]
    assert first_results == [{"chunk_index": 0, "text": "A"}, {"chunk_index": 1, "text": "B"}]
    assert second_results == first_results
    assert (tmp_path / "extract_chunks" / "chunk_000.json").exists()
    assert (tmp_path / "extract_chunks" / "chunk_001.json").exists()


def test_process_chunks_resumes_from_missing_chunk_only(tmp_path):
    processor = ChunkProcessor(str(tmp_path), "extract_chunks")
    processor.save_chunk_result(0, {"chunk_index": 0, "cached": True})
    calls: list[int] = []
    progress: list[tuple[int, str]] = []

    def handle(index: int, chunk: str) -> dict:
        calls.append(index)
        return {"chunk_index": index, "text": chunk}

    results = processor.process_chunks(
        ["cached", "fresh"],
        handle,
        max_retry=1,
        on_progress=lambda i, _n, status: progress.append((i, status)),
    )

    assert calls == [1]
    assert results == [{"chunk_index": 0, "cached": True}, {"chunk_index": 1, "text": "fresh"}]
    assert (0, "cached") in progress


def test_process_chunks_retries_failed_chunk_only(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.chunk_processor.time.sleep", lambda _seconds: None)
    processor = ChunkProcessor(str(tmp_path), "extract_chunks")
    attempts = {0: 0, 1: 0}

    def handle(index: int, chunk: str) -> dict:
        attempts[index] += 1
        if index == 1 and attempts[index] == 1:
            raise TimeoutError("chunk timeout")
        return {"chunk_index": index, "text": chunk}

    results = processor.process_chunks(["ok", "retry"], handle, max_retry=3)

    assert results == [{"chunk_index": 0, "text": "ok"}, {"chunk_index": 1, "text": "retry"}]
    assert attempts == {0: 1, 1: 2}


def test_process_chunks_raises_after_max_retry(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.chunk_processor.time.sleep", lambda _seconds: None)
    processor = ChunkProcessor(str(tmp_path), "extract_chunks")

    def handle(index: int, chunk: str) -> dict:
        raise TimeoutError(f"timeout {index}: {chunk}")

    with pytest.raises(TimeoutError):
        processor.process_chunks(["fail"], handle, max_retry=2)

    assert not (tmp_path / "extract_chunks" / "chunk_000.json").exists()
