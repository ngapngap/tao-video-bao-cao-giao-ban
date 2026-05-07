"""Pydantic schemas cho output AI Pass 1."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    page_no: Optional[int] = None
    source_snippet: str = ""
    confidence: Optional[float] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def parse_confidence(cls, v):
        """Chấp nhận string 'high'/'medium'/'low' hoặc float."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            mapping = {"high": 0.9, "medium": 0.7, "low": 0.5, "very_high": 0.95}
            if v.lower() in mapping:
                return mapping[v.lower()]
            try:
                return float(v)
            except ValueError:
                return None
        return None


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
    title: str = ""
    period: str = ""  # YYYY-MM
    organization: str = ""


class RawLLMExtractedReport(BaseModel):
    """Schema linh hoạt để parse output LLM, chấp nhận nhiều format."""

    report_month: str = ""
    report_title: str = ""
    report_date: str = ""
    owner_org: str = ""
    issuing_org: str = ""
    report_type: str = ""
    metrics: dict[str, Any] | list[Any] = Field(default_factory=dict)
    sections: list[Any] = Field(default_factory=list)
    warnings: list[str | dict[str, Any]] = Field(default_factory=list)
    issues: dict[str, Any] = Field(default_factory=dict)
    priorities_next_month: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class ExtractedReport(BaseModel):
    report_metadata: ReportMetadata = ReportMetadata(title="", period="", organization="")
    metrics: list[Metric] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"


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
