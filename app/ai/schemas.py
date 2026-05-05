"""Pydantic schemas cho output AI Pass 1."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Citation(BaseModel):
    page_no: int
    source_snippet: str
    confidence: float


class Metric(BaseModel):
    metric_key: str
    metric_name: str
    value: str  # number hoặc string
    unit: str = ""
    comparison_type: str = "none"  # yoy, mom, plan_ratio, none
    comparison_value: Optional[float] = None
    citations: list[Citation] = []


class Section(BaseModel):
    section_key: str
    summary: str
    citations: list[Citation] = []


class ReportMetadata(BaseModel):
    title: str
    period: str  # YYYY-MM
    organization: str


class ExtractedReport(BaseModel):
    report_metadata: ReportMetadata
    metrics: list[Metric] = []
    sections: list[Section] = []
    warnings: list[str] = []


class TTSSettings(BaseModel):
    enabled: bool = True
    text: str = ""
    voice: str = "vi-VN-NamMinhNeural"


class DurationPolicy(BaseModel):
    mode: str = "tts_first"  # tts_first, fixed
    min_seconds: int = 4
    max_seconds: int = 20
    buffer_seconds: float = 0.4


class WorkflowScene(BaseModel):
    scene_id: str
    scene_type: str  # intro, content, closing
    title: str
    objective: str = ""
    source_data_keys: list[str] = []
    visual_layers: list = []
    motion: dict = {}
    tts: TTSSettings = TTSSettings()
    duration_policy: DurationPolicy = DurationPolicy()


class WorkflowMetadata(BaseModel):
    template_version: str = "wf.v2"
    report_month: str
    job_id: str


class VideoSettings(BaseModel):
    fps: int = 30
    resolution: str = "1920x1080"
    aspect_ratio: str = "16:9"


class WorkflowOutput(BaseModel):
    workflow_metadata: WorkflowMetadata
    video_settings: VideoSettings = VideoSettings()
    scenes: list[WorkflowScene] = []
