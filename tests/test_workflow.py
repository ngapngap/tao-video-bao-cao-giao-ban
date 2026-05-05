"""Tests cho workflow composer và validator."""

from __future__ import annotations

from app.workflow import WorkflowComposer, WorkflowValidator


def _sample_extracted_report() -> dict:
    return {
        "report_metadata": {
            "title": "Báo cáo giao ban",
            "period": "2026-05",
            "organization": "Đơn vị mẫu",
        },
        "metrics": [
            {
                "metric_key": "so_thu",
                "metric_name": "Số thu",
                "value": "1234",
                "unit": "tỷ đồng",
                "citations": [{"page_no": 1, "source_snippet": "Số thu 1234 tỷ đồng", "confidence": 0.95}],
            },
            {
                "metric_key": "so_chi",
                "metric_name": "Số chi",
                "value": "567",
                "unit": "tỷ đồng",
                "citations": [{"page_no": 1, "source_snippet": "Số chi 567 tỷ đồng", "confidence": 0.9}],
            },
        ],
        "sections": [
            {
                "section_key": "danh_gia_chung",
                "summary": "Tình hình ổn định",
                "citations": [{"page_no": 1, "source_snippet": "Tình hình ổn định", "confidence": 0.8}],
            }
        ],
        "warnings": [],
    }


def _valid_workflow() -> dict:
    return {
        "workflow_metadata": {"template_version": "wf.v2", "report_month": "2026-05", "job_id": "job-001"},
        "video_settings": {"fps": 30, "resolution": "1920x1080", "aspect_ratio": "16:9"},
        "scenes": [
            {
                "scene_id": "scene_intro",
                "scene_type": "intro",
                "title": "Intro",
                "source_data_keys": [],
                "tts": {"enabled": True, "text": "Xin chào."},
                "duration_policy": {"mode": "tts_first", "min_seconds": 4, "max_seconds": 12},
            },
            {
                "scene_id": "scene_content_01",
                "scene_type": "content",
                "title": "Số thu",
                "source_data_keys": ["so_thu"],
                "tts": {"enabled": True, "text": "Số thu đạt 1234 tỷ đồng."},
                "duration_policy": {"mode": "tts_first", "min_seconds": 5, "max_seconds": 20},
            },
            {
                "scene_id": "scene_closing",
                "scene_type": "closing",
                "title": "Kết thúc",
                "source_data_keys": [],
                "tts": {"enabled": False, "text": ""},
                "duration_policy": {"mode": "fixed", "min_seconds": 4, "max_seconds": 8},
            },
        ],
    }


def _codes(result) -> list[str]:
    return [error["code"] for error in result.errors]


def test_compose_from_extracted_report_creates_intro_content_and_closing():
    workflow = WorkflowComposer().compose_from_extracted_report(_sample_extracted_report(), "2026-05", "job-001")

    scenes = workflow["scenes"]
    assert workflow["workflow_metadata"] == {
        "template_version": "wf.v2",
        "report_month": "2026-05",
        "job_id": "job-001",
    }
    assert len(scenes) == 4
    assert scenes[0]["scene_type"] == "intro"
    assert scenes[1]["scene_type"] == "content"
    assert scenes[2]["scene_type"] == "content"
    assert scenes[-1]["scene_type"] == "closing"
    assert scenes[1]["source_data_keys"] == ["so_thu"]
    assert scenes[2]["source_data_keys"] == ["so_chi"]


def test_validate_valid_workflow_passes():
    result = WorkflowValidator().validate(_valid_workflow(), _sample_extracted_report())

    assert result.passed is True
    assert result.errors == []


def test_validate_missing_intro_fails_with_intro_count_invalid():
    workflow = _valid_workflow()
    workflow["scenes"] = workflow["scenes"][1:]

    result = WorkflowValidator().validate(workflow)

    assert result.passed is False
    assert "INTRO_COUNT_INVALID" in _codes(result)


def test_validate_intro_in_middle_fails_with_intro_position_invalid():
    workflow = _valid_workflow()
    workflow["scenes"] = [workflow["scenes"][1], workflow["scenes"][0], workflow["scenes"][2]]

    result = WorkflowValidator().validate(workflow)

    assert result.passed is False
    assert "INTRO_POSITION_INVALID" in _codes(result)


def test_validate_empty_tts_text_fails_with_empty_tts():
    workflow = _valid_workflow()
    workflow["scenes"][1]["tts"] = {"enabled": True, "text": ""}

    result = WorkflowValidator().validate(workflow)

    assert result.passed is False
    assert "EMPTY_TTS" in _codes(result)


def test_validate_duplicate_scene_id_fails():
    workflow = _valid_workflow()
    workflow["scenes"][1]["scene_id"] = "scene_intro"

    result = WorkflowValidator().validate(workflow)

    assert result.passed is False
    assert "DUPLICATE_SCENE_ID" in _codes(result)


def test_validate_invalid_source_data_key_warns_without_failing():
    workflow = _valid_workflow()
    workflow["scenes"][1]["source_data_keys"] = ["khong_ton_tai"]

    result = WorkflowValidator().validate(workflow, _sample_extracted_report())

    assert result.passed is True
    assert "INVALID_SOURCE_KEY" in _codes(result)
    assert any(error["severity"] == "WARN" for error in result.errors)
