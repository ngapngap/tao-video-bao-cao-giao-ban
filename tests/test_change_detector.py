"""Tests cho ChangeDetector tối ưu polling Job & Logs screen."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.ui.screens.job_logs_screen import ChangeDetector


def _wait_for_mtime_tick() -> None:
    """Đảm bảo filesystem ghi nhận mtime khác nhau trên Windows."""
    time.sleep(0.02)


def test_has_changed_returns_false_when_file_is_unchanged(tmp_path: Path) -> None:
    file_path = tmp_path / "job_state.json"
    file_path.write_text('{"status":"RUNNING"}', encoding="utf-8")

    detector = ChangeDetector()

    assert detector.has_changed(str(file_path)) is True
    assert detector.has_changed(str(file_path)) is False


def test_has_changed_returns_true_when_content_changes(tmp_path: Path) -> None:
    file_path = tmp_path / "job_state.json"
    file_path.write_text('{"status":"RUNNING"}', encoding="utf-8")

    detector = ChangeDetector()
    assert detector.has_changed(str(file_path)) is True

    _wait_for_mtime_tick()
    file_path.write_text('{"status":"DONE"}', encoding="utf-8")

    assert detector.has_changed(str(file_path)) is True


def test_has_changed_returns_false_when_mtime_changes_but_content_same(tmp_path: Path) -> None:
    file_path = tmp_path / "job_state.json"
    content = '{"status":"RUNNING"}'
    file_path.write_text(content, encoding="utf-8")

    detector = ChangeDetector()
    assert detector.has_changed(str(file_path)) is True

    _wait_for_mtime_tick()
    os.utime(file_path, None)

    assert detector.has_changed(str(file_path)) is False


def test_get_new_lines_only_returns_lines_after_offset(tmp_path: Path) -> None:
    file_path = tmp_path / "job-events.ndjson"
    file_path.write_text("line1\nline2\n", encoding="utf-8")

    detector = ChangeDetector()
    new_lines, total = detector.get_new_lines(str(file_path), 0)

    assert new_lines == ["line1\n", "line2\n"]
    assert total == 2

    with file_path.open("a", encoding="utf-8") as file:
        file.write("line3\nline4\n")

    new_lines, total = detector.get_new_lines(str(file_path), 2)

    assert new_lines == ["line3\n", "line4\n"]
    assert total == 4


def test_has_changed_returns_false_when_file_does_not_exist(tmp_path: Path) -> None:
    detector = ChangeDetector()

    assert detector.has_changed(str(tmp_path / "missing.ndjson")) is False
