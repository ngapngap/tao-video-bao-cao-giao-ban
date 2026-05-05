"""Entrypoint cho ứng dụng Báo Cáo Giao Ban - Video Generator."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk

from app.ai import ExtractedReport, LLMClient, P1_1_PDF_EXTRACTION, P1_2_WORKFLOW_COMPOSITION, WorkflowOutput
from app.core import EventLogger, JobRunner, JobState, JobStatus, RetryPolicy, StepRecord, StepResult
from app.core.event_logger import mask_sensitive_text
from app.pdf.normalizer import DataNormalizer
from app.pdf.parser import PDFParser
from app.ui import tokens
from app.ui.navigation import NavigationController
from app.ui.screens import ConfigScreen, CreateVideoScreen, HistoryScreen, JobLogsScreen
from app.ui.sidebar import SidebarFrame
from app.ui.topbar import TopBarFrame
from app.video.prompts import (
    S2_1_SCENE_PLANNING,
    S2_2_VISUAL_SPEC,
    S2_3_NARRATION_TTS,
    S2_4_COMPONENT_SPEC,
    S2_5_ASSET_PLAN,
    S2_6_RENDER_PLAN,
    S2_7_QA_FIX,
    S2_8_FINAL_PACKAGING,
)
from app.video.remotion_handoff import FinalPackager, RemotionManifest, RenderGate, TTSGenerator
from app.workflow import WorkflowComposer, WorkflowValidator

APP_TITLE = "Báo Cáo Giao Ban - Video Generator"
SCREEN_TITLES = {
    "create_video": "Tạo video",
    "config": "Cấu hình",
    "job_logs": "Job & Logs",
    "history": "Lịch sử",
}
STATUS_TEXT = {
    JobStatus.DRAFT: "Nháp",
    JobStatus.QUEUED: "Đang chờ",
    JobStatus.RUNNING: "Đang chạy",
    JobStatus.WAITING_RETRY: "Chờ thử lại",
    JobStatus.PARTIAL_DONE: "Hoàn thành một phần",
    JobStatus.DONE: "Hoàn thành",
    JobStatus.FAILED: "Thất bại",
    JobStatus.CANCELED: "Đã hủy",
}
DEFAULT_STEPS: tuple[tuple[str, str], ...] = (
    ("S1.1", "Chuẩn bị thư mục job"),
    ("S1.2", "Sao chép PDF đầu vào"),
    ("S1.3", "Đọc và chuẩn hóa PDF"),
    ("P1.1", "Trích xuất số liệu báo cáo"),
    ("P1.2", "Sinh workflow mới"),
    ("S2.1", "Lập kế hoạch scene video"),
    ("S2.2", "Tạo visual spec"),
    ("S2.3", "Tạo kịch bản lời đọc TTS"),
    ("S2.4", "Tạo component spec Remotion"),
    ("S2.5", "Tạo asset plan"),
    ("S2.6", "Tạo render plan"),
    ("S2.7", "QA và fix preview"),
    ("S2.8", "Đóng gói video final"),
)
VIDEO_PROMPTS = {
    "S2.1": S2_1_SCENE_PLANNING,
    "S2.2": S2_2_VISUAL_SPEC,
    "S2.3": S2_3_NARRATION_TTS,
    "S2.4": S2_4_COMPONENT_SPEC,
    "S2.5": S2_5_ASSET_PLAN,
    "S2.6": S2_6_RENDER_PLAN,
    "S2.7": S2_7_QA_FIX,
    "S2.8": S2_8_FINAL_PACKAGING,
}


class App(ctk.CTk):
    """App shell chính gồm sidebar, topbar và content area."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(tokens.WINDOW_SIZE)
        self.minsize(tokens.WINDOW_MIN_WIDTH, tokens.WINDOW_MIN_HEIGHT)
        self.configure(fg_color=tokens.COLOR_BACKGROUND)
        self.active_runner: JobRunner | None = None
        self.current_job_state: JobState | None = None
        self.current_job_started_at: datetime | None = None
        self.history_jobs: list[object] = []
        self.runtime_config: dict[str, Any] = self._default_runtime_config()

        self.grid_columnconfigure(0, minsize=tokens.SIDEBAR_WIDTH, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, minsize=tokens.TOPBAR_HEIGHT, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self.sidebar = SidebarFrame(self, on_nav_change=self.show_screen)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.topbar = TopBarFrame(self, title=SCREEN_TITLES["create_video"], status="Sẵn sàng", on_open_outputs=self.open_outputs, on_open_config=lambda: self.show_screen("config"))
        self.topbar.grid(row=0, column=1, sticky="nsew")
        self.content = ctk.CTkFrame(self, fg_color=tokens.COLOR_BACKGROUND, corner_radius=0)
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.navigation = NavigationController(self.content)
        self.navigation.add_change_listener(self._handle_screen_changed)
        self._register_screens()
        self.show_screen("create_video")

    def _register_screens(self) -> None:
        self.create_video_screen = CreateVideoScreen(self.content, on_view_job_details=self._show_job_logs_from_create, on_start_job=self._start_job_from_create)
        self.config_screen = ConfigScreen(self.content, on_config_saved=self._handle_config_saved)
        self.job_logs_screen = JobLogsScreen(self.content, on_open_output=self.open_outputs, on_cancel_job=self._cancel_current_job)
        self.history_screen = HistoryScreen(self.content, on_view_details=self._show_job_logs_from_history, on_delete_job=self._delete_job_from_history)
        self.navigation.register("create_video", self.create_video_screen)
        self.navigation.register("config", self.config_screen)
        self.navigation.register("job_logs", self.job_logs_screen)
        self.navigation.register("history", self.history_screen)

    def show_screen(self, screen_name: str) -> None:
        """Chuyển sang screen tương ứng từ sidebar/topbar."""
        self.navigation.show(screen_name)

    def _show_job_logs_from_create(self) -> None:
        if self.current_job_state is not None:
            self.job_logs_screen.set_job_state(self.current_job_state, self._current_output_dir())
        self.show_screen("job_logs")

    def _show_job_logs_from_history(self, job_id: str) -> None:
        if self.current_job_state is not None and self.current_job_state.job_id == job_id:
            self.job_logs_screen.set_job_state(self.current_job_state, self._current_output_dir())
        self.show_screen("job_logs")

    def _handle_config_saved(self) -> None:
        self.runtime_config = self.config_screen.get_config()
        llm_ready, tts_ready = self.config_screen.is_config_ready()
        self.create_video_screen.set_config_ready(llm_ready=llm_ready, tts_ready=tts_ready)
        self.sidebar.set_config_status("Sẵn sàng" if llm_ready and tts_ready else "Chưa sẵn sàng")

    def _handle_screen_changed(self, screen_name: str) -> None:
        self.sidebar.set_active(screen_name)
        self.topbar.set_title(SCREEN_TITLES.get(screen_name, screen_name))

    def _start_job_from_create(self, payload: dict[str, str]) -> None:
        if self.active_runner is not None and self.current_job_state is not None and self.current_job_state.status == JobStatus.RUNNING:
            self.create_video_screen.set_current_job(self.current_job_state, self.current_job_started_at)
            return
        self.runtime_config = self.config_screen.get_config()
        now = datetime.now(timezone.utc)
        job_id = now.strftime("%Y%m%d-%H%M%S")
        report_month = payload.get("report_month", now.strftime("%Y%m"))
        output_dir = Path(payload.get("output_root") or "outputs") / report_month / job_id
        steps = [StepRecord(step_id=step_id, name=name) for step_id, name in DEFAULT_STEPS]
        job_state = JobState(job_id=job_id, status=JobStatus.QUEUED, report_month=report_month, current_step_id=steps[0].step_id, steps=steps, created_at=now.isoformat(), updated_at=now.isoformat())
        self.current_job_state = job_state
        self.current_job_started_at = now
        runtime_policy = self.runtime_config.get("runtime_policy", {})
        self.active_runner = JobRunner(
            job_state,
            str(output_dir),
            retry_policy=RetryPolicy(
                max_retry=int(runtime_policy.get("max_retry") or 3),
                backoff_seconds=float(runtime_policy.get("retry_backoff_seconds") or 30),
                step_timeout=float(runtime_policy.get("step_timeout_seconds") or 600),
            ),
        )
        self._register_job_step_handlers(self.active_runner, payload)
        self.create_video_screen.set_current_job(job_state, now)
        self.job_logs_screen.set_job_state(job_state, str(output_dir))
        self.history_screen.upsert_job(job_state, payload, str(output_dir))
        self.topbar.set_status("Đang chạy")
        thread = threading.Thread(target=self._run_active_job, daemon=True)
        thread.start()

    def _register_job_step_handlers(self, runner: JobRunner, payload: dict[str, str]) -> None:
        handlers = {
            "S1.1": self._handle_prepare_job_dirs,
            "S1.2": self._make_copy_pdf_handler(payload),
            "S1.3": self._handle_parse_pdf,
            "P1.1": self._make_extract_report_handler(payload),
            "P1.2": self._make_compose_workflow_handler(payload),
            "S2.1": self._handle_create_scene_plan,
            "S2.2": self._handle_create_visual_spec,
            "S2.3": self._handle_create_tts_script,
            "S2.4": self._handle_create_component_spec,
            "S2.5": self._handle_create_asset_plan,
            "S2.6": self._handle_create_render_plan,
            "S2.7": self._handle_run_qa_fix,
            "S2.8": self._handle_final_packaging,
        }
        for step_id, handler in handlers.items():
            runner.register_step(step_id, handler)

    def _handle_prepare_job_dirs(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        logger.log("INFO", job_state.current_step_id, "[S1.1] Bắt đầu chuẩn bị cấu trúc thư mục output", job_state.job_id)
        self._simulate_step_progress(1.0)
        artifacts: list[str] = []
        for relative_dir in ("input", "parsed", "workflow", "tts", "remotion", "final", "logs"):
            path = Path(output_dir) / relative_dir
            path.mkdir(parents=True, exist_ok=True)
            artifacts.append(str(path))
        logger.log("INFO", job_state.current_step_id, f"[S1.1] Hoàn thành: đã sẵn sàng {len(artifacts)} thư mục output", job_state.job_id)
        return StepResult(artifacts=artifacts)

    def _make_copy_pdf_handler(self, payload: dict[str, str]):
        def handler(job_state: JobState, output_dir: str) -> StepResult:
            logger = self._logger(output_dir)
            source = Path(payload.get("pdf_path", ""))
            if not source.exists() or source.suffix.lower() != ".pdf":
                return StepResult(success=False, error_code="PDF_NOT_FOUND", error_message=f"Không tìm thấy PDF hợp lệ: {source}")
            target = Path(output_dir) / "input" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            logger.log("INFO", job_state.current_step_id, f"[S1.2] Bắt đầu sao chép PDF đầu vào: {source.name}", job_state.job_id)
            self._simulate_step_progress(1.0)
            shutil.copy2(source, target)
            logger.log("INFO", job_state.current_step_id, f"[S1.2] Hoàn thành: đã sao chép PDF vào {target}", job_state.job_id)
            return StepResult(artifacts=[str(target)])

        return handler

    def _handle_parse_pdf(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        pdf_path = self._find_input_pdf(output_dir)
        logger.log("INFO", job_state.current_step_id, f"[S1.3] Bắt đầu đọc PDF thật bằng PyMuPDF/pdfplumber: {pdf_path.name}", job_state.job_id)
        self._simulate_step_progress(1.5)
        parse_result = PDFParser(str(pdf_path)).parse()
        normalized_text = DataNormalizer.normalize_text(parse_result.raw_text)
        artifact = Path(output_dir) / "parsed" / "pdf-parse-result.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "file_path": str(pdf_path),
            "total_pages": parse_result.total_pages,
            "text_chunk_count": len(parse_result.text_chunks),
            "table_chunk_count": len(parse_result.table_chunks),
            "raw_text": normalized_text,
            "raw_text_preview": normalized_text[:2000],
            "text_chunks": [chunk.__dict__ for chunk in parse_result.text_chunks[:100]],
            "table_chunks": [chunk.__dict__ for chunk in parse_result.table_chunks[:50]],
        }
        self._write_json(artifact, data)
        logger.log("INFO", job_state.current_step_id, f"[S1.3] Hoàn thành: PDF parse xong {parse_result.total_pages} trang, {len(parse_result.text_chunks)} khối text, {len(parse_result.table_chunks)} bảng", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _make_extract_report_handler(self, payload: dict[str, str]):
        def handler(job_state: JobState, output_dir: str) -> StepResult:
            logger = self._logger(output_dir)
            parse_data = self._read_json(Path(output_dir) / "parsed" / "pdf-parse-result.json")
            logger.log("INFO", job_state.current_step_id, "[P1.1] Bắt đầu trích xuất report từ dữ liệu PDF đã parse", job_state.job_id)
            self._simulate_step_progress(0.5)
            if self._mock_ai_mode():
                extracted_report = self._build_extracted_report(parse_data, payload, job_state)
                logger.log("INFO", job_state.current_step_id, "[P1.1] Đang dùng mock_ai_mode=True, giữ fallback extract mock", job_state.job_id)
            else:
                raw_text = parse_data.get("raw_text") or parse_data.get("raw_text_preview", "")
                input_payload = {
                    "report_month": job_state.report_month,
                    "report_title": payload.get("report_title") or "Báo cáo giao ban",
                    "owner_org": payload.get("owner_org") or "Chưa nhập đơn vị",
                    "pdf_parse_result": {**parse_data, "raw_text": raw_text},
                }
                extracted_report = self._llm_chat(P1_1_PDF_EXTRACTION, input_payload, "P1.1", logger, job_state.job_id)
                extracted_report = ExtractedReport.model_validate(extracted_report).model_dump(mode="json")
                logger.log("INFO", job_state.current_step_id, f"[P1.1] Đã gọi LLM extract, nhận {len(extracted_report.get('metrics', []))} metrics", job_state.job_id)
            artifact = Path(output_dir) / "parsed" / "extracted-report.json"
            self._write_json(artifact, extracted_report)
            validation = WorkflowValidator().validate_extracted_report(extracted_report)
            validation_path = Path(output_dir) / "parsed" / "extracted-report.validation.json"
            self._write_json(validation_path, validation.model_dump())
            logger.log("INFO", job_state.current_step_id, f"[P1.1] Hoàn thành: extracted report có {len(extracted_report['metrics'])} metrics, validation_passed={validation.passed}", job_state.job_id)
            if not validation.passed:
                return StepResult(success=False, error_code="EXTRACTED_REPORT_INVALID", error_message=json.dumps(validation.errors, ensure_ascii=False), artifacts=[str(artifact), str(validation_path)])
            return StepResult(artifacts=[str(artifact), str(validation_path)])

        return handler

    def _make_compose_workflow_handler(self, payload: dict[str, str]):
        def handler(job_state: JobState, output_dir: str) -> StepResult:
            logger = self._logger(output_dir)
            extracted_report = self._read_json(Path(output_dir) / "parsed" / "extracted-report.json")
            template_path = payload.get("workflow_template") or "workflow.md"
            logger.log("INFO", job_state.current_step_id, "[P1.2] Bắt đầu sinh workflow từ extracted report và workflow template", job_state.job_id)
            self._simulate_step_progress(0.5)
            if self._mock_ai_mode():
                workflow = WorkflowComposer(template_path).compose_from_extracted_report(extracted_report, job_state.report_month, job_state.job_id)
                logger.log("INFO", job_state.current_step_id, "[P1.2] Đang dùng mock_ai_mode=True, giữ fallback compose mock", job_state.job_id)
            else:
                template_content = Path(template_path).read_text(encoding="utf-8")
                input_payload = {
                    "report_month": job_state.report_month,
                    "job_id": job_state.job_id,
                    "extracted_report": extracted_report,
                    "workflow_template_md": template_content,
                }
                ai_workflow = self._llm_chat(P1_2_WORKFLOW_COMPOSITION, input_payload, "P1.2", logger, job_state.job_id)
                workflow = WorkflowComposer(template_path).compose_from_ai_output(ai_workflow, job_state.report_month, job_state.job_id)
                workflow = WorkflowOutput.model_validate(workflow).model_dump(mode="json")
                logger.log("INFO", job_state.current_step_id, f"[P1.2] Đã gọi LLM compose workflow, {len(workflow.get('scenes', []))} scenes", job_state.job_id)
            validation = WorkflowValidator().validate(workflow, extracted_report)
            workflow_path = Path(output_dir) / "workflow" / "generated-workflow.json"
            named_workflow_path = Path(output_dir) / "workflow" / f"workflow-{job_state.report_month}-{job_state.job_id}.json"
            workflow_md_path = Path(output_dir) / "workflow" / f"workflow-{job_state.report_month}-{job_state.job_id}.md"
            validation_path = Path(output_dir) / "workflow" / "workflow-validation.json"
            self._write_json(workflow_path, workflow)
            self._write_json(named_workflow_path, workflow)
            workflow_md_path.write_text("```json\n" + json.dumps(workflow, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
            self._write_json(validation_path, validation.model_dump())
            logger.log("INFO", job_state.current_step_id, f"[P1.2] Hoàn thành: workflow sinh {len(workflow.get('scenes', []))} scenes, validation_passed={validation.passed}", job_state.job_id)
            if not validation.passed:
                return StepResult(success=False, error_code="WORKFLOW_VALIDATION_FAILED", error_message=json.dumps(validation.errors, ensure_ascii=False), artifacts=[str(workflow_path), str(validation_path)])
            return StepResult(artifacts=[str(workflow_path), str(named_workflow_path), str(workflow_md_path), str(validation_path)])

        return handler

    def _handle_create_scene_plan(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        workflow = self._read_json(Path(output_dir) / "workflow" / "generated-workflow.json")
        scenes = workflow.get("scenes", [])
        logger.log("INFO", job_state.current_step_id, f"[S2.1] Bắt đầu lập kế hoạch scene video từ workflow ({len(scenes)} scenes)", job_state.job_id)
        self._simulate_step_progress(0.5)
        if not self._mock_ai_mode():
            scene_plan = self._llm_video_step("S2.1", {"workflow": workflow}, logger, job_state)
        else:
            scene_plan = {
                "mode": "mock_llm",
                "step": "S2.1_scene_planning",
                "scene_count": len(scenes),
                "scenes": [
                    {
                        "scene_id": scene.get("scene_id"),
                        "scene_type": scene.get("scene_type", "content"),
                        "title": scene.get("title", ""),
                        "objective": scene.get("objective", ""),
                        "duration_policy": scene.get("duration_policy", {}),
                        "source_data_keys": scene.get("source_data_keys", []),
                        "tts": scene.get("tts", {}),
                    }
                    for scene in scenes
                ],
            }
        artifact = Path(output_dir) / "remotion" / "scene-plan.json"
        self._write_json(artifact, scene_plan)
        logger.log("INFO", job_state.current_step_id, f"[S2.1] Hoàn thành: đã tạo scene-plan.json cho {len(scene_plan.get('scenes', scenes))} scenes", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _handle_create_visual_spec(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        scene_plan = self._read_json(Path(output_dir) / "remotion" / "scene-plan.json")
        scenes = scene_plan.get("scenes", [])
        logger.log("INFO", job_state.current_step_id, "[S2.2] Bắt đầu tạo visual spec: chart types, layout, màu sắc, motion layer", job_state.job_id)
        self._simulate_step_progress(0.5)
        if not self._mock_ai_mode():
            visual_spec = self._llm_video_step("S2.2", {"scene_plan": scene_plan, "workflow": self._read_json(Path(output_dir) / "workflow" / "generated-workflow.json")}, logger, job_state)
        else:
            chart_types = ["kpi_card", "bar_chart", "line_chart", "table_summary"]
            visual_spec = {
                "mode": "mock_llm",
                "step": "S2.2_visual_spec",
                "design_system": {"theme": "data-dense-dashboard", "primary": "#1E40AF", "accent": "#F59E0B"},
                "scene_visuals": [
                    {
                        "scene_id": scene.get("scene_id"),
                        "layout": "hero_title" if scene.get("scene_type") == "intro" else "metric_dashboard",
                        "chart_type": chart_types[index % len(chart_types)],
                        "motion": {"enter": "fade-up", "emphasis": "number-count", "exit": "fade"},
                    }
                    for index, scene in enumerate(scenes)
                ],
            }
        artifact = Path(output_dir) / "remotion" / "visual-spec.json"
        self._write_json(artifact, visual_spec)
        logger.log("INFO", job_state.current_step_id, f"[S2.2] Hoàn thành: visual spec có {len(visual_spec.get('scene_visuals', []))} scene visuals", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _handle_create_tts_script(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        scene_plan = self._read_json(Path(output_dir) / "remotion" / "scene-plan.json")
        scenes = scene_plan.get("scenes", [])
        logger.log("INFO", job_state.current_step_id, "[S2.3] Bắt đầu tạo kịch bản TTS và audio theo từng scene", job_state.job_id)
        self._simulate_step_progress(0.5)
        if not self._mock_ai_mode():
            tts_data = self._llm_video_step("S2.3", {"scene_plan": scene_plan, "visual_spec": self._read_json(Path(output_dir) / "remotion" / "visual-spec.json")}, logger, job_state)
            scripts = tts_data.get("scripts") or tts_data.get("scenes") or tts_data.get("tts_scripts") or []
            if scripts:
                scripts = [self._normalize_tts_script(item) for item in scripts]
            else:
                scripts = [self._normalize_tts_script(scene) for scene in scenes]
        else:
            scripts = [self._normalize_tts_script(scene) for scene in scenes]
        tts_scenes = [{"scene_id": item["scene_id"], "tts": {"enabled": item["enabled"], "text": item["text"], "voice": item["voice"]}} for item in scripts]
        tts_manifest = self._tts_generator(output_dir).generate_all(tts_scenes)
        artifact_data = {"mode": "mock_tts" if self._mock_ai_mode() else "real_tts", "step": "S2.3_narration_tts", "scripts": scripts, "tts_manifest": tts_manifest}
        artifact = Path(output_dir) / "tts" / "tts-script.json"
        self._write_json(artifact, artifact_data)
        logger.log("INFO", job_state.current_step_id, f"[S2.3] Hoàn thành: tạo TTS script cho {len(scripts)} scenes và audio manifest", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _handle_create_component_spec(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        scene_plan = self._read_json(Path(output_dir) / "remotion" / "scene-plan.json")
        visual_spec = self._read_json(Path(output_dir) / "remotion" / "visual-spec.json")
        logger.log("INFO", job_state.current_step_id, "[S2.4] Bắt đầu tạo Remotion component spec deterministic", job_state.job_id)
        self._simulate_step_progress(0.5)
        if not self._mock_ai_mode():
            component_spec = self._llm_video_step("S2.4", {"scene_plan": scene_plan, "visual_spec": visual_spec}, logger, job_state)
            if "components" not in component_spec:
                component_spec = {"mode": "real_llm", "step": "S2.4_component_spec", "components": component_spec.get("scenes", [])}
        else:
            visual_by_scene = {item.get("scene_id"): item for item in visual_spec.get("scene_visuals", [])}
            components = []
            for scene in scene_plan.get("scenes", []):
                scene_id = scene.get("scene_id")
                scene_type = scene.get("scene_type", "content")
                component_type = "TitleScene" if scene_type == "intro" else "ClosingScene" if scene_type == "closing" else "MetricScene"
                components.append({"scene_id": scene_id, "type": component_type, "props": {"title": scene.get("title", ""), "visual": visual_by_scene.get(scene_id, {})}})
            component_spec = {"mode": "mock_llm", "step": "S2.4_component_spec", "components": components}
        artifact = Path(output_dir) / "remotion" / "component-spec.json"
        self._write_json(artifact, component_spec)
        logger.log("INFO", job_state.current_step_id, f"[S2.4] Hoàn thành: component spec có {len(component_spec.get('components', []))} components", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _handle_create_asset_plan(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        component_spec = self._read_json(Path(output_dir) / "remotion" / "component-spec.json")
        logger.log("INFO", job_state.current_step_id, "[S2.5] Bắt đầu lập asset plan: fonts, icons, background, chart cache", job_state.job_id)
        self._simulate_step_progress(0.5)
        if not self._mock_ai_mode():
            asset_plan = self._llm_video_step("S2.5", {"component_spec": component_spec, "visual_spec": self._read_json(Path(output_dir) / "remotion" / "visual-spec.json")}, logger, job_state)
        else:
            assets = [
                {"asset_id": "font_primary", "type": "font", "name": "Segoe UI/Cascadia fallback", "required": True},
                {"asset_id": "bg_data_grid", "type": "background", "name": "data-grid-light", "required": True},
                {"asset_id": "icon_status", "type": "icon", "name": "status-pills", "required": False},
            ]
            for component in component_spec.get("components", []):
                assets.append({"asset_id": f"chart_cache_{component.get('scene_id')}", "type": "chart_cache", "scene_id": component.get("scene_id"), "required": True})
            asset_plan = {"mode": "mock_llm", "step": "S2.5_asset_plan", "assets": assets}
        artifact = Path(output_dir) / "remotion" / "asset-plan.json"
        self._write_json(artifact, asset_plan)
        logger.log("INFO", job_state.current_step_id, f"[S2.5] Hoàn thành: asset plan có {len(asset_plan.get('assets', []))} assets", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _handle_create_render_plan(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        scene_plan = self._read_json(Path(output_dir) / "remotion" / "scene-plan.json")
        tts_script = self._read_json(Path(output_dir) / "tts" / "tts-script.json")
        tts_manifest = tts_script.get("tts_manifest", {})
        logger.log("INFO", job_state.current_step_id, "[S2.6] Bắt đầu tạo render plan: timeline sync TTS-first và frame ranges", job_state.job_id)
        self._simulate_step_progress(0.5)
        if not self._mock_ai_mode():
            render_plan = self._llm_video_step("S2.6", {"scene_plan": scene_plan, "tts_manifest": tts_manifest, "component_spec": self._read_json(Path(output_dir) / "remotion" / "component-spec.json")}, logger, job_state)
            render_plan = self._ensure_render_plan(render_plan, scene_plan, tts_manifest)
        else:
            render_plan = self._ensure_render_plan({"mode": "mock_llm", "step": "S2.6_render_plan"}, scene_plan, tts_manifest)
        artifact = Path(output_dir) / "remotion" / "render-plan.json"
        self._write_json(artifact, render_plan)
        logger.log("INFO", job_state.current_step_id, f"[S2.6] Hoàn thành: render plan {len(render_plan.get('timeline', []))} scenes, {render_plan.get('estimated_duration_seconds', 0)} giây", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _handle_run_qa_fix(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        workflow = self._read_json(Path(output_dir) / "workflow" / "generated-workflow.json")
        component_spec = self._read_json(Path(output_dir) / "remotion" / "component-spec.json")
        render_plan = self._read_json(Path(output_dir) / "remotion" / "render-plan.json")
        tts_script = self._read_json(Path(output_dir) / "tts" / "tts-script.json")
        logger.log("INFO", job_state.current_step_id, "[S2.7] Bắt đầu QA preview: kiểm tra sync, overflow, thiếu audio/component", job_state.job_id)
        self._simulate_step_progress(0.5)
        manifest = RemotionManifest(output_dir).build_manifest(workflow, component_spec, render_plan, tts_script.get("tts_manifest", {}))
        preview_ok, preview_errors = RenderGate(output_dir).check_preview_ready(manifest)
        final_ok, final_errors = RenderGate(output_dir).check_final_ready(manifest, tts_script.get("tts_manifest", {}))
        issues = preview_errors + [error for error in final_errors if error not in preview_errors]
        if not self._mock_ai_mode():
            ai_qa = self._llm_video_step("S2.7", {"manifest": manifest, "issues": issues}, logger, job_state)
            qa_report = {**ai_qa, "preview_ready": preview_ok, "final_ready": final_ok, "issues": ai_qa.get("issues", issues)}
        else:
            qa_report = {"mode": "mock_qa", "step": "S2.7_qa_fix", "preview_ready": preview_ok, "final_ready": final_ok, "issues": issues, "fixes_applied": [], "summary": "no issues found" if not issues else "issues detected"}
        artifact = Path(output_dir) / "remotion" / "qa-fix.json"
        self._write_json(artifact, qa_report)
        logger.log("INFO", job_state.current_step_id, f"[S2.7] Hoàn thành: QA preview_ready={preview_ok}, final_ready={final_ok}, issues={len(qa_report.get('issues', []))}", job_state.job_id)
        if qa_report.get("issues"):
            return StepResult(success=False, error_code="QA_CHECK_FAILED", error_message=json.dumps(qa_report.get("issues", []), ensure_ascii=False), artifacts=[str(artifact)])
        return StepResult(artifacts=[str(artifact)])

    def _handle_final_packaging(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        workflow = self._read_json(Path(output_dir) / "workflow" / "generated-workflow.json")
        component_spec = self._read_json(Path(output_dir) / "remotion" / "component-spec.json")
        render_plan = self._read_json(Path(output_dir) / "remotion" / "render-plan.json")
        tts_script = self._read_json(Path(output_dir) / "tts" / "tts-script.json")
        logger.log("INFO", job_state.current_step_id, "[S2.8] Bắt đầu đóng gói final: tạo Remotion manifest, video.mp4 và publish manifest", job_state.job_id)
        self._simulate_step_progress(0.5)
        remotion_manifest = RemotionManifest(output_dir).build_manifest(workflow, component_spec, render_plan, tts_script.get("tts_manifest", {}))
        remotion_manifest_path = RemotionManifest(output_dir).save_manifest(remotion_manifest)
        packager = FinalPackager(output_dir)
        if not self._mock_ai_mode():
            self._llm_video_step("S2.8", {"remotion_manifest": remotion_manifest, "render_plan": render_plan}, logger, job_state)
        video_path = packager.create_mock_video()
        packager.create_publish_manifest(job_state.job_id, job_state.report_month, video_path, remotion_manifest)
        publish_path = Path(output_dir) / "final" / "publish-manifest.json"
        video_full_path = Path(output_dir) / video_path
        logger.log("INFO", job_state.current_step_id, f"[S2.8] Hoàn thành: đã tạo {video_full_path} và {publish_path}", job_state.job_id)
        return StepResult(artifacts=[str(video_full_path), str(publish_path), str(remotion_manifest_path)])

    def _logger(self, output_dir: str) -> EventLogger:
        return EventLogger(output_dir)

    def _find_input_pdf(self, output_dir: str) -> Path:
        input_dir = Path(output_dir) / "input"
        pdf_files = sorted(input_dir.glob("*.pdf"))
        if not pdf_files:
            raise FileNotFoundError(f"Không tìm thấy PDF trong {input_dir}")
        return pdf_files[0]

    def _build_extracted_report(self, parse_data: dict[str, Any], payload: dict[str, str], job_state: JobState) -> dict[str, Any]:
        raw_text = parse_data.get("raw_text") or parse_data.get("raw_text_preview", "")
        preview = (parse_data.get("raw_text_preview") or raw_text[:2000])[:2000]
        total_pages = int(parse_data.get("total_pages") or 0)
        text_chunk_count = int(parse_data.get("text_chunk_count") or len(parse_data.get("text_chunks", [])))
        table_chunk_count = int(parse_data.get("table_chunk_count") or len(parse_data.get("table_chunks", [])))
        number_count = len(re.findall(r"\d[\d.,]*", raw_text))
        metrics = [
            {
                "metric_key": "pdf_total_pages",
                "metric_name": "Số trang PDF đã parse",
                "value": str(total_pages),
                "unit": "trang",
                "citations": [{"page_no": 1, "source_snippet": preview[:240], "confidence": 0.95}],
            },
            {
                "metric_key": "pdf_text_blocks",
                "metric_name": "Số khối text trích xuất được",
                "value": str(text_chunk_count),
                "unit": "khối",
                "citations": [{"page_no": 1, "source_snippet": preview[:240], "confidence": 0.9}],
            },
            {
                "metric_key": "pdf_table_blocks",
                "metric_name": "Số bảng trích xuất được",
                "value": str(table_chunk_count),
                "unit": "bảng",
                "citations": [{"page_no": 1, "source_snippet": preview[:240], "confidence": 0.9}],
            },
            {
                "metric_key": "pdf_numeric_tokens",
                "metric_name": "Số token dạng số phát hiện trong nội dung PDF",
                "value": str(number_count),
                "unit": "token",
                "citations": [{"page_no": 1, "source_snippet": preview[:240], "confidence": 0.75}],
            },
        ]
        return {
            "report_metadata": {
                "title": payload.get("report_title") or "Báo cáo giao ban",
                "period": job_state.report_month,
                "organization": payload.get("owner_org") or "Chưa nhập đơn vị",
            },
            "metrics": metrics,
            "sections": [
                {
                    "section_key": "pdf_summary",
                    "summary": preview[:500] or "PDF không có text preview",
                    "citations": [{"page_no": 1, "source_snippet": preview[:240], "confidence": 0.4}],
                }
            ],
            "warnings": ["basic_extraction_from_pdf_parse_result", "mock_ai_mode_enabled"],
        }

    def _llm_chat(self, system_prompt: str, input_payload: dict[str, Any], step_id: str, logger: EventLogger, job_id: str) -> dict[str, Any]:
        try:
            result = self._llm_client().chat_with_retry_parse(system_prompt, json.dumps(input_payload, ensure_ascii=False))
            if not isinstance(result, dict):
                raise ValueError("LLM output phải là JSON object")
            return result
        except Exception as exc:
            safe_message = mask_sensitive_text(str(exc))
            logger.log("ERROR", step_id, f"[{step_id}] LLM call/parse failed: {safe_message}", job_id)
            raise

    def _llm_video_step(self, step_id: str, input_payload: dict[str, Any], logger: EventLogger, job_state: JobState) -> dict[str, Any]:
        result = self._llm_chat(VIDEO_PROMPTS[step_id], input_payload, step_id, logger, job_state.job_id)
        if not isinstance(result, dict):
            raise ValueError(f"{step_id} output phải là dict")
        logger.log("INFO", step_id, f"[{step_id}] Đã gọi LLM thật và nhận JSON keys={list(result.keys())[:8]}", job_state.job_id)
        return result

    def _llm_client(self) -> LLMClient:
        llm_config = self.runtime_config.get("llm", {})
        url = str(llm_config.get("url_model") or "")
        api_key = str(llm_config.get("api_key") or "")
        model = str(llm_config.get("default_model") or "")
        if not url or not api_key or not model:
            raise ValueError("Thiếu cấu hình LLM URL/model/API key; bật mock_ai_mode=True nếu muốn chạy mock")
        timeout = float(self.runtime_config.get("runtime_policy", {}).get("step_timeout_seconds") or 600)
        return LLMClient(url, api_key, model, timeout=timeout)

    def _tts_generator(self, output_dir: str) -> TTSGenerator:
        tts_config = self.runtime_config.get("tts", {})
        return TTSGenerator(
            output_dir,
            tts_url=str(tts_config.get("url_tts") or ""),
            tts_api_key=str(tts_config.get("api_key") or ""),
            tts_model=str(tts_config.get("model_tts") or ""),
            mock_mode=self._mock_ai_mode(),
            timeout=float(self.runtime_config.get("runtime_policy", {}).get("step_timeout_seconds") or 600),
        )

    def _mock_ai_mode(self) -> bool:
        return bool(self.runtime_config.get("runtime_policy", {}).get("mock_ai_mode", True))

    def _normalize_tts_script(self, item: dict[str, Any]) -> dict[str, Any]:
        tts = item.get("tts", item)
        return {
            "scene_id": item.get("scene_id", tts.get("scene_id", "")),
            "enabled": bool(tts.get("enabled", True)),
            "text": str(tts.get("text") or item.get("text") or ""),
            "voice": str(tts.get("voice") or item.get("voice") or self.runtime_config.get("tts", {}).get("voice") or "vi_female"),
        }

    def _ensure_render_plan(self, render_plan: dict[str, Any], scene_plan: dict[str, Any], tts_manifest: dict[str, Any]) -> dict[str, Any]:
        if render_plan.get("timeline"):
            return render_plan
        fps = int(render_plan.get("fps") or 30)
        start_frame = 0
        timeline = []
        for scene in scene_plan.get("scenes", []):
            scene_id = scene.get("scene_id")
            duration_seconds = max(3.0, float(tts_manifest.get(scene_id, {}).get("duration_seconds") or 0), float(scene.get("duration_policy", {}).get("min_seconds") or 0))
            duration_frames = int(duration_seconds * fps)
            timeline.append({"scene_id": scene_id, "start_frame": start_frame, "duration_frames": duration_frames, "duration_seconds": round(duration_seconds, 1)})
            start_frame += duration_frames
        render_plan.update({"fps": fps, "timeline": timeline, "total_frames": start_frame, "estimated_duration_seconds": round(start_frame / fps, 1)})
        return render_plan

    def _default_runtime_config(self) -> dict[str, Any]:
        return {
            "llm": {"url_model": "", "default_model": "", "api_key": "", "credential_id_model": ""},
            "tts": {"url_tts": "", "model_tts": "", "voice": "", "api_key": "", "credential_id_tts": ""},
            "runtime_policy": {"step_timeout_seconds": 600, "max_retry": 3, "retry_backoff_seconds": 30, "enable_resume": True, "mock_ai_mode": True},
        }

    def _simulate_step_progress(self, seconds: float) -> None:
        time.sleep(seconds)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _run_active_job(self) -> None:
        if self.active_runner is None:
            return
        result = self.active_runner.run()
        self.after(0, lambda: self._handle_job_finished(result))

    def _handle_job_finished(self, job_state: JobState) -> None:
        self.current_job_state = job_state
        self.create_video_screen.mark_job_finished(job_state)
        self.job_logs_screen.set_job_state(job_state, self._current_output_dir())
        self.history_screen.upsert_job(job_state, {}, self._current_output_dir())
        self.topbar.set_status(STATUS_TEXT.get(job_state.status, "Sẵn sàng"))
        if job_state.status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELED}:
            self.active_runner = None

    def _cancel_current_job(self) -> None:
        if self.active_runner is not None:
            self.active_runner.cancel()
        if self.current_job_state is not None:
            self.current_job_state.status = JobStatus.CANCELED
            self.current_job_state.updated_at = datetime.now(timezone.utc).isoformat()
            self.create_video_screen.mark_job_finished(self.current_job_state)
            self.job_logs_screen.set_job_state(self.current_job_state, self._current_output_dir())
            self.history_screen.upsert_job(self.current_job_state, {}, self._current_output_dir())
            self.topbar.set_status("Đã hủy")
            self.active_runner = None

    def _delete_job_from_history(self, job_id: str, status: str) -> None:
        if self.current_job_state is not None and self.current_job_state.job_id == job_id and status == "RUNNING":
            self._cancel_current_job()
        if self.current_job_state is not None and self.current_job_state.job_id == job_id:
            self.current_job_state.status = JobStatus.CANCELED
            self.job_logs_screen.set_job_state(self.current_job_state, self._current_output_dir())

    def _current_output_dir(self) -> str:
        if self.current_job_state is None:
            return "outputs"
        return str(Path("outputs") / self.current_job_state.report_month / self.current_job_state.job_id)

    def open_outputs(self) -> None:
        """Mở thư mục outputs nếu đã tồn tại; tạo mới khi chưa có."""
        outputs_path = os.path.abspath("outputs")
        os.makedirs(outputs_path, exist_ok=True)
        os.startfile(outputs_path)


def main() -> None:
    """Khởi tạo cửa sổ desktop app shell."""
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
