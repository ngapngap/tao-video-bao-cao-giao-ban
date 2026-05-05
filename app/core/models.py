"""Data models cho job engine core."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    """Trạng thái thực thi của một step trong job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    WAITING_RETRY = "WAITING_RETRY"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    """Trạng thái lifecycle chuẩn của job."""

    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_RETRY = "WAITING_RETRY"
    PARTIAL_DONE = "PARTIAL_DONE"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class StepRecord(BaseModel):
    """Checkpoint state của một step."""

    step_id: str
    name: str
    status: StepStatus = StepStatus.PENDING
    attempt: int = 0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    artifacts: list[str] = Field(default_factory=list)


class JobState(BaseModel):
    """Checkpoint state tổng thể của một job."""

    job_id: str
    status: JobStatus = JobStatus.DRAFT
    report_month: str
    current_step_id: Optional[str] = None
    steps: list[StepRecord] = Field(default_factory=list)
    created_at: str
    updated_at: str


class EventLogEntry(BaseModel):
    """Một dòng log sự kiện dạng NDJSON."""

    timestamp: str
    level: str  # INFO, WARN, ERROR
    step_id: Optional[str] = None
    message: str
    job_id: str


class StepResult(BaseModel):
    """Kết quả trả về từ step handler."""

    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    artifacts: list[str] = Field(default_factory=list)
