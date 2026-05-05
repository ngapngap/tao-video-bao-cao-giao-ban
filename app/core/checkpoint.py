"""Checkpoint manager cho job_state.json và event log NDJSON."""

from __future__ import annotations

import json
import os
from typing import Optional

from app.core.models import EventLogEntry, JobState


class CheckpointManager:
    """Lưu/đọc job_state.json và event log."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.state_path = os.path.join(output_dir, "job_state.json")
        self.events_path = os.path.join(output_dir, "logs", "job-events.ndjson")

    def save_state(self, job_state: JobState):
        """Ghi job_state.json."""
        os.makedirs(self.output_dir, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(job_state.model_dump(), f, ensure_ascii=False, indent=2)

    def load_state(self) -> Optional[JobState]:
        """Đọc job_state.json nếu tồn tại."""
        if not os.path.exists(self.state_path):
            return None
        with open(self.state_path, "r", encoding="utf-8") as f:
            return JobState.model_validate(json.load(f))

    def append_event(self, entry: EventLogEntry):
        """Ghi 1 dòng event vào NDJSON."""
        os.makedirs(os.path.dirname(self.events_path), exist_ok=True)
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")

    def read_events(self, level_filter: Optional[str] = None) -> list[EventLogEntry]:
        """Đọc tất cả events, filter theo level nếu có."""
        if not os.path.exists(self.events_path):
            return []

        normalized_level = level_filter.upper() if level_filter else None
        events: list[EventLogEntry] = []
        with open(self.events_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                entry = EventLogEntry.model_validate(json.loads(stripped))
                if normalized_level and entry.level.upper() != normalized_level:
                    continue
                events.append(entry)
        return events
