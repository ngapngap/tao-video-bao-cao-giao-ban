"""Checkpoint manager cho job_state.json và event log NDJSON."""

from __future__ import annotations

import json
import os
from typing import Optional

from app.core.event_logger import EventLogger
from app.core.models import EventLogEntry, JobState


class CheckpointManager:
    """Lưu/đọc job_state.json và event log."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.state_path = os.path.join(output_dir, "job_state.json")
        self.event_logger = EventLogger(output_dir)
        self.events_path = str(self.event_logger.events_path)

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
        """Ghi 1 dòng event vào NDJSON có mask secret/token."""
        self.event_logger.append(entry)

    def read_events(self, level_filter: Optional[str] = None) -> list[EventLogEntry]:
        """Đọc tất cả events, filter theo level nếu có."""
        return self.event_logger.read(level_filter=level_filter)
