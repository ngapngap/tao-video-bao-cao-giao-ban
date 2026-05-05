"""Màn hình Lịch sử jobs với filter, bảng và actions."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from app.core import JobState, JobStatus
from app.ui import tokens

STATUS_COLORS = {
    "DONE": tokens.COLOR_SUCCESS,
    "FAILED": tokens.COLOR_ERROR,
    "RUNNING": tokens.COLOR_STATUS_RUNNING,
    "CANCELED": tokens.COLOR_NEUTRAL,
    "QUEUED": tokens.COLOR_WARNING,
}
STATUS_TEXT = {
    "ALL": "Tất cả",
    "DONE": "Hoàn thành",
    "FAILED": "Thất bại",
    "RUNNING": "Đang chạy",
    "CANCELED": "Đã hủy",
    "QUEUED": "Đang chờ",
}


@dataclass(frozen=True)
class HistoryJob:
    """Data object cho một job trong lịch sử."""

    month: str
    job_id: str
    pdf_file: str
    status: str
    created: str
    duration: str
    final_video: str
    output_folder: str


def generate_mock_history_data() -> list[HistoryJob]:
    """Sinh job mẫu cho màn hình Lịch sử."""
    return [
        HistoryJob("202603", "20260505-001", "bao-cao-giao-ban-202603.pdf", "RUNNING", "2026-05-05 15:42", "05:18", "-", "outputs/202603/20260505-001"),
        HistoryJob("202602", "20260402-003", "bao-cao-giao-ban-202602.pdf", "DONE", "2026-04-02 09:30", "18:44", "bao-cao-giao-ban-202602.mp4", "outputs/202602/20260402-003"),
    ]


class HistoryScreen(ctk.CTkFrame):
    """Màn hình lọc và quản lý lịch sử job local."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        on_view_details: Callable[[str], None] | None = None,
        on_delete_job: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color=tokens.COLOR_BACKGROUND, corner_radius=0)
        self.on_view_details = on_view_details
        self.on_delete_job = on_delete_job
        self.jobs = generate_mock_history_data()
        self.month_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Tất cả")
        self.keyword_var = ctk.StringVar(value="")
        self.filtered_jobs = list(self.jobs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_filters()
        self._build_table_card()
        self._refresh_table()

    def _build_filters(self) -> None:
        filters = self._create_card(self)
        filters.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_XL, tokens.SPACING_MD))
        filters.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(filters, text="Tháng", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT).grid(row=0, column=0, sticky="w", padx=(tokens.SPACING_LG, tokens.SPACING_SM), pady=(tokens.SPACING_LG, tokens.SPACING_XS))
        ctk.CTkLabel(filters, text="Trạng thái", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT).grid(row=0, column=1, sticky="w", padx=(0, tokens.SPACING_SM), pady=(tokens.SPACING_LG, tokens.SPACING_XS))
        ctk.CTkLabel(filters, text="Từ khóa", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT).grid(row=0, column=2, sticky="w", padx=(0, tokens.SPACING_SM), pady=(tokens.SPACING_LG, tokens.SPACING_XS))
        self.month_entry = ctk.CTkEntry(filters, textvariable=self.month_var, width=130, placeholder_text="YYYYMM", font=tokens.FONT_BODY)
        self.month_entry.grid(row=1, column=0, sticky="ew", padx=(tokens.SPACING_LG, tokens.SPACING_SM), pady=(0, tokens.SPACING_LG))
        self.month_entry.bind("<KeyRelease>", lambda _event: self._refresh_table())
        self.status_dropdown = ctk.CTkOptionMenu(filters, values=["Tất cả", "Hoàn thành", "Thất bại", "Đang chạy", "Đã hủy", "Đang chờ"], variable=self.status_var, width=150, command=lambda _value: self._refresh_table())
        self.status_dropdown.grid(row=1, column=1, sticky="ew", padx=(0, tokens.SPACING_SM), pady=(0, tokens.SPACING_LG))
        self.keyword_entry = ctk.CTkEntry(filters, textvariable=self.keyword_var, placeholder_text="PDF, mã job, video...", font=tokens.FONT_BODY)
        self.keyword_entry.grid(row=1, column=2, sticky="ew", padx=(0, tokens.SPACING_SM), pady=(0, tokens.SPACING_LG))
        self.keyword_entry.bind("<KeyRelease>", lambda _event: self._refresh_table())
        search_button = ctk.CTkButton(filters, text="Tìm kiếm", width=110, height=36, corner_radius=tokens.RADIUS_MD, fg_color=tokens.COLOR_PRIMARY, hover_color=tokens.COLOR_PRIMARY_HOVER, text_color=tokens.COLOR_WHITE, font=tokens.FONT_BODY_BOLD, command=self._refresh_table)
        search_button.grid(row=1, column=3, sticky="e", padx=(0, tokens.SPACING_LG), pady=(0, tokens.SPACING_LG))

    def _build_table_card(self) -> None:
        card = self._create_card(self)
        card.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_XL))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        title = ctk.CTkLabel(card, text="Danh sách job local", font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT, anchor="w")
        title.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_LG, pady=(tokens.SPACING_LG, tokens.SPACING_MD))
        self.table_frame = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=0)
        self.table_frame.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_LG, pady=(0, tokens.SPACING_LG))
        for column, weight in enumerate((1, 2, 3, 1, 2, 1, 2, 4)):
            self.table_frame.grid_columnconfigure(column, weight=weight, uniform="history_table")

    def upsert_job(self, job_state: JobState, payload: dict[str, str], output_folder: str) -> None:
        """Thêm hoặc cập nhật job runtime vào lịch sử."""
        created = self._format_created(job_state.created_at)
        pdf_file = os.path.basename(payload.get("pdf_path") or "-")
        existing = next((job for job in self.jobs if job.job_id == job_state.job_id), None)
        if existing is not None and pdf_file == "-":
            pdf_file = existing.pdf_file
        final_video = "video.mp4" if job_state.status == JobStatus.DONE else "-"
        updated = HistoryJob(job_state.report_month, job_state.job_id, pdf_file, job_state.status.value, created, self._duration_text(job_state), final_video, output_folder)
        self.jobs = [updated if job.job_id == job_state.job_id else job for job in self.jobs]
        if existing is None:
            self.jobs.insert(0, updated)
        self._refresh_table()

    def _refresh_table(self) -> None:
        month_filter = self.month_var.get().strip()
        status_filter = self._status_code(self.status_var.get().strip())
        keyword = self.keyword_var.get().strip().lower()
        self.filtered_jobs = []
        for job in self.jobs:
            haystack = f"{job.month} {job.job_id} {job.pdf_file} {job.status} {job.final_video}".lower()
            if month_filter and month_filter not in job.month:
                continue
            if status_filter != "ALL" and status_filter != job.status:
                continue
            if keyword and keyword not in haystack:
                continue
            self.filtered_jobs.append(job)
        for child in self.table_frame.winfo_children():
            child.destroy()
        if not self.filtered_jobs:
            empty = ctk.CTkLabel(self.table_frame, text="Chưa có job nào. Hãy tạo video từ màn hình Tạo video.", font=tokens.FONT_BODY, text_color=tokens.COLOR_MUTED, anchor="center")
            empty.grid(row=0, column=0, columnspan=8, sticky="nsew", padx=tokens.SPACING_XL, pady=tokens.SPACING_2XL)
            return
        headers = ["Tháng", "Mã job", "File PDF", "Trạng thái", "Tạo lúc", "Thời lượng", "Video cuối", "Thao tác"]
        for column, header in enumerate(headers):
            label = ctk.CTkLabel(self.table_frame, text=header, font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_PRIMARY, anchor="w")
            label.grid(row=0, column=column, sticky="ew", padx=tokens.SPACING_SM, pady=(0, tokens.SPACING_SM))
        for row, job in enumerate(self.filtered_jobs, start=1):
            self._build_job_row(row, job)

    def _build_job_row(self, row: int, job: HistoryJob) -> None:
        values = [job.month, job.job_id, job.pdf_file, STATUS_TEXT.get(job.status, job.status), job.created, job.duration, job.final_video]
        for column, value in enumerate(values):
            color = STATUS_COLORS.get(job.status, tokens.COLOR_TEXT) if column == 3 else tokens.COLOR_TEXT
            font = tokens.FONT_BODY_BOLD if column == 3 else tokens.FONT_BODY
            cell = ctk.CTkLabel(self.table_frame, text=value, font=font, text_color=color, anchor="w", justify="left", wraplength=230 if column in (2, 6) else 120)
            cell.grid(row=row, column=column, sticky="ew", padx=tokens.SPACING_SM, pady=tokens.SPACING_SM)
        actions = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        actions.grid(row=row, column=7, sticky="ew", padx=tokens.SPACING_SM, pady=tokens.SPACING_SM)
        actions.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._action_button(actions, "Xem chi tiết", lambda job_id=job.job_id: self._view_details(job_id), 108).grid(row=0, column=0, padx=(0, tokens.SPACING_XS))
        video_state = "normal" if job.status == "DONE" else "disabled"
        self._action_button(actions, "Mở video", self._mock_action, 82, state=video_state).grid(row=0, column=1, padx=(0, tokens.SPACING_XS))
        self._action_button(actions, "Mở thư mục", lambda folder=job.output_folder: self._open_folder(folder), 92).grid(row=0, column=2, padx=(0, tokens.SPACING_XS))
        self._action_button(actions, "Xóa", lambda job_id=job.job_id: self._confirm_delete(job_id), 58, danger=True).grid(row=0, column=3)

    def _view_details(self, job_id: str) -> None:
        if self.on_view_details is not None:
            self.on_view_details(job_id)

    def _open_folder(self, folder: str) -> None:
        os.makedirs(folder, exist_ok=True)
        os.startfile(os.path.abspath(folder))

    def _confirm_delete(self, job_id: str) -> None:
        job = next((item for item in self.jobs if item.job_id == job_id), None)
        if job is None:
            return
        message = f"Xóa job {job_id} khỏi lịch sử local?"
        if job.status == "RUNNING":
            message = f"Job {job_id} đang chạy. Hệ thống sẽ hủy job trước khi xóa. Tiếp tục?"
        if messagebox.askyesno("Xóa job", message):
            if self.on_delete_job is not None:
                self.on_delete_job(job_id, job.status)
            self.jobs = [item for item in self.jobs if item.job_id != job_id]
            self._refresh_table()

    def _mock_action(self) -> None:
        return

    def _action_button(self, master: ctk.CTkBaseClass, text: str, command: Callable[[], None], width: int, state: str = "normal", danger: bool = False) -> ctk.CTkButton:
        return ctk.CTkButton(master, text=text, width=width, height=30, corner_radius=tokens.RADIUS_SM, fg_color=tokens.COLOR_SURFACE, hover_color="#FEE2E2" if danger else tokens.COLOR_BACKGROUND, border_width=tokens.BORDER_WIDTH, border_color=tokens.COLOR_ERROR if danger else tokens.COLOR_BORDER, text_color=tokens.COLOR_ERROR if danger else tokens.COLOR_TEXT, font=tokens.FONT_SMALL, command=command, state=state)

    def _create_card(self, master: ctk.CTkBaseClass) -> ctk.CTkFrame:
        return ctk.CTkFrame(master, fg_color=tokens.COLOR_SURFACE, corner_radius=tokens.RADIUS_LG, border_width=tokens.BORDER_WIDTH, border_color=tokens.COLOR_BORDER)

    def _status_code(self, label: str) -> str:
        reverse = {value: key for key, value in STATUS_TEXT.items()}
        return reverse.get(label, "ALL")

    def _format_created(self, timestamp: str) -> str:
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return timestamp

    def _duration_text(self, job_state: JobState) -> str:
        try:
            created = datetime.fromisoformat(job_state.created_at.replace("Z", "+00:00"))
            updated = datetime.fromisoformat(job_state.updated_at.replace("Z", "+00:00"))
            seconds = max(0, int((updated - created).total_seconds()))
            return f"{seconds // 60:02d}:{seconds % 60:02d}"
        except ValueError:
            return "-"

    def on_show(self) -> None:
        """Lifecycle hook để NavigationController gọi khi screen được hiển thị."""
        self._refresh_table()
