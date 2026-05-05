"""Event logger ghi NDJSON có mask secret/token cho job runtime."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.models import EventLogEntry

TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|apikey|token|authorization|bearer|secret)(\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_-]{8,})"),
    re.compile(r"(?i)(gho_[A-Za-z0-9_]+)"),
    re.compile(r"(?i)(ghp_[A-Za-z0-9_]+)"),
)


def mask_sensitive_text(text: str) -> str:
    """Mask API key/token-like content trước khi ghi log hoặc hiển thị UI."""
    masked = text
    masked = TOKEN_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}****", masked)
    for pattern in TOKEN_PATTERNS[1:]:
        masked = pattern.sub("****", masked)
    return masked


class EventLogger:
    """Ghi và đọc event log dạng NDJSON theo chuẩn outputs/YYYYMM/<job_id>/logs."""

    def __init__(self, output_dir: str | os.PathLike[str]) -> None:
        self.output_dir = Path(output_dir)
        self.logs_dir = self.output_dir / "logs"
        self.events_path = self.logs_dir / "job-events.ndjson"

    def append(self, entry: EventLogEntry) -> None:
        """Append một event đã được mask vào file NDJSON."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        safe_entry = entry.model_copy(update={"message": mask_sensitive_text(entry.message)})
        with self.events_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(safe_entry.model_dump(), ensure_ascii=False) + "\n")

    def log(self, level: str, step_id: Optional[str], message: str, job_id: str) -> None:
        """Tạo EventLogEntry nhanh và ghi xuống file."""
        self.append(
            EventLogEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                level=level.upper(),
                step_id=step_id,
                message=message,
                job_id=job_id,
            )
        )

    def read(self, level_filter: Optional[str] = None) -> list[EventLogEntry]:
        """Đọc event log thực từ file, có thể lọc theo level."""
        if not self.events_path.exists():
            return []
        normalized_level = level_filter.upper() if level_filter else None
        events: list[EventLogEntry] = []
        with self.events_path.open("r", encoding="utf-8") as file:
            for line in file:
                stripped = line.strip()
                if not stripped:
                    continue
                entry = EventLogEntry.model_validate(json.loads(stripped))
                if normalized_level and entry.level.upper() != normalized_level:
                    continue
                events.append(entry)
        return events
