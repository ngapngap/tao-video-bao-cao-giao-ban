"""Màn hình Job & Logs với timeline, log viewer, artifacts và job_state mock."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import customtkinter as ctk

from app.ui import tokens


STATUS_STYLES = {
    "DONE": ("✓", tokens.COLOR_SUCCESS),
    "RUNNING": ("●", tokens.COLOR_STATUS_RUNNING),
    "PENDING": ("○", tokens.COLOR_NEUTRAL),
    "FAILED": ("✗", tokens.COLOR_ERROR),
    "WAITING_RETRY": ("⚠", tokens.COLOR_WARNING),
    "CANCELED": ("○", tokens.COLOR_NEUTRAL),
}


@dataclass(frozen=True)
class StepRow:
    """Data object cho một step trong timeline."""

    step_id: str
    phase: str
    name: str
    status: str
    attempt: int
    duration: str
    last_error: str = ""
    error_code: str = ""
    retryable: bool = True


@dataclass(frozen=True)
class LogEntry:
    """Data object cho một dòng log."""

    time: str
    level: str
    step_id: str
    message: str

    def format(self) -> str:
        return f"[{self.time}] [{self.level}] [{self.step_id}] {self.message}"


@dataclass(frozen=True)
class Artifact:
    """Data object cho artifact của job."""

    filename: str
    type: str
    size: str
    path: str


def generate_mock_job_data() -> dict[str, Any]:
    """Sinh mock data cho màn hình Job & Logs theo Issue #5."""
    phases = [
        ("Input & Parse", "S1.1", "Copy PDF input", "DONE", 1, "00:03"),
        ("Input & Parse", "S1.2", "Parse PDF text", "DONE", 1, "00:11"),
        ("Input & Parse", "S1.3", "Normalize extracted pages", "DONE", 1, "00:07"),
        ("AI Pass 1", "P1.1", "Extract report metrics", "DONE", 1, "01:26"),
        ("AI Pass 1", "P1.1b", "Validate structured data", "DONE", 1, "00:18"),
        ("Workflow Compose", "P1.2", "Compose video outline", "DONE", 1, "00:24"),
        ("Workflow Compose", "P1.3", "Write generated workflow", "DONE", 1, "00:08"),
        ("AI Pass 2", "S2.1", "Generate scene brief", "DONE", 1, "00:42"),
        ("AI Pass 2", "S2.2", "Generate narration script", "RUNNING", 2, "02:13"),
        ("AI Pass 2", "S2.3", "Generate visual spec", "PENDING", 0, ""),
        ("AI Pass 2", "S2.4", "Generate TTS plan", "PENDING", 0, ""),
        ("AI Pass 2", "S2.5", "Generate Remotion scenes", "PENDING", 0, ""),
        ("AI Pass 2", "S2.6", "Validate scene assets", "PENDING", 0, ""),
        ("AI Pass 2", "S2.7", "Render preview segments", "PENDING", 0, ""),
        ("AI Pass 2", "S2.8", "Render final video", "PENDING", 0, ""),
        ("Render & Package", "S2.8a", "Package MP4", "PENDING", 0, ""),
        ("Render & Package", "S2.9", "Write final metadata", "PENDING", 0, ""),
        ("Render & Package", "S2.10", "Cleanup temp files", "PENDING", 0, ""),
    ]
    steps = [StepRow(*item) for item in phases]

    base_time = datetime(2026, 5, 5, 15, 42, 0)
    log_templates = [
        ("INFO", "S1.1", "Created job output directory outputs/202603/20260505-001"),
        ("INFO", "S1.1", "Copied input PDF to input/bao-cao-giao-ban-202603.pdf"),
        ("INFO", "S1.2", "Started PDF text extraction with pymupdf"),
        ("INFO", "S1.2", "Extracted 18 pages, 42 tables candidates"),
        ("WARN", "S1.3", "Detected 2 low-confidence table rows; kept for AI validation"),
        ("INFO", "P1.1", "Submitted extraction prompt chunk 1/3"),
        ("INFO", "P1.1", "Submitted extraction prompt chunk 2/3"),
        ("INFO", "P1.1", "Submitted extraction prompt chunk 3/3"),
        ("INFO", "P1.1b", "Pydantic validation passed for report metrics"),
        ("INFO", "P1.2", "Composed 12-section video outline"),
        ("INFO", "P1.3", "Generated workflow file workflow/generated-workflow.json"),
        ("INFO", "S2.1", "Scene brief generated for 8 frames"),
        ("INFO", "S2.2", "Started narration script generation"),
        ("WARN", "S2.2", "Model response exceeded soft budget; retry with shorter context"),
        ("INFO", "S2.2", "Retry attempt 2 started after backoff 30s"),
        ("INFO", "S2.2", "Received partial narration for frame 1-4"),
        ("INFO", "S2.2", "Waiting for frame 5-8 completion"),
        ("INFO", "S2.3", "Queued visual spec generation"),
        ("INFO", "S2.4", "Queued TTS plan generation"),
        ("ERROR", "S2.6", "Mock historical error: missing optional logo asset; fallback available"),
    ]
    logs = [
        LogEntry((base_time + timedelta(seconds=index * 11)).strftime("%H:%M:%S"), level, step_id, message)
        for index, (level, step_id, message) in enumerate(log_templates)
    ]

    artifacts = [
        Artifact("bao-cao-giao-ban-202603.pdf", "input/pdf", "4.8 MB", "outputs/202603/20260505-001/input/bao-cao-giao-ban-202603.pdf"),
        Artifact("extracted-report.json", "parsed/json", "128 KB", "outputs/202603/20260505-001/parsed/extracted-report.json"),
        Artifact("generated-workflow.json", "workflow/json", "74 KB", "outputs/202603/20260505-001/workflow/generated-workflow.json"),
        Artifact("tts-script.md", "tts/markdown", "18 KB", "outputs/202603/20260505-001/tts/tts-script.md"),
        Artifact("bao-cao-giao-ban-202603.mp4", "final/video", "96 MB", "outputs/202603/20260505-001/final/bao-cao-giao-ban-202603.mp4"),
    ]

    return {
        "job_id": "20260505-001",
        "status": "RUNNING",
        "report_month": "202603",
        "steps": steps,
        "logs": logs,
        "artifacts": artifacts,
    }


class JobLogsScreen(ctk.CTkFrame):
    """Màn hình theo dõi job, log realtime mock và artifact."""

    def __init__(self, master: ctk.CTkBaseClass, on_open_output: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color=tokens.COLOR_BACKGROUND, corner_radius=0)
        self.on_open_output = on_open_output
        self.job_data = generate_mock_job_data()
        self.log_filter_var = ctk.StringVar(value="All")
        self.search_var = ctk.StringVar(value="")
        self.auto_scroll_var = ctk.BooleanVar(value=True)
        self._phase_row_index = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_content()
        self._refresh_logs()

    def _build_header(self) -> None:
        header = self._create_card(self)
        header.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_XL, tokens.SPACING_MD))
        header.grid_columnconfigure(0, weight=1)

        meta_frame = ctk.CTkFrame(header, fg_color="transparent")
        meta_frame.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=tokens.SPACING_LG)
        meta_frame.grid_columnconfigure(0, weight=1)

        self.job_header_label = ctk.CTkLabel(
            meta_frame,
            text=f"Job {self.job_data['job_id']}  •  Status: {self.job_data['status']}  •  Tháng: {self.job_data['report_month']}",
            font=tokens.FONT_HEADING_LARGE,
            text_color=tokens.COLOR_TEXT,
            anchor="w",
        )
        self.job_header_label.grid(row=0, column=0, sticky="ew")

        buttons = ctk.CTkFrame(meta_frame, fg_color="transparent")
        buttons.grid(row=0, column=1, sticky="e")
        for index, (text, command) in enumerate(
            (
                ("Resume", self._mock_action),
                ("Retry Failed Step", self._mock_action),
                ("Cancel", self._mock_action),
                ("Open output", self._open_output),
            )
        ):
            button = self._secondary_button(buttons, text=text, command=command, width=132)
            button.grid(row=0, column=index, sticky="e", padx=(tokens.SPACING_SM if index else 0, 0))

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

        title = ctk.CTkLabel(card, text="Step timeline", font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT, anchor="w")
        title.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_LG, pady=(tokens.SPACING_LG, tokens.SPACING_MD))

        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=0)
        scroll.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=(0, tokens.SPACING_LG))
        scroll.grid_columnconfigure(0, weight=1)

        current_phase = ""
        row = 0
        for step in self.job_data["steps"]:
            if step.phase != current_phase:
                current_phase = step.phase
                phase_label = ctk.CTkLabel(scroll, text=current_phase, font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_PRIMARY, anchor="w")
                phase_label.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_SM, pady=(tokens.SPACING_MD, tokens.SPACING_XS))
                row += 1
            self._build_step_row(scroll, row, step)
            row += 1

    def _build_step_row(self, master: ctk.CTkFrame, row: int, step: StepRow) -> None:
        icon, color = STATUS_STYLES.get(step.status, STATUS_STYLES["PENDING"])
        row_frame = ctk.CTkFrame(master, fg_color=tokens.COLOR_BACKGROUND, corner_radius=tokens.RADIUS_MD)
        row_frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XS, pady=(0, tokens.SPACING_SM))
        row_frame.grid_columnconfigure(1, weight=1)

        icon_label = ctk.CTkLabel(row_frame, text=icon, width=28, font=tokens.FONT_BODY_BOLD, text_color=color)
        icon_label.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(tokens.SPACING_SM, tokens.SPACING_XS), pady=tokens.SPACING_SM)

        name_label = ctk.CTkLabel(row_frame, text=f"{step.step_id}  {step.name}", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w")
        name_label.grid(row=0, column=1, sticky="ew", padx=(0, tokens.SPACING_SM), pady=(tokens.SPACING_SM, 0))

        detail_parts = [f"attempt: {step.attempt}"]
        if step.duration:
            detail_parts.append(f"duration: {step.duration}")
        if step.last_error:
            detail_parts.append(f"error: {step.last_error}")
        detail = ctk.CTkLabel(row_frame, text="  •  ".join(detail_parts), font=tokens.FONT_SMALL, text_color=tokens.COLOR_MUTED, anchor="w")
        detail.grid(row=1, column=1, sticky="ew", padx=(0, tokens.SPACING_SM), pady=(0, tokens.SPACING_SM))

    def _build_right_tabs(self, master: ctk.CTkFrame) -> None:
        right = ctk.CTkFrame(master, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(tokens.SPACING_MD, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        self._build_failure_summary(right)

        self.tabview = ctk.CTkTabview(right, fg_color=tokens.COLOR_SURFACE, segmented_button_fg_color=tokens.COLOR_BACKGROUND)
        self.tabview.grid(row=1, column=0, sticky="nsew")
        self.tabview.add("Logs")
        self.tabview.add("Artifacts")
        self.tabview.add("Job State JSON")

        self._build_logs_tab(self.tabview.tab("Logs"))
        self._build_artifacts_tab(self.tabview.tab("Artifacts"))
        self._build_state_tab(self.tabview.tab("Job State JSON"))

    def _build_failure_summary(self, master: ctk.CTkFrame) -> None:
        failed_step = next((step for step in self.job_data["steps"] if step.status == "FAILED"), None)
        if failed_step is None:
            return

        card = self._create_card(master)
        card.grid(row=0, column=0, sticky="ew", pady=(0, tokens.SPACING_MD))
        card.grid_columnconfigure(0, weight=1)
        text = (
            f"Failed step: {failed_step.name}\n"
            f"Error code: {failed_step.error_code or 'UNKNOWN'}\n"
            f"Retryable: {'yes' if failed_step.retryable else 'no'}\n"
            "Suggested action: Kiểm tra log chi tiết rồi retry từ checkpoint gần nhất."
        )
        label = ctk.CTkLabel(card, text=text, font=tokens.FONT_BODY, text_color=tokens.COLOR_ERROR, anchor="w", justify="left")
        label.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_LG, pady=tokens.SPACING_LG)
        if failed_step.retryable:
            button = self._secondary_button(card, text="Retry failed step", command=self._mock_action, width=150)
            button.grid(row=0, column=1, sticky="e", padx=(0, tokens.SPACING_LG), pady=tokens.SPACING_LG)

    def _build_logs_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_MD, pady=(tokens.SPACING_MD, tokens.SPACING_SM))
        toolbar.grid_columnconfigure(1, weight=1)

        self.filter_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["All", "Info", "Warn", "Error"],
            variable=self.log_filter_var,
            width=100,
            command=lambda _value: self._refresh_logs(),
        )
        self.filter_menu.grid(row=0, column=0, sticky="w", padx=(0, tokens.SPACING_SM))

        self.search_entry = ctk.CTkEntry(toolbar, textvariable=self.search_var, placeholder_text="Tìm trong log...", font=tokens.FONT_BODY)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, tokens.SPACING_SM))
        self.search_entry.bind("<KeyRelease>", lambda _event: self._refresh_logs())

        self.auto_scroll_checkbox = ctk.CTkCheckBox(
            toolbar,
            text="Auto scroll",
            variable=self.auto_scroll_var,
            fg_color=tokens.COLOR_PRIMARY,
            border_color=tokens.COLOR_BORDER,
            font=tokens.FONT_BODY,
        )
        self.auto_scroll_checkbox.grid(row=0, column=2, sticky="e", padx=(0, tokens.SPACING_SM))

        self.copy_button = self._secondary_button(toolbar, text="Copy selected", command=self._copy_selected_log, width=120, height=36)
        self.copy_button.grid(row=0, column=3, sticky="e", padx=(0, tokens.SPACING_SM))
        self.open_log_button = self._secondary_button(toolbar, text="Open log file", command=self._mock_action, width=112, height=36)
        self.open_log_button.grid(row=0, column=4, sticky="e")

        self.logs_textbox = ctk.CTkTextbox(
            tab,
            font=("Consolas", 12),
            fg_color="#0B1220",
            text_color="#E5E7EB",
            corner_radius=tokens.RADIUS_MD,
            wrap="none",
        )
        self.logs_textbox.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=(0, tokens.SPACING_MD))

    def _build_artifacts_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent", corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=tokens.SPACING_MD)
        scroll.grid_columnconfigure(1, weight=1)

        for row, artifact in enumerate(self.job_data["artifacts"]):
            row_frame = ctk.CTkFrame(scroll, fg_color=tokens.COLOR_BACKGROUND, corner_radius=tokens.RADIUS_MD)
            row_frame.grid(row=row, column=0, sticky="ew", pady=(0, tokens.SPACING_SM))
            row_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row_frame, text="📄", font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT).grid(
                row=0, column=0, rowspan=2, padx=tokens.SPACING_MD, pady=tokens.SPACING_MD
            )
            ctk.CTkLabel(row_frame, text=artifact.filename, font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w").grid(
                row=0, column=1, sticky="ew", pady=(tokens.SPACING_MD, 0)
            )
            ctk.CTkLabel(row_frame, text=f"{artifact.type}  •  {artifact.size}", font=tokens.FONT_SMALL, text_color=tokens.COLOR_MUTED, anchor="w").grid(
                row=1, column=1, sticky="ew", pady=(0, tokens.SPACING_MD)
            )
            self._secondary_button(row_frame, text="Open", command=self._mock_action, width=72, height=32).grid(
                row=0, column=2, rowspan=2, padx=(tokens.SPACING_SM, 0), pady=tokens.SPACING_MD
            )
            self._secondary_button(row_frame, text="Reveal", command=self._mock_action, width=76, height=32).grid(
                row=0, column=3, rowspan=2, padx=tokens.SPACING_SM, pady=tokens.SPACING_MD
            )

    def _build_state_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        state_textbox = ctk.CTkTextbox(tab, font=("Consolas", 12), wrap="none", corner_radius=tokens.RADIUS_MD)
        state_textbox.grid(row=0, column=0, sticky="nsew", padx=tokens.SPACING_MD, pady=tokens.SPACING_MD)
        state_textbox.insert("1.0", self._format_job_state_json())
        state_textbox.configure(state="disabled")

    def _refresh_logs(self) -> None:
        if not hasattr(self, "logs_textbox"):
            return
        selected_level = self.log_filter_var.get().upper()
        query = self.search_var.get().strip().lower()
        lines = []
        for log in self.job_data["logs"]:
            if selected_level != "ALL" and log.level != selected_level:
                continue
            formatted = log.format()
            if query and query not in formatted.lower():
                continue
            lines.append(formatted)

        self.logs_textbox.configure(state="normal")
        self.logs_textbox.delete("1.0", "end")
        self.logs_textbox.insert("1.0", "\n".join(lines) if lines else "Không có log phù hợp với bộ lọc.")
        if self.auto_scroll_var.get():
            self.logs_textbox.see("end")
        self.logs_textbox.configure(state="disabled")

    def _format_job_state_json(self) -> str:
        state = {
            "job_id": self.job_data["job_id"],
            "status": self.job_data["status"],
            "report_month": self.job_data["report_month"],
            "steps": [step.__dict__ for step in self.job_data["steps"]],
            "artifacts": [artifact.__dict__ for artifact in self.job_data["artifacts"]],
        }
        return json.dumps(state, ensure_ascii=False, indent=2)

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

    def _mock_action(self) -> None:
        return

    def _secondary_button(
        self,
        master: ctk.CTkBaseClass,
        text: str,
        command: Callable[[], None],
        width: int = 120,
        height: int = 38,
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            master,
            text=text,
            width=width,
            height=height,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            hover_color=tokens.COLOR_BACKGROUND,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            command=command,
        )

    def _create_card(self, master: ctk.CTkBaseClass) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            master,
            fg_color=tokens.COLOR_SURFACE,
            corner_radius=tokens.RADIUS_LG,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
        )

    def on_show(self) -> None:
        """Lifecycle hook để NavigationController gọi khi screen được hiển thị."""
