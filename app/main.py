"""Entrypoint cho ứng dụng Báo Cáo Giao Ban - Video Generator."""

from __future__ import annotations

import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk

from app.core import JobRunner, JobState, JobStatus, RetryPolicy, StepRecord, StepResult
from app.ui import tokens
from app.ui.navigation import NavigationController
from app.ui.screens import ConfigScreen, CreateVideoScreen, HistoryScreen, JobLogsScreen
from app.ui.sidebar import SidebarFrame
from app.ui.topbar import TopBarFrame

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
        self.active_runner = JobRunner(job_state, str(output_dir), retry_policy=RetryPolicy(max_retry=1, backoff_seconds=0, step_timeout=10))
        for step_id, _name in DEFAULT_STEPS:
            self.active_runner.register_step(step_id, self._make_ui_step_handler(payload))
        self.create_video_screen.set_current_job(job_state, now)
        self.job_logs_screen.set_job_state(job_state, str(output_dir))
        self.history_screen.upsert_job(job_state, payload, str(output_dir))
        self.topbar.set_status("Đang chạy")
        thread = threading.Thread(target=self._run_active_job, daemon=True)
        thread.start()

    def _make_ui_step_handler(self, payload: dict[str, str]):
        def handler(job_state: JobState, output_dir: str) -> StepResult:
            current_step = job_state.current_step_id or "JOB"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            if current_step == "S1.2" and payload.get("pdf_path"):
                return StepResult(success=True, artifacts=[payload["pdf_path"]])
            return StepResult(success=True, artifacts=[])

        return handler

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
