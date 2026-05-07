"""Workflow validator cho các rule bắt buộc."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel


class WorkflowValidationResult(BaseModel):
    passed: bool
    errors: list[dict]
    suggested_fixes: list[str]


class TemplateValidationResult(BaseModel):
    passed: bool
    errors: list[dict]


class WorkflowValidator:
    """Validate workflow theo rules bắt buộc."""

    SUPPORTED_DURATION_MODES = {"tts_first", "fixed"}
    SUPPORTED_SCENE_TYPES = {"intro", "content", "closing"}
    RESOLUTION_PATTERN = re.compile(r"^\d+x\d+$")

    def validate(self, workflow: dict, extracted_report: dict | None = None) -> WorkflowValidationResult:
        errors: list[dict[str, Any]] = []
        workflow = self._normalize_workflow(workflow)

        self._validate_workflow_metadata(workflow, errors)

        scenes = workflow.get("scenes", [])
        if not scenes:
            errors.append({"code": "NO_SCENES", "message": "Workflow không có scene nào", "severity": "ERROR"})
            return WorkflowValidationResult(passed=False, errors=errors, suggested_fixes=["Thêm scene vào workflow"])

        intro_scenes = [scene for scene in scenes if scene.get("scene_type") == "intro"]
        if len(intro_scenes) != 1:
            errors.append(
                {
                    "code": "INTRO_COUNT_INVALID",
                    "message": f"Cần đúng 1 intro, tìm thấy {len(intro_scenes)}",
                    "severity": "ERROR",
                }
            )
        elif scenes[0].get("scene_type") != "intro":
            errors.append({"code": "INTRO_POSITION_INVALID", "message": "Intro phải ở scene đầu tiên", "severity": "ERROR"})

        closing_scenes = [scene for scene in scenes if scene.get("scene_type") == "closing"]
        if len(closing_scenes) != 1:
            errors.append(
                {
                    "code": "CLOSING_COUNT_INVALID",
                    "message": f"Cần đúng 1 closing, tìm thấy {len(closing_scenes)}",
                    "severity": "ERROR",
                }
            )
        elif scenes[-1].get("scene_type") != "closing":
            errors.append(
                {"code": "CLOSING_POSITION_INVALID", "message": "Closing phải ở scene cuối cùng", "severity": "ERROR"}
            )

        scene_ids = [scene.get("scene_id") for scene in scenes]
        non_empty_scene_ids = [scene_id for scene_id in scene_ids if self._is_non_empty_string(scene_id)]
        if len(non_empty_scene_ids) != len(set(non_empty_scene_ids)):
            errors.append({"code": "DUPLICATE_SCENE_ID", "message": "Có scene_id trùng lặp", "severity": "ERROR"})

        valid_keys = self._valid_source_keys(extracted_report) if extracted_report else set()

        for index, scene in enumerate(scenes):
            scene_id = scene.get("scene_id") if self._is_non_empty_string(scene.get("scene_id")) else f"scene_index_{index}"
            self._validate_required_scene_fields(scene, scene_id, errors)
            self._validate_scene_type(scene, scene_id, errors)
            self._validate_tts(scene, scene_id, errors)
            self._validate_duration_policy(scene, scene_id, errors)
            self._validate_source_data_keys(scene, scene_id, valid_keys, extracted_report is not None, errors)

        return WorkflowValidationResult(
            passed=not any(error.get("severity") == "ERROR" for error in errors),
            errors=errors,
            suggested_fixes=[],
        )

    def validate_template(self, template_content: str) -> TemplateValidationResult:
        """Kiểm tra template workflow.md có hợp lệ về cấu trúc không.
        Không validate values vì template dùng placeholders.
        """
        errors: list[dict[str, str]] = []
        normalized_content = template_content.lower()

        if not re.search(r"scene_type\s*[:=].*intro", template_content, re.IGNORECASE) and "intro" not in normalized_content:
            errors.append({"code": "MISSING_INTRO_TEMPLATE", "message": "Template thiếu scene intro"})

        if not re.search(r"scene_type\s*[:=].*closing", template_content, re.IGNORECASE) and "closing" not in normalized_content:
            errors.append({"code": "MISSING_CLOSING_TEMPLATE", "message": "Template thiếu scene closing"})

        required_fields = ["scene_id", "scene_type", "title", "tts", "duration_policy"]
        for field in required_fields:
            if field not in template_content:
                errors.append({"code": "MISSING_TEMPLATE_FIELD", "message": f"Template thiếu field {field}"})

        if "INTRO_COUNT_EXACTLY_ONE" not in template_content:
            errors.append({"code": "MISSING_VALIDATION_RULES", "message": "Template thiếu validation rules"})

        return TemplateValidationResult(
            passed=len(errors) == 0,
            errors=errors,
        )

    def validate_extracted_report(self, extracted_report: dict) -> WorkflowValidationResult:
        """Validate extracted report dict trước khi dùng làm nguồn sinh workflow."""
        errors: list[dict[str, Any]] = []

        if not isinstance(extracted_report, dict):
            errors.append(
                {
                    "code": "EXTRACTED_REPORT_INVALID",
                    "message": "Extracted report phải là dict",
                    "severity": "ERROR",
                }
            )
            return WorkflowValidationResult(passed=False, errors=errors, suggested_fixes=[])

        report_metadata = extracted_report.get("report_metadata")
        if not isinstance(report_metadata, dict):
            errors.append(
                {
                    "code": "MISSING_METADATA",
                    "message": "Extracted report thiếu report_metadata",
                    "severity": "ERROR",
                }
            )
        else:
            for field in ("title", "period"):
                if not self._is_non_empty_string(report_metadata.get(field)):
                    errors.append(
                        {
                            "code": "MISSING_METADATA",
                            "field": f"report_metadata.{field}",
                            "message": f"Extracted report thiếu report_metadata.{field}",
                            "severity": "ERROR",
                        }
                    )

        metrics = extracted_report.get("metrics", [])
        sections = extracted_report.get("sections", [])
        self._validate_extracted_collection(metrics, "metrics", "metric_key", errors)
        self._validate_extracted_collection(sections, "sections", "section_key", errors)

        duplicate_keys = self._duplicates(
            [
                key
                for key in [*self._collect_keys(metrics, "metric_key"), *self._collect_keys(sections, "section_key")]
                if self._is_non_empty_string(key)
            ]
        )
        for key in duplicate_keys:
            errors.append(
                {
                    "code": "DUPLICATE_SOURCE_KEY",
                    "source_key": key,
                    "message": f"Extracted report có source key trùng lặp: {key}",
                    "severity": "ERROR",
                }
            )

        return WorkflowValidationResult(
            passed=not any(error.get("severity") == "ERROR" for error in errors),
            errors=errors,
            suggested_fixes=[],
        )

    def _normalize_workflow(self, workflow: dict) -> dict:
        """Normalize workflow fields that LLM may return in compatible alternate shapes."""
        if not isinstance(workflow, dict):
            return workflow

        video_settings = workflow.get("video_settings")
        if not isinstance(video_settings, dict):
            return workflow

        resolution = video_settings.get("resolution")
        if isinstance(resolution, dict):
            width = resolution.get("width", 1920)
            height = resolution.get("height", 1080)
            video_settings["resolution"] = f"{width}x{height}"

        return workflow

    def _validate_workflow_metadata(self, workflow: dict, errors: list[dict[str, Any]]) -> None:
        metadata = workflow.get("workflow_metadata")
        if not isinstance(metadata, dict):
            errors.append(
                {
                    "code": "MISSING_METADATA",
                    "message": "Workflow thiếu workflow_metadata",
                    "severity": "ERROR",
                }
            )
        else:
            for field in ("report_month", "job_id"):
                if not self._is_non_empty_string(metadata.get(field)):
                    errors.append(
                        {
                            "code": "MISSING_METADATA",
                            "field": f"workflow_metadata.{field}",
                            "message": f"Workflow thiếu workflow_metadata.{field}",
                            "severity": "ERROR",
                        }
                    )

        video_settings = workflow.get("video_settings")
        resolution = video_settings.get("resolution") if isinstance(video_settings, dict) else None
        if not self._is_non_empty_string(resolution) or not self.RESOLUTION_PATTERN.match(resolution):
            errors.append(
                {
                    "code": "MISSING_METADATA",
                    "field": "video_settings.resolution",
                    "message": "Workflow thiếu video_settings.resolution hoặc resolution không đúng format WxH",
                    "severity": "ERROR",
                }
            )

    def _validate_required_scene_fields(
        self, scene: dict, scene_id: str, errors: list[dict[str, Any]]
    ) -> None:
        for field in ("scene_id", "title"):
            if not self._is_non_empty_string(scene.get(field)):
                errors.append(
                    {
                        "code": "MISSING_FIELD",
                        "scene_id": scene_id,
                        "field": field,
                        "message": f"Scene {scene_id} thiếu field bắt buộc: {field}",
                        "severity": "ERROR",
                    }
                )

    def _validate_scene_type(self, scene: dict, scene_id: str, errors: list[dict[str, Any]]) -> None:
        scene_type = scene.get("scene_type")
        if scene_type not in self.SUPPORTED_SCENE_TYPES:
            errors.append(
                {
                    "code": "UNSUPPORTED_SCENE_TYPE",
                    "scene_id": scene_id,
                    "message": f"Scene {scene_id} có scene_type không hỗ trợ: {scene_type}",
                    "severity": "ERROR",
                }
            )

    def _validate_tts(self, scene: dict, scene_id: str, errors: list[dict[str, Any]]) -> None:
        tts = scene.get("tts", {})
        if tts.get("enabled", True) and not tts.get("text", "").strip():
            errors.append(
                {
                    "code": "EMPTY_TTS",
                    "scene_id": scene_id,
                    "message": f"Scene {scene_id} có tts.enabled=true nhưng text rỗng",
                    "severity": "ERROR",
                }
            )

    def _validate_duration_policy(self, scene: dict, scene_id: str, errors: list[dict[str, Any]]) -> None:
        policy = scene.get("duration_policy")
        if not isinstance(policy, dict):
            errors.append(
                {
                    "code": "DURATION_POLICY_INVALID",
                    "scene_id": scene_id,
                    "message": f"Scene {scene_id} thiếu duration_policy",
                    "severity": "ERROR",
                }
            )
            return

        mode = policy.get("mode")
        min_seconds = policy.get("min_seconds")
        max_seconds = policy.get("max_seconds")
        if mode not in self.SUPPORTED_DURATION_MODES:
            errors.append(
                {
                    "code": "DURATION_POLICY_INVALID",
                    "scene_id": scene_id,
                    "field": "duration_policy.mode",
                    "message": f"Scene {scene_id} có duration_policy.mode không hợp lệ: {mode}",
                    "severity": "ERROR",
                }
            )

        if not self._is_positive_number(min_seconds):
            errors.append(
                {
                    "code": "DURATION_POLICY_INVALID",
                    "scene_id": scene_id,
                    "field": "duration_policy.min_seconds",
                    "message": f"Scene {scene_id} có duration_policy.min_seconds phải > 0",
                    "severity": "ERROR",
                }
            )

        if not self._is_number(max_seconds) or (self._is_number(min_seconds) and max_seconds < min_seconds):
            errors.append(
                {
                    "code": "DURATION_POLICY_INVALID",
                    "scene_id": scene_id,
                    "field": "duration_policy.max_seconds",
                    "message": f"Scene {scene_id} có duration_policy.max_seconds phải >= min_seconds",
                    "severity": "ERROR",
                }
            )

    def _validate_source_data_keys(
        self,
        scene: dict,
        scene_id: str,
        valid_keys: set[str],
        has_extracted_report: bool,
        errors: list[dict[str, Any]],
    ) -> None:
        if scene.get("scene_type") != "content":
            return

        source_keys = scene.get("source_data_keys", [])
        if not source_keys:
            errors.append(
                {
                    "code": "EMPTY_SOURCE_KEYS",
                    "scene_id": scene_id,
                    "message": f"Content scene {scene_id} không có source_data_keys",
                    "severity": "WARN",
                }
            )
            return

        if not has_extracted_report:
            return

        for key in source_keys:
            if key not in valid_keys:
                errors.append(
                    {
                        "code": "INVALID_SOURCE_KEY",
                        "scene_id": scene_id,
                        "message": f"source_data_key '{key}' không tồn tại trong extracted report",
                        "severity": "WARN",
                    }
                )

    def _validate_extracted_collection(
        self,
        collection: Any,
        collection_name: str,
        key_field: str,
        errors: list[dict[str, Any]],
    ) -> None:
        if collection is None:
            return
        if not isinstance(collection, list):
            errors.append(
                {
                    "code": "EXTRACTED_REPORT_INVALID",
                    "field": collection_name,
                    "message": f"Extracted report field {collection_name} phải là list",
                    "severity": "ERROR",
                }
            )
            return

        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                errors.append(
                    {
                        "code": "EXTRACTED_REPORT_INVALID",
                        "field": f"{collection_name}[{index}]",
                        "message": f"{collection_name}[{index}] phải là dict",
                        "severity": "ERROR",
                    }
                )
                continue
            if not self._is_non_empty_string(item.get(key_field)):
                errors.append(
                    {
                        "code": "MISSING_FIELD",
                        "field": f"{collection_name}[{index}].{key_field}",
                        "message": f"{collection_name}[{index}] thiếu {key_field}",
                        "severity": "ERROR",
                    }
                )

    def _valid_source_keys(self, extracted_report: dict | None) -> set[str]:
        if not extracted_report:
            return set()
        return {
            key
            for key in [
                *self._collect_keys(extracted_report.get("metrics", []), "metric_key"),
                *self._collect_keys(extracted_report.get("sections", []), "section_key"),
            ]
            if self._is_non_empty_string(key)
        }

    @staticmethod
    def _collect_keys(collection: Any, key_field: str) -> list[str]:
        if not isinstance(collection, list):
            return []
        return [item.get(key_field, "") for item in collection if isinstance(item, dict)]

    @staticmethod
    def _duplicates(values: Iterable[str]) -> list[str]:
        seen = set()
        duplicates = []
        for value in values:
            if value in seen and value not in duplicates:
                duplicates.append(value)
            seen.add(value)
        return duplicates

    @staticmethod
    def _is_non_empty_string(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _is_positive_number(self, value: Any) -> bool:
        return self._is_number(value) and value > 0
