"""Entrypoint cho ứng dụng Báo Cáo Giao Ban - Video Generator."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk

from app.core import EventLogger, JobRunner, JobState, JobStatus, RetryPolicy, StepRecord, StepResult
from app.pdf.normalizer import DataNormalizer
from app.pdf.parser import PDFParser
from app.ui import tokens
from app.ui.navigation import NavigationController
from app.ui.screens import ConfigScreen, CreateVideoScreen, HistoryScreen, JobLogsScreen
from app.ui.sidebar import SidebarFrame
from app.ui.topbar import TopBarFrame
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
    ("S2.2", "Sinh kịch bản lời đọc"),
    ("S2.3", "Đóng gói kết quả mock"),
)


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
        self.create_video_screen.set_config_ready(llm_ready=True, tts_ready=True)
        self.sidebar.set_config_status("Sẵn sàng")

    def _handle_screen_changed(self, screen_name: str) -> None:
        self.sidebar.set_active(screen_name)
        self.topbar.set_title(SCREEN_TITLES.get(screen_name, screen_name))

    def _start_job_from_create(self, payload: dict[str, str]) -> None:
        if self.active_runner is not None and self.current_job_state is not None and self.current_job_state.status == JobStatus.RUNNING:
            self.create_video_screen.set_current_job(self.current_job_state, self.current_job_started_at)
            return
        now = datetime.now(timezone.utc)
        job_id = now.strftime("%Y%m%d-%H%M%S")
        report_month = payload.get("report_month", now.strftime("%Y%m"))
        output_dir = Path(payload.get("output_root") or "outputs") / report_month / job_id
        steps = [StepRecord(step_id=step_id, name=name) for step_id, name in DEFAULT_STEPS]
        job_state = JobState(job_id=job_id, status=JobStatus.QUEUED, report_month=report_month, current_step_id=steps[0].step_id, steps=steps, created_at=now.isoformat(), updated_at=now.isoformat())
        self.current_job_state = job_state
        self.current_job_started_at = now
        self.active_runner = JobRunner(job_state, str(output_dir), retry_policy=RetryPolicy(max_retry=1, backoff_seconds=0, step_timeout=30))
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
            "S2.1": self._handle_mock_scene_plan,
            "S2.2": self._handle_mock_tts_script,
            "S2.3": self._handle_mock_final_packaging,
        }
        for step_id, handler in handlers.items():
            runner.register_step(step_id, handler)

    def _handle_prepare_job_dirs(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        logger.log("INFO", job_state.current_step_id, "Tạo cấu trúc thư mục output cho job", job_state.job_id)
        artifacts: list[str] = []
        for relative_dir in ("input", "parsed", "workflow", "tts", "remotion", "final", "logs"):
            path = Path(output_dir) / relative_dir
            path.mkdir(parents=True, exist_ok=True)
            artifacts.append(str(path))
        logger.log("INFO", job_state.current_step_id, f"Đã sẵn sàng {len(artifacts)} thư mục output", job_state.job_id)
        return StepResult(artifacts=artifacts)

    def _make_copy_pdf_handler(self, payload: dict[str, str]):
        def handler(job_state: JobState, output_dir: str) -> StepResult:
            logger = self._logger(output_dir)
            source = Path(payload.get("pdf_path", ""))
            if not source.exists() or source.suffix.lower() != ".pdf":
                return StepResult(success=False, error_code="PDF_NOT_FOUND", error_message=f"Không tìm thấy PDF hợp lệ: {source}")
            target = Path(output_dir) / "input" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            logger.log("INFO", job_state.current_step_id, f"Sao chép PDF đầu vào: {source.name}", job_state.job_id)
            shutil.copy2(source, target)
            logger.log("INFO", job_state.current_step_id, f"Đã sao chép PDF vào {target}", job_state.job_id)
            return StepResult(artifacts=[str(target)])

        return handler

    def _handle_parse_pdf(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        pdf_path = self._find_input_pdf(output_dir)
        logger.log("INFO", job_state.current_step_id, f"Bắt đầu đọc PDF thật bằng PyMuPDF/pdfplumber: {pdf_path.name}", job_state.job_id)
        parse_result = PDFParser(str(pdf_path)).parse()
        normalized_text = DataNormalizer.normalize_text(parse_result.raw_text)
        artifact = Path(output_dir) / "parsed" / "pdf-parse-result.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "file_path": str(pdf_path),
            "total_pages": parse_result.total_pages,
            "text_chunk_count": len(parse_result.text_chunks),
            "table_chunk_count": len(parse_result.table_chunks),
            "raw_text_preview": normalized_text[:2000],
            "text_chunks": [chunk.__dict__ for chunk in parse_result.text_chunks[:100]],
            "table_chunks": [chunk.__dict__ for chunk in parse_result.table_chunks[:50]],
        }
        self._write_json(artifact, data)
        logger.log("INFO", job_state.current_step_id, f"PDF parse xong: {parse_result.total_pages} trang, {len(parse_result.text_chunks)} khối text, {len(parse_result.table_chunks)} bảng", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _make_extract_report_handler(self, payload: dict[str, str]):
        def handler(job_state: JobState, output_dir: str) -> StepResult:
            logger = self._logger(output_dir)
            parse_data = self._read_json(Path(output_dir) / "parsed" / "pdf-parse-result.json")
            logger.log("INFO", job_state.current_step_id, "Trích xuất số liệu mock từ nội dung PDF đã parse", job_state.job_id)
            extracted_report = self._build_extracted_report(parse_data, payload, job_state)
            artifact = Path(output_dir) / "parsed" / "extracted-report.json"
            self._write_json(artifact, extracted_report)
            validation = WorkflowValidator().validate_extracted_report(extracted_report)
            logger.log("INFO", job_state.current_step_id, f"Extracted report có {len(extracted_report['metrics'])} metrics, validation_passed={validation.passed}", job_state.job_id)
            if not validation.passed:
                return StepResult(success=False, error_code="EXTRACTED_REPORT_INVALID", error_message=json.dumps(validation.errors, ensure_ascii=False))
            return StepResult(artifacts=[str(artifact)])

        return handler

    def _make_compose_workflow_handler(self, payload: dict[str, str]):
        def handler(job_state: JobState, output_dir: str) -> StepResult:
            logger = self._logger(output_dir)
            extracted_report = self._read_json(Path(output_dir) / "parsed" / "extracted-report.json")
            logger.log("INFO", job_state.current_step_id, "Sinh workflow từ extracted report và validate schema nghiệp vụ", job_state.job_id)
            workflow = WorkflowComposer(payload.get("workflow_template") or "workflow.md").compose_from_extracted_report(extracted_report, job_state.report_month, job_state.job_id)
            validation = WorkflowValidator().validate(workflow, extracted_report)
            workflow_path = Path(output_dir) / "workflow" / "generated-workflow.json"
            validation_path = Path(output_dir) / "workflow" / "workflow-validation.json"
            self._write_json(workflow_path, workflow)
            self._write_json(validation_path, validation.model_dump())
            logger.log("INFO", job_state.current_step_id, f"Workflow sinh {len(workflow.get('scenes', []))} scenes, validation_passed={validation.passed}", job_state.job_id)
            if not validation.passed:
                return StepResult(success=False, error_code="WORKFLOW_VALIDATION_FAILED", error_message=json.dumps(validation.errors, ensure_ascii=False))
            return StepResult(artifacts=[str(workflow_path), str(validation_path)])

        return handler

    def _handle_mock_scene_plan(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        workflow = self._read_json(Path(output_dir) / "workflow" / "generated-workflow.json")
        scenes = workflow.get("scenes", [])
        logger.log("INFO", job_state.current_step_id, f"Tạo scene plan mock cho {len(scenes)} scenes", job_state.job_id)
        artifact = Path(output_dir) / "remotion" / "scene-plan.json"
        self._write_json(artifact, {"mode": "mock_llm", "scene_count": len(scenes), "scenes": scenes})
        return StepResult(artifacts=[str(artifact)])

    def _handle_mock_tts_script(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        scene_plan = self._read_json(Path(output_dir) / "remotion" / "scene-plan.json")
        scripts = [{"scene_id": scene.get("scene_id"), "text": scene.get("tts", {}).get("text", "")} for scene in scene_plan.get("scenes", [])]
        logger.log("INFO", job_state.current_step_id, f"Tạo TTS script mock cho {len(scripts)} scenes", job_state.job_id)
        artifact = Path(output_dir) / "tts" / "tts-script.json"
        self._write_json(artifact, {"mode": "mock_tts", "scripts": scripts})
        return StepResult(artifacts=[str(artifact)])

    def _handle_mock_final_packaging(self, job_state: JobState, output_dir: str) -> StepResult:
        logger = self._logger(output_dir)
        logger.log("INFO", job_state.current_step_id, "Đóng gói manifest video mock, chưa gọi render thật", job_state.job_id)
        artifact = Path(output_dir) / "final" / "publish-manifest.json"
        manifest = {
            "job_id": job_state.job_id,
            "report_month": job_state.report_month,
            "mode": "mock_video_pipeline",
            "final_video": None,
            "artifacts": ["workflow/generated-workflow.json", "remotion/scene-plan.json", "tts/tts-script.json"],
        }
        self._write_json(artifact, manifest)
        logger.log("INFO", job_state.current_step_id, f"Hoàn tất pipeline mock, manifest: {artifact}", job_state.job_id)
        return StepResult(artifacts=[str(artifact)])

    def _logger(self, output_dir: str) -> EventLogger:
        return EventLogger(output_dir)

    def _find_input_pdf(self, output_dir: str) -> Path:
        input_dir = Path(output_dir) / "input"
        pdf_files = sorted(input_dir.glob("*.pdf"))
        if not pdf_files:
            raise FileNotFoundError(f"Không tìm thấy PDF trong {input_dir}")
        return pdf_files[0]

    def _build_extracted_report(self, parse_data: dict[str, Any], payload: dict[str, str], job_state: JobState) -> dict[str, Any]:
        raw_text = parse_data.get("raw_text_preview", "")
        numbers = re.findall(r"\d[\d.,]*", raw_text)
        metrics = []
        for index, number in enumerate(numbers[:5], 1):
            metrics.append(
                {
                    "metric_key": f"metric_{index:02d}",
                    "metric_name": f"Số liệu phát hiện {index}",
                    "value": number,
                    "unit": "",
                    "citations": [{"page_no": 1, "source_snippet": raw_text[:240], "confidence": 0.5}],
                }
            )
        if not metrics:
            metrics.append(
                {
                    "metric_key": "summary_01",
                    "metric_name": "Tóm tắt nội dung PDF",
                    "value": "Đã đọc nội dung PDF",
                    "unit": "",
                    "citations": [{"page_no": 1, "source_snippet": raw_text[:240], "confidence": 0.4}],
                }
            )
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
                    "summary": raw_text[:500] or "PDF không có text preview",
                    "citations": [{"page_no": 1, "source_snippet": raw_text[:240], "confidence": 0.4}],
                }
            ],
            "warnings": ["mock_extraction_from_pdf_text"],
        }

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
