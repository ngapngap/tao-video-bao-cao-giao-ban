"""Tests cho Pydantic schemas AI Pass 1."""

from __future__ import annotations

from app.ai import ExtractedReport, WorkflowOutput


def test_extracted_report_parses_from_dict():
    report = ExtractedReport(
        **{
            "report_metadata": {
                "title": "Báo cáo giao ban tháng 05/2026",
                "period": "2026-05",
                "organization": "Đơn vị mẫu",
            },
            "metrics": [
                {
                    "metric_key": "so_thu",
                    "metric_name": "Số thu",
                    "value": "1234",
                    "unit": "tỷ đồng",
                    "comparison_type": "plan_ratio",
                    "comparison_value": 0.95,
                    "citations": [{"page_no": 1, "source_snippet": "Số thu 1234 tỷ đồng", "confidence": 0.98}],
                }
            ],
            "sections": [
                {
                    "section_key": "danh_gia_chung",
                    "summary": "Tình hình ổn định",
                    "citations": [{"page_no": 2, "source_snippet": "Tình hình ổn định", "confidence": 0.9}],
                }
            ],
            "warnings": ["Thiếu số liệu chi tiết nhóm A"],
        }
    )

    assert report.report_metadata.period == "2026-05"
    assert report.metrics[0].metric_key == "so_thu"
    assert report.metrics[0].citations[0].page_no == 1
    assert report.sections[0].section_key == "danh_gia_chung"
    assert report.warnings == ["Thiếu số liệu chi tiết nhóm A"]


def test_workflow_output_parses_from_dict():
    workflow = WorkflowOutput(
        **{
            "workflow_metadata": {"template_version": "wf.v2", "report_month": "2026-05", "job_id": "job-001"},
            "video_settings": {"fps": 30, "resolution": "1920x1080", "aspect_ratio": "16:9"},
            "scenes": [
                {
                    "scene_id": "scene_intro",
                    "scene_type": "intro",
                    "title": "Giới thiệu",
                    "objective": "Mở đầu video",
                    "source_data_keys": [],
                    "visual_layers": [],
                    "motion": {},
                    "tts": {"enabled": True, "text": "Xin chào.", "voice": "vi-VN-NamMinhNeural"},
                    "duration_policy": {
                        "mode": "tts_first",
                        "min_seconds": 4,
                        "max_seconds": 12,
                        "buffer_seconds": 0.4,
                    },
                },
                {
                    "scene_id": "scene_closing",
                    "scene_type": "closing",
                    "title": "Kết thúc",
                    "tts": {"enabled": False, "text": ""},
                },
            ],
        }
    )

    assert workflow.workflow_metadata.job_id == "job-001"
    assert workflow.video_settings.resolution == "1920x1080"
    assert workflow.scenes[0].tts.enabled is True
    assert workflow.scenes[0].duration_policy.mode == "tts_first"
    assert workflow.scenes[1].tts.enabled is False
