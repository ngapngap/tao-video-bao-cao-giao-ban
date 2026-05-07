"""Comprehensive tests cho workflow template validation mở rộng."""

from __future__ import annotations

from copy import deepcopy

from app.main import App
from app.workflow import WorkflowValidator


def _sample_extracted_report() -> dict:
    return {
        "report_metadata": {
            "title": "Báo cáo giao ban",
            "period": "2026-05",
            "organization": "Đơn vị mẫu",
        },
        "metrics": [
            {"metric_key": "so_thu", "metric_name": "Số thu", "value": "1234", "unit": "tỷ đồng"},
            {"metric_key": "so_chi", "metric_name": "Số chi", "value": "567", "unit": "tỷ đồng"},
        ],
        "sections": [{"section_key": "danh_gia_chung", "summary": "Tình hình ổn định"}],
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
                "scene_id": "scene_content_02",
                "scene_type": "content",
                "title": "Đánh giá chung",
                "source_data_keys": ["danh_gia_chung"],
                "tts": {"enabled": True, "text": "Tình hình ổn định."},
                "duration_policy": {"mode": "fixed", "min_seconds": 5, "max_seconds": 5},
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


def _validate(workflow: dict, extracted_report: dict | None = None):
    return WorkflowValidator().validate(deepcopy(workflow), deepcopy(extracted_report) if extracted_report else None)


def _codes(result) -> list[str]:
    return [error["code"] for error in result.errors]


def _errors(result, code: str) -> list[dict]:
    return [error for error in result.errors if error["code"] == code]


def test_happy_path_valid_workflow_passes_without_errors():
    result = _validate(_valid_workflow(), _sample_extracted_report())

    assert result.passed is True
    assert result.errors == []


def test_intro_missing_fails_with_intro_count_invalid():
    workflow = _valid_workflow()
    workflow["scenes"] = workflow["scenes"][1:]

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "INTRO_COUNT_INVALID" in _codes(result)


def test_intro_extra_fails_with_intro_count_invalid():
    workflow = _valid_workflow()
    workflow["scenes"].insert(1, {**deepcopy(workflow["scenes"][0]), "scene_id": "scene_intro_2"})

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "INTRO_COUNT_INVALID" in _codes(result)


def test_intro_wrong_position_fails_with_intro_position_invalid():
    workflow = _valid_workflow()
    workflow["scenes"] = [workflow["scenes"][1], workflow["scenes"][0], *workflow["scenes"][2:]]

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "INTRO_POSITION_INVALID" in _codes(result)


def test_closing_missing_fails_with_closing_count_invalid():
    workflow = _valid_workflow()
    workflow["scenes"] = workflow["scenes"][:-1]

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "CLOSING_COUNT_INVALID" in _codes(result)


def test_closing_extra_fails_with_closing_count_invalid():
    workflow = _valid_workflow()
    workflow["scenes"].insert(-1, {**deepcopy(workflow["scenes"][-1]), "scene_id": "scene_closing_2"})

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "CLOSING_COUNT_INVALID" in _codes(result)


def test_closing_wrong_position_fails_with_closing_position_invalid():
    workflow = _valid_workflow()
    workflow["scenes"] = [workflow["scenes"][0], workflow["scenes"][-1], *workflow["scenes"][1:-1]]

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "CLOSING_POSITION_INVALID" in _codes(result)


def test_duplicate_scene_id_fails_with_duplicate_scene_id():
    workflow = _valid_workflow()
    workflow["scenes"][2]["scene_id"] = "scene_content_01"

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "DUPLICATE_SCENE_ID" in _codes(result)


def test_unsupported_scene_type_fails_with_unsupported_scene_type():
    workflow = _valid_workflow()
    workflow["scenes"][1]["scene_type"] = "summary"

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "UNSUPPORTED_SCENE_TYPE" in _codes(result)


def test_missing_scene_id_and_title_fail_with_missing_field():
    workflow = _valid_workflow()
    workflow["scenes"][1]["scene_id"] = " "
    workflow["scenes"][1]["title"] = ""

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert _codes(result).count("MISSING_FIELD") == 2
    assert {error["field"] for error in _errors(result, "MISSING_FIELD")} >= {"scene_id", "title"}


def test_tts_enabled_with_empty_text_fails_with_empty_tts():
    workflow = _valid_workflow()
    workflow["scenes"][1]["tts"] = {"enabled": True, "text": "   "}

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "EMPTY_TTS" in _codes(result)


def test_tts_disabled_with_empty_text_passes():
    workflow = _valid_workflow()
    workflow["scenes"][1]["tts"] = {"enabled": False, "text": ""}

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is True
    assert "EMPTY_TTS" not in _codes(result)


def test_duration_invalid_mode_fails_with_duration_policy_invalid():
    workflow = _valid_workflow()
    workflow["scenes"][1]["duration_policy"]["mode"] = "auto"

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "DURATION_POLICY_INVALID" in _codes(result)


def test_duration_min_seconds_must_be_positive():
    workflow = _valid_workflow()
    workflow["scenes"][1]["duration_policy"]["min_seconds"] = 0

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "DURATION_POLICY_INVALID" in _codes(result)
    assert any(error.get("field") == "duration_policy.min_seconds" for error in result.errors)


def test_duration_max_seconds_must_be_greater_than_or_equal_min_seconds():
    workflow = _valid_workflow()
    workflow["scenes"][1]["duration_policy"] = {"mode": "tts_first", "min_seconds": 10, "max_seconds": 5}

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "DURATION_POLICY_INVALID" in _codes(result)
    assert any(error.get("field") == "duration_policy.max_seconds" for error in result.errors)


def test_missing_duration_policy_fails_with_duration_policy_invalid():
    workflow = _valid_workflow()
    del workflow["scenes"][1]["duration_policy"]

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "DURATION_POLICY_INVALID" in _codes(result)


def test_content_scene_empty_source_keys_warns_without_failing():
    workflow = _valid_workflow()
    workflow["scenes"][1]["source_data_keys"] = []

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is True
    assert "EMPTY_SOURCE_KEYS" in _codes(result)
    assert all(error["severity"] == "WARN" for error in _errors(result, "EMPTY_SOURCE_KEYS"))


def test_source_key_not_found_warns_without_failing():
    workflow = _valid_workflow()
    workflow["scenes"][1]["source_data_keys"] = ["khong_ton_tai"]

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is True
    assert "INVALID_SOURCE_KEY" in _codes(result)
    assert all(error["severity"] == "WARN" for error in _errors(result, "INVALID_SOURCE_KEY"))


def test_missing_workflow_metadata_fails_with_missing_metadata():
    workflow = _valid_workflow()
    del workflow["workflow_metadata"]

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "MISSING_METADATA" in _codes(result)


def test_missing_report_month_and_job_id_fail_with_missing_metadata():
    workflow = _valid_workflow()
    workflow["workflow_metadata"]["report_month"] = ""
    workflow["workflow_metadata"]["job_id"] = " "

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert _codes(result).count("MISSING_METADATA") >= 2
    assert {error.get("field") for error in _errors(result, "MISSING_METADATA")} >= {
        "workflow_metadata.report_month",
        "workflow_metadata.job_id",
    }


def test_invalid_resolution_format_fails_with_missing_metadata():
    workflow = _valid_workflow()
    workflow["video_settings"]["resolution"] = "full-hd"

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "MISSING_METADATA" in _codes(result)
    assert any(error.get("field") == "video_settings.resolution" for error in result.errors)


def test_missing_video_settings_resolution_fails_with_missing_metadata():
    workflow = _valid_workflow()
    workflow["video_settings"] = {}

    result = _validate(workflow, _sample_extracted_report())

    assert result.passed is False
    assert "MISSING_METADATA" in _codes(result)
    assert any(error.get("field") == "video_settings.resolution" for error in result.errors)


def test_validate_extracted_report_happy_path_passes():
    result = WorkflowValidator().validate_extracted_report(_sample_extracted_report())

    assert result.passed is True
    assert result.errors == []


def test_validate_extracted_report_requires_dict():
    result = WorkflowValidator().validate_extracted_report(["not", "dict"])

    assert result.passed is False
    assert "EXTRACTED_REPORT_INVALID" in _codes(result)


def test_validate_extracted_report_requires_report_metadata_title_and_period():
    report = _sample_extracted_report()
    report["report_metadata"] = {"title": "", "period": " "}

    result = WorkflowValidator().validate_extracted_report(report)

    assert result.passed is False
    assert _codes(result).count("MISSING_METADATA") == 2
    assert {error.get("field") for error in _errors(result, "MISSING_METADATA")} == {
        "report_metadata.title",
        "report_metadata.period",
    }


def test_validate_extracted_report_requires_metric_and_section_keys():
    report = _sample_extracted_report()
    report["metrics"][0]["metric_key"] = ""
    report["sections"][0]["section_key"] = " "

    result = WorkflowValidator().validate_extracted_report(report)

    assert result.passed is False
    assert _codes(result).count("MISSING_FIELD") == 2
    assert {error.get("field") for error in _errors(result, "MISSING_FIELD")} == {
        "metrics[0].metric_key",
        "sections[0].section_key",
    }


def test_validate_extracted_report_detects_duplicate_source_keys():
    report = _sample_extracted_report()
    report["sections"].append({"section_key": "so_thu", "summary": "Trùng key với metric"})

    result = WorkflowValidator().validate_extracted_report(report)

    assert result.passed is False
    assert "DUPLICATE_SOURCE_KEY" in _codes(result)


def test_validate_extracted_report_metrics_and_sections_must_be_lists():
    report = _sample_extracted_report()
    report["metrics"] = {"metric_key": "so_thu"}
    report["sections"] = "danh_gia_chung"

    result = WorkflowValidator().validate_extracted_report(report)

    assert result.passed is False
    assert _codes(result).count("EXTRACTED_REPORT_INVALID") == 2
    assert {error.get("field") for error in _errors(result, "EXTRACTED_REPORT_INVALID")} == {"metrics", "sections"}


def test_auto_fix_workflow_removes_duplicate_closings_and_keeps_one_closing_at_end():
    workflow = _valid_workflow()
    duplicate_closing = deepcopy(workflow["scenes"][-1])
    duplicate_closing["scene_id"] = "scene_closing_duplicate"
    duplicate_closing["title"] = "Kết thúc duplicate cuối"
    workflow["scenes"].insert(2, duplicate_closing)

    fixed = App._auto_fix_workflow(object.__new__(App), workflow)
    scenes = fixed["scenes"]
    result = _validate(fixed, _sample_extracted_report())

    assert result.passed is True
    assert [scene["scene_type"] for scene in scenes].count("closing") == 1
    assert scenes[-1]["scene_type"] == "closing"
    assert scenes[-1]["title"] == "Kết thúc"


def test_auto_fix_workflow_removes_duplicate_intros_and_keeps_one_intro_at_start():
    workflow = _valid_workflow()
    duplicate_intro = deepcopy(workflow["scenes"][0])
    duplicate_intro["scene_id"] = "scene_intro_duplicate"
    duplicate_intro["title"] = "Intro duplicate giữa"
    workflow["scenes"].insert(2, duplicate_intro)

    fixed = App._auto_fix_workflow(object.__new__(App), workflow)
    scenes = fixed["scenes"]
    result = _validate(fixed, _sample_extracted_report())

    assert result.passed is True
    assert [scene["scene_type"] for scene in scenes].count("intro") == 1
    assert scenes[0]["scene_type"] == "intro"
    assert scenes[0]["title"] == "Intro"
