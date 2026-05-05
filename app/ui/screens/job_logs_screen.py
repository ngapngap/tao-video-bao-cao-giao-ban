"""Màn hình Job & Logs với timeline, log viewer, artifacts và job_state thực."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core import CheckpointManager, JobState, JobStatus, StepStatus, mask_sensitive_text
from app.core.models import EventLogEntry
from app.ui import tokens

STATUS_STYLES = {
    "DONE": ("✓", tokens.COLOR_SUCCESS),
    "RUNNING": ("●", tokens.COLOR_STATUS_RUNNING),
    "PENDING": ("○", tokens.COLOR_NEUTRAL),
    "FAILED": ("✗", tokens.COLOR_ERROR),
    "WAITING_RETRY": ("!", tokens.COLOR_WARNING),
    "CANCELED": ("○", tokens.COLOR_NEUTRAL),
}
STATUS_TEXT = {
    "DRAFT": "Nháp",
    "QUEUED": "Đang chờ",
    "RUNNING": "Đang chạy",
    "WAITING_RETRY": "Chờ thử lại",
    "PARTIAL_DONE": "Hoàn thành một phần",
    "DONE": "Hoàn thành",
    "FAILED": "Thất bại",
    "CANCELED": "Đã hủy",
    "PENDING": "Chờ chạy",
}
PHASES = {
    "S1": "Đầu vào & đọc PDF",
    "P1": "AI pass 1 & workflow",
    "S2": "AI pass 2 & đóng gói",
}


class ChangeDetector:
    """Detect file changes bằng last-modified time + content hash."""

    def __init__(self) -> None:
        self._file_mtimes: dict[str, float] = {}
        self._file_hashes: dict[str, str] = {}

    def has_changed(self, file_path: str) -> bool:
        """Check nếu file đã thay đổi kể từ lần check cuối."""
        if not os.path.exists(file_path):
            return False

        mtime = os.path.getmtime(file_path)
        if file_path in self._file_mtimes and self._file_mtimes[file_path] == mtime:
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            content_hash = hashlib.md5(content.encode()).hexdigest()

            if file_path in self._file_hashes and self._file_hashes[file_path] == content_hash:
                self._file_mtimes[file_path] = mtime
                return False

            self._file_mtimes[file_path] = mtime
            self._file_hashes[file_path] = content_hash
            return True
        except Exception:
            return False

    def get_new_lines(self, file_path: str, from_line: int = 0) -> tuple[list[str], int]:
        """Đọc các dòng mới từ file NDJSON kể từ from_line. Trả (new_lines, total_lines)."""
        if not os.path.exists(file_path):
            return [], 0
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            total = len(all_lines)
            if total > from_line:
                return all_lines[from_line:], total
            return [], total
        except Exception:
            return [], 0


@dataclass(frozen=True)
class Artifact:
    """Data object cho artifact của job."""

    filename: str
    type: str
    size: str
    path: str


class JobLogsScreen(ctk.CTkFrame):
    """Màn hình theo dõi job, log realtime và artifact."""

    def __init__(self, master: ctk.CTkBaseClass, on_open_output: Callable[[], None] | None = None, on_cancel_job: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color=tokens.COLOR_BACKGROUND, corner_radius=0)
        self.on_open_output = on_open_output
        self.on_cancel_job = on_cancel_job
        self.job_state: JobState | None = None
        self.output_dir = "outputs"
        self.log_filter_var = ctk.StringVar(value="Tất cả")
        self.search_var = ctk.StringVar(value="")
        self.auto_scroll_var = ctk.BooleanVar(value=True)
        self._change_detector = ChangeDetector()
        self._last_log_line_count = 0
        self._artifacts_folder_mtime: float | None = None
        self._cached_step_statuses: dict[str, str] = {}
        self._timeline_rows_by_step_id: dict[str, int] = {}
        self._timeline_frames_by_step_id: dict[str, ctk.CTkFrame] = {}
        self._cached_artifact_paths: tuple[str, ...] = ()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_content()
        self.set_job_state(None, "outputs")

    def _build_header(self) -> None:
        header = self._create_card(self)
        header.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_XL, tokens.SPACING_MD))
        header.grid_columnconfigure(0, weight=1)
        meta_frame = ctk.CTkFrame(header, fg_color="transparent")
        meta_frame.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=tokens.SPACING_LG)
        meta_frame.grid_columnconfigure(0, weight=1)
        self.job_header_label = ctk.CTkLabel(meta_frame, text="Chưa có job đang hiển thị", font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT, anchor="w")
        self.job_header_label.grid(row=0, column=0, sticky="ew")
        buttons = ctk.CTkFrame(meta_frame, fg_color="transparent")
        buttons.grid(row=0, column=1, sticky="e")
        self.resume_button = self._secondary_button(buttons, text="Tiếp tục", command=self._mock_action, width=104)
        self.resume_button.grid(row=0, column=0, sticky="e")
        self.retry_button = self._secondary_button(buttons, text="Thử lại bước lỗi", command=self._mock_action, width=124)
        self.retry_button.grid(row=0, column=1, sticky="e", padx=(tokens.SPACING_SM, 0))
        self.cancel_button = self._secondary_button(buttons, text="Hủy", command=self.cancel_job, width=84)
        self.cancel_button.grid(row=0, column=2, sticky="e", padx=(tokens.SPACING_SM, 0))
        self.open_output_button = self._secondary_button(buttons, text="Mở output", command=self._open_output, width=104)
        self.open_output_button.grid(row=0, column=3, sticky="e", padx=(tokens.SPACING_SM, 0))

    def _build_content(self) -> None:
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_XL))
        content.grid_columnconfigure(0, weight=3, uniform="job_logs_columns")
        content.grid_columnconfigure(1, weight=7, uniform="job_logs_columns")
        content.grid_rowconfigure(0, weight=1)
        self._build_timeline(content)
        self._build_right_tabs(content)

    def _build_timeline(self, master: ctk.CTkFrame) -> None:
        card = self._create_card(master)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, tokens.SPACING_MD))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        title = ctk.CTkLabel(card, text="Timeline bước", font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT, anchor="w")
        title.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_LG, pady=(tokens.SPACING_LG, tokens.SPACING_MD))
        self.timeline_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=0)
        self.timeline_scroll.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=(0, tokens.SPACING_LG))
        self.timeline_scroll.grid_columnconfigure(0, weight=1)

    def _build_step_row(self, master: ctk.CTkFrame, row: int, step: Any) -> ctk.CTkFrame:
        status = step.status.value if hasattr(step.status, "value") else str(step.status)
        icon, color = STATUS_STYLES.get(status, STATUS_STYLES["PENDING"])
        row_frame = ctk.CTkFrame(master, fg_color=tokens.COLOR_BACKGROUND, corner_radius=tokens.RADIUS_MD)
        row_frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XS, pady=(0, tokens.SPACING_SM))
        row_frame.grid_columnconfigure(1, weight=1)
        icon_label = ctk.CTkLabel(row_frame, text=icon, width=28, font=tokens.FONT_BODY_BOLD, text_color=color)
        icon_label.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(tokens.SPACING_SM, tokens.SPACING_XS), pady=tokens.SPACING_SM)
        name_label = ctk.CTkLabel(row_frame, text=f"{step.step_id}  {step.name}", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w")
        name_label.grid(row=0, column=1, sticky="ew", padx=(0, tokens.SPACING_SM), pady=(tokens.SPACING_SM, 0))
        detail_parts = [f"trạng thái: {STATUS_TEXT.get(status, status)}", f"lần thử: {step.attempt}"]
        if step.error_message:
            detail_parts.append(f"lỗi: {step.error_message}")
        detail = ctk.CTkLabel(row_frame, text="  •  ".join(detail_parts), font=tokens.FONT_SMALL, text_color=tokens.COLOR_MUTED, anchor="w")
        detail.grid(row=1, column=1, sticky="ew", padx=(0, tokens.SPACING_SM), pady=(0, tokens.SPACING_SM))
        return row_frame

    def _build_right_tabs(self, master: ctk.CTkFrame) -> None:
        right = ctk.CTkFrame(master, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(tokens.SPACING_MD, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)
        self.tabview = ctk.CTkTabview(right, fg_color=tokens.COLOR_SURFACE, segmented_button_fg_color=tokens.COLOR_BACKGROUND)
        self.tabview.grid(row=0, column=0, sticky="nsew")
        self.tabview.add("Logs")
        self.tabview.add("Artifacts")
        self.tabview.add("Job State JSON")
        self._build_logs_tab(self.tabview.tab("Logs"))
        self._build_artifacts_tab(self.tabview.tab("Artifacts"))
        self._build_state_tab(self.tabview.tab("Job State JSON"))

    def _build_logs_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_MD, pady=(tokens.SPACING_MD, tokens.SPACING_SM))
        toolbar.grid_columnconfigure(1, weight=1)
        self.filter_menu = ctk.CTkOptionMenu(toolbar, values=["Tất cả", "Info", "Warn", "Error"], variable=self.log_filter_var, width=100, command=lambda _value: self._refresh_logs())
        self.filter_menu.grid(row=0, column=0, sticky="w", padx=(0, tokens.SPACING_SM))
        self.search_entry = ctk.CTkEntry(toolbar, textvariable=self.search_var, placeholder_text="Tìm trong log...", font=tokens.FONT_BODY)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, tokens.SPACING_SM))
        self.search_entry.bind("<KeyRelease>", lambda _event: self._refresh_logs())
        self.auto_scroll_checkbox = ctk.CTkCheckBox(toolbar, text="Tự cuộn", variable=self.auto_scroll_var, fg_color=tokens.COLOR_PRIMARY, border_color=tokens.COLOR_BORDER, font=tokens.FONT_BODY)
        self.auto_scroll_checkbox.grid(row=0, column=2, sticky="e", padx=(0, tokens.SPACING_SM))
        self.copy_button = self._secondary_button(toolbar, text="Copy log", command=self._copy_selected_log, width=100, height=36)
        self.copy_button.grid(row=0, column=3, sticky="e", padx=(0, tokens.SPACING_SM))
        self.open_log_button = self._secondary_button(toolbar, text="Mở file log", command=self._open_log_file, width=112, height=36)
        self.open_log_button.grid(row=0, column=4, sticky="e")
        self.logs_textbox = ctk.CTkTextbox(tab, font=("Consolas", 12), fg_color="#0B1220", text_color="#E5E7EB", corner_radius=tokens.RADIUS_MD, wrap="none")
        self.logs_textbox.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=(0, tokens.SPACING_MD))

    def _build_artifacts_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        self.artifact_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent", corner_radius=0)
        self.artifact_scroll.grid(row=0, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=tokens.SPACING_MD)
        self.artifact_scroll.grid_columnconfigure(1, weight=1)

    def _build_state_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        self.state_textbox = ctk.CTkTextbox(tab, font=("Consolas", 12), wrap="none", corner_radius=tokens.RADIUS_MD)
        self.state_textbox.grid(row=0, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=tokens.SPACING_MD)

    def set_job_state(self, job_state: JobState | None, output_dir: str) -> None:
        self.job_state = job_state
        self.output_dir = output_dir
        self._reset_polling_cache()
        self._refresh_all()
        self._schedule_realtime_refresh()

    def cancel_job(self) -> None:
        if self.on_cancel_job is not None:
            self.on_cancel_job()
        elif self.job_state is not None:
            self.job_state.status = JobStatus.CANCELED
            self._refresh_all()

    def _refresh_all(self) -> None:
        self._load_latest_job_state_from_disk()
        self._refresh_header()
        self._refresh_timeline()
        self._refresh_logs()
        self._refresh_artifacts()
        self._refresh_state_json()

    def _reset_polling_cache(self) -> None:
        self._change_detector = ChangeDetector()
        self._last_log_line_count = 0
        self._artifacts_folder_mtime = None
        self._cached_step_statuses.clear()
        self._timeline_rows_by_step_id.clear()
        self._timeline_frames_by_step_id.clear()
        self._cached_artifact_paths = ()

    def _schedule_realtime_refresh(self) -> None:
        if self.job_state is None:
            return
        if self.job_state.status not in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.WAITING_RETRY}:
            return
        self.after(1000, self._poll_realtime_state)

    def _poll_realtime_state(self) -> None:
        if self.job_state is None:
            return

        job_state_path = self._job_state_path()
        if self._change_detector.has_changed(job_state_path):
            self._load_latest_job_state_from_disk()
            self._refresh_header()
            self._refresh_timeline_cells()
            self._refresh_artifacts_if_changed()
            self._refresh_state_json()

        new_lines, total = self._change_detector.get_new_lines(self._log_file_path(), self._last_log_line_count)
        if new_lines:
            self._append_log_lines(new_lines)
            self._last_log_line_count = total
        elif total < self._last_log_line_count:
            self._refresh_logs()

        if self._artifacts_folder_changed():
            self._refresh_artifacts_if_changed()

        self._schedule_realtime_refresh()

    def _job_state_path(self) -> str:
        return str(Path(self.output_dir) / "job_state.json")

    def _log_file_path(self) -> str:
        return str(Path(self.output_dir) / "logs" / "job-events.ndjson")

    def _load_latest_job_state_from_disk(self) -> None:
        state_path = Path(self._job_state_path())
        if not state_path.exists():
            return
        try:
            self.job_state = JobState.model_validate(json.loads(state_path.read_text(encoding="utf-8")))
        except Exception:
            return

    def _refresh_header(self) -> None:
        if self.job_state is None:
            self.job_header_label.configure(text="Chưa có job đang hiển thị")
            self.cancel_button.configure(state="disabled")
            return
        status = self.job_state.status.value
        self.job_header_label.configure(text=f"Job {self.job_state.job_id}  •  Trạng thái: {STATUS_TEXT.get(status, status)}  •  Tháng: {self.job_state.report_month}")
        cancel_state = "normal" if self.job_state.status == JobStatus.RUNNING else "disabled"
        self.cancel_button.configure(state=cancel_state)

    def _refresh_timeline(self) -> None:
        for child in self.timeline_scroll.winfo_children():
            child.destroy()
        self._cached_step_statuses.clear()
        self._timeline_rows_by_step_id.clear()
        self._timeline_frames_by_step_id.clear()
        if self.job_state is None:
            ctk.CTkLabel(self.timeline_scroll, text="Chưa có dữ liệu timeline", font=tokens.FONT_BODY, text_color=tokens.COLOR_MUTED).grid(row=0, column=0, padx=tokens.SPACING_MD, pady=tokens.SPACING_MD)
            return
        row = 0
        current_phase = ""
        for step in self.job_state.steps:
            phase = PHASES.get(step.step_id.split(".")[0], "Khác")
            if phase != current_phase:
                current_phase = phase
                ctk.CTkLabel(self.timeline_scroll, text=current_phase, font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_PRIMARY, anchor="w").grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_SM, pady=(tokens.SPACING_MD, tokens.SPACING_XS))
                row += 1
            row_frame = self._build_step_row(self.timeline_scroll, row, step)
            self._timeline_rows_by_step_id[step.step_id] = row
            self._timeline_frames_by_step_id[step.step_id] = row_frame
            self._cached_step_statuses[step.step_id] = self._step_status_value(step)
            row += 1

    def _refresh_timeline_cells(self) -> None:
        """Chỉ update cells có status khác với cached state."""
        if self.job_state is None:
            return
        for step in self.job_state.steps:
            cached_status = self._cached_step_statuses.get(step.step_id)
            current_status = self._step_status_value(step)
            if step.step_id not in self._timeline_rows_by_step_id:
                self._refresh_timeline()
                return
            if cached_status != current_status:
                self._update_single_cell(step)
                self._cached_step_statuses[step.step_id] = current_status

    def _update_single_cell(self, step: Any) -> None:
        row = self._timeline_rows_by_step_id[step.step_id]
        old_frame = self._timeline_frames_by_step_id.get(step.step_id)
        if old_frame is not None:
            old_frame.destroy()
        self._timeline_frames_by_step_id[step.step_id] = self._build_step_row(self.timeline_scroll, row, step)

    def _step_status_value(self, step: Any) -> str:
        return step.status.value if hasattr(step.status, "value") else str(step.status)

    def _read_log_events(self) -> list[EventLogEntry]:
        level = self.log_filter_var.get().upper()
        level_filter = None if level in {"TẤT CẢ", "ALL"} else level
        return CheckpointManager(self.output_dir).read_events(level_filter=level_filter)

    def _refresh_logs(self) -> None:
        if not hasattr(self, "logs_textbox"):
            return
        query = self.search_var.get().strip().lower()
        lines = []
        for event in self._read_log_events():
            formatted = self._format_log_event(event)
            if query and query not in formatted.lower():
                continue
            lines.append(formatted)
        self.logs_textbox.configure(state="normal")
        self.logs_textbox.delete("1.0", "end")
        self.logs_textbox.insert("1.0", "\n".join(lines) if lines else "Chưa có log thực cho job này.")
        if self.auto_scroll_var.get():
            self.logs_textbox.see("end")
        self.logs_textbox.configure(state="disabled")
        _, total = self._change_detector.get_new_lines(self._log_file_path(), 0)
        self._last_log_line_count = total

    def _append_log_lines(self, lines: list[str]) -> None:
        """Append dòng mới vào log textbox, không rebuild."""
        if not hasattr(self, "logs_textbox"):
            return
        formatted_lines = []
        for line in lines:
            parsed = self._parse_log_line(line.strip())
            if parsed and self._matches_filter(parsed):
                formatted_lines.append(parsed["formatted"])
        if not formatted_lines:
            return
        self.logs_textbox.configure(state="normal")
        current_text = self.logs_textbox.get("1.0", "end").strip()
        if current_text == "Chưa có log thực cho job này.":
            self.logs_textbox.delete("1.0", "end")
            prefix = ""
        else:
            prefix = "\n" if current_text else ""
        self.logs_textbox.insert("end", prefix + "\n".join(formatted_lines))
        if self.auto_scroll_var.get():
            self.logs_textbox.see("end")
        self.logs_textbox.configure(state="disabled")

    def _parse_log_line(self, line: str) -> dict[str, str] | None:
        if not line:
            return None
        try:
            event = EventLogEntry.model_validate(json.loads(line))
        except Exception:
            return None
        return {"level": event.level.upper(), "formatted": self._format_log_event(event)}

    def _matches_filter(self, parsed: dict[str, str]) -> bool:
        level = self.log_filter_var.get().upper()
        if level not in {"TẤT CẢ", "ALL"} and parsed["level"] != level:
            return False
        query = self.search_var.get().strip().lower()
        return not query or query in parsed["formatted"].lower()

    def _format_log_event(self, event: EventLogEntry) -> str:
        timestamp = self._format_log_time(event.timestamp)
        step_id = event.step_id or "JOB"
        return mask_sensitive_text(f"[{timestamp}] [{event.level.upper()}] [{step_id}] {event.message}")

    def _refresh_artifacts_if_changed(self) -> None:
        artifacts = self._collect_artifacts()
        artifact_paths = tuple(artifact.path for artifact in artifacts)
        if artifact_paths != self._cached_artifact_paths:
            self._refresh_artifacts(artifacts)

    def _artifacts_folder_changed(self) -> bool:
        """Check nếu thư mục artifacts có file mới/xóa."""
        artifacts_dir = Path(self.output_dir)
        if not artifacts_dir.exists():
            return False
        current_mtime = os.path.getmtime(artifacts_dir)
        if current_mtime != self._artifacts_folder_mtime:
            self._artifacts_folder_mtime = current_mtime
            return True
        return False

    def _refresh_artifacts(self, artifacts: list[Artifact] | None = None) -> None:
        for child in self.artifact_scroll.winfo_children():
            child.destroy()
        artifacts = self._collect_artifacts() if artifacts is None else artifacts
        self._cached_artifact_paths = tuple(artifact.path for artifact in artifacts)
        if not artifacts:
            ctk.CTkLabel(self.artifact_scroll, text="Chưa có artifact", font=tokens.FONT_BODY, text_color=tokens.COLOR_MUTED).grid(row=0, column=0, sticky="w", padx=tokens.SPACING_MD, pady=tokens.SPACING_MD)
            return
        for row, artifact in enumerate(artifacts):
            row_frame = ctk.CTkFrame(self.artifact_scroll, fg_color=tokens.COLOR_BACKGROUND, corner_radius=tokens.RADIUS_MD)
            row_frame.grid(row=row, column=0, sticky="ew", pady=(0, tokens.SPACING_SM))
            row_frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row_frame, text=artifact.filename, font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w").grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_MD, pady=(tokens.SPACING_MD, 0))
            ctk.CTkLabel(row_frame, text=f"{artifact.type}  •  {artifact.size}", font=tokens.FONT_SMALL, text_color=tokens.COLOR_MUTED, anchor="w").grid(row=1, column=0, sticky="ew", padx=tokens.SPACING_MD, pady=(0, tokens.SPACING_MD))
            self._secondary_button(row_frame, text="Mở", command=lambda path=artifact.path: self._open_path(path), width=62, height=32).grid(row=0, column=1, rowspan=2, padx=(tokens.SPACING_SM, 0), pady=tokens.SPACING_MD)
            self._secondary_button(row_frame, text="Hiện thư mục", command=lambda path=artifact.path: self._reveal_path(path), width=96, height=32).grid(row=0, column=2, rowspan=2, padx=tokens.SPACING_SM, pady=tokens.SPACING_MD)

    def _refresh_state_json(self) -> None:
        self.state_textbox.configure(state="normal")
        self.state_textbox.delete("1.0", "end")
        self.state_textbox.insert("1.0", self._format_job_state_json())
        self.state_textbox.configure(state="disabled")

    def _collect_artifacts(self) -> list[Artifact]:
        artifacts: list[Artifact] = []
        if self.job_state is None:
            return artifacts
        for step in self.job_state.steps:
            for path in step.artifacts:
                artifacts.append(self._artifact_from_path(path))
        state_path = Path(self._job_state_path())
        log_path = Path(self._log_file_path())
        for path in (state_path, log_path):
            if path.exists():
                artifacts.append(self._artifact_from_path(str(path)))
        return artifacts

    def _artifact_from_path(self, path: str) -> Artifact:
        p = Path(path)
        size = "0 B"
        if p.exists() and p.is_file():
            size = self._format_file_size(p.stat().st_size)
        return Artifact(filename=p.name or str(p), type=p.suffix.lstrip(".") or "file", size=size, path=str(p))

    def _format_job_state_json(self) -> str:
        if self.job_state is None:
            return json.dumps({"message": "Chưa có job"}, ensure_ascii=False, indent=2)
        return json.dumps(self.job_state.model_dump(), ensure_ascii=False, indent=2)

    def _copy_selected_log(self) -> None:
        try:
            selected = self.logs_textbox.get("sel.first", "sel.last")
        except Exception:
            selected = self.logs_textbox.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(selected)

    def _open_output(self) -> None:
        if self.on_open_output is not None:
            self.on_open_output()
            return
        outputs_path = os.path.abspath("outputs")
        os.makedirs(outputs_path, exist_ok=True)
        os.startfile(outputs_path)

    def _open_log_file(self) -> None:
        log_path = Path(self.output_dir) / "logs" / "job-events.ndjson"
        if log_path.exists():
            os.startfile(os.path.abspath(log_path))

    def _open_path(self, path: str) -> None:
        if os.path.exists(path):
            os.startfile(os.path.abspath(path))

    def _reveal_path(self, path: str) -> None:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        os.makedirs(folder or "outputs", exist_ok=True)
        os.startfile(os.path.abspath(folder or "outputs"))

    def _mock_action(self) -> None:
        return

    def _secondary_button(self, master: ctk.CTkBaseClass, text: str, command: Callable[[], None], width: int = 120, height: int = 38) -> ctk.CTkButton:
        return ctk.CTkButton(master, text=text, width=width, height=height, corner_radius=tokens.RADIUS_MD, fg_color=tokens.COLOR_SURFACE, hover_color=tokens.COLOR_BACKGROUND, border_width=tokens.BORDER_WIDTH, border_color=tokens.COLOR_BORDER, text_color=tokens.COLOR_TEXT, font=tokens.FONT_BODY, command=command)

    def _create_card(self, master: ctk.CTkBaseClass) -> ctk.CTkFrame:
        return ctk.CTkFrame(master, fg_color=tokens.COLOR_SURFACE, corner_radius=tokens.RADIUS_LG, border_width=tokens.BORDER_WIDTH, border_color=tokens.COLOR_BORDER)

    def _format_log_time(self, timestamp: str) -> str:
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%H:%M:%S")
        except ValueError:
            return timestamp

    def _format_file_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"

    def on_show(self) -> None:
        """Lifecycle hook để NavigationController gọi khi screen được hiển thị."""
        self._refresh_all()
