"""Màn hình Tạo video cho luồng nhập PDF và kiểm tra readiness."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from app.ui import tokens

if not hasattr(ctk, "filedialog"):
    ctk.filedialog = filedialog

MONTH_PATTERN = re.compile(r"^20\d{2}(0[1-9]|1[0-2])$")


class CreateVideoScreen(ctk.CTkFrame):
    """Form tạo video gồm input package, readiness checklist và job summary."""

    def __init__(self, master: ctk.CTkBaseClass, on_view_job_details: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color=tokens.COLOR_BACKGROUND, corner_radius=0)

        self.on_view_job_details = on_view_job_details
        self.selected_pdf_path: Path | None = None
        self.output_root = Path("outputs")
        self.readiness_state: dict[str, bool | None] = {
            "pdf_valid": None,
            "month_valid": None,
            "template_valid": None,
            "llm_ready": None,
            "tts_ready": None,
            "output_writable": None,
        }
        self.readiness_widgets: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}

        self.grid_columnconfigure(0, weight=5, uniform="create_video_columns")
        self.grid_columnconfigure(1, weight=7, uniform="create_video_columns")
        self.grid_rowconfigure(0, weight=1)

        self._build_input_card()
        self._build_right_panel()
        self.check_start_enabled()

    def _build_input_card(self) -> None:
        self.input_card = self._create_card(self)
        self.input_card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(tokens.SPACING_XL, tokens.SPACING_MD),
            pady=tokens.SPACING_XL,
        )
        self.input_card.grid_columnconfigure(0, weight=1)
        self.input_card.grid_rowconfigure(9, weight=1)

        title = ctk.CTkLabel(
            self.input_card,
            text="Input package",
            font=tokens.FONT_HEADING_LARGE,
            text_color=tokens.COLOR_TEXT,
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_XL, tokens.SPACING_LG))

        self._build_pdf_picker(row=1)
        self.month_entry = self._build_entry_field(
            row=2,
            label="Tháng báo cáo (YYYYMM)",
            placeholder="202603",
            on_key_release=self._handle_month_changed,
        )
        self.month_error_label = ctk.CTkLabel(
            self.input_card,
            text="",
            font=tokens.FONT_SMALL,
            text_color=tokens.COLOR_ERROR,
            anchor="w",
        )
        self.month_error_label.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=tokens.SPACING_XL,
            pady=(0, tokens.SPACING_SM),
        )

        self.title_entry = self._build_entry_field(
            row=4,
            label="Tiêu đề",
            placeholder="Báo cáo giao ban tháng 03/2026",
            on_key_release=self.update_readiness,
        )
        self.org_entry = self._build_entry_field(
            row=5,
            label="Đơn vị",
            placeholder="BHXH ...",
            on_key_release=self.update_readiness,
        )
        self._build_template_field(row=6)
        self._build_output_field(row=7)
        self._build_profile_field(row=8)

        self.start_button = ctk.CTkButton(
            self.input_card,
            text="Start Job",
            height=46,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_CTA,
            hover_color=tokens.COLOR_WARNING,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY_BOLD,
            state="disabled",
            command=lambda: None,
        )
        self.start_button.grid(
            row=10,
            column=0,
            sticky="ew",
            padx=tokens.SPACING_XL,
            pady=(tokens.SPACING_LG, tokens.SPACING_XL),
        )

    def _build_pdf_picker(self, row: int) -> None:
        frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_LG))
        frame.grid_columnconfigure(1, weight=1)

        button = ctk.CTkButton(
            frame,
            text="Chọn PDF...",
            width=118,
            height=36,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_PRIMARY,
            hover_color=tokens.COLOR_PRIMARY_HOVER,
            text_color=tokens.COLOR_WHITE,
            font=tokens.FONT_BODY_BOLD,
            command=self.choose_pdf,
        )
        button.grid(row=0, column=0, sticky="w", padx=(0, tokens.SPACING_MD))

        self.pdf_status_label = ctk.CTkLabel(
            frame,
            text="Chưa chọn file PDF",
            font=tokens.FONT_BODY,
            text_color=tokens.COLOR_MUTED,
            anchor="w",
        )
        self.pdf_status_label.grid(row=0, column=1, sticky="ew")

    def _build_entry_field(
        self,
        row: int,
        label: str,
        placeholder: str,
        on_key_release: object | None = None,
    ) -> ctk.CTkEntry:
        frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))
        frame.grid_columnconfigure(0, weight=1)

        field_label = ctk.CTkLabel(
            frame,
            text=label,
            font=tokens.FONT_BODY_BOLD,
            text_color=tokens.COLOR_TEXT,
            anchor="w",
        )
        field_label.grid(row=0, column=0, sticky="ew", pady=(0, tokens.SPACING_XS))

        entry = ctk.CTkEntry(
            frame,
            height=36,
            corner_radius=tokens.RADIUS_MD,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            fg_color=tokens.COLOR_SURFACE,
            text_color=tokens.COLOR_TEXT,
            placeholder_text=placeholder,
            font=tokens.FONT_BODY,
        )
        entry.grid(row=1, column=0, sticky="ew")
        if on_key_release is not None:
            entry.bind("<KeyRelease>", lambda _event: on_key_release())
        return entry

    def _build_template_field(self, row: int) -> None:
        frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(frame, text="Workflow template", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w")
        label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, tokens.SPACING_XS))

        self.template_var = ctk.StringVar(value="workflow.md")
        entry = ctk.CTkEntry(
            frame,
            textvariable=self.template_var,
            height=36,
            corner_radius=tokens.RADIUS_MD,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            fg_color=tokens.COLOR_SURFACE,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            state="disabled",
        )
        entry.grid(row=1, column=0, sticky="ew", padx=(0, tokens.SPACING_SM))

        button = ctk.CTkButton(
            frame,
            text="Kiểm tra",
            width=96,
            height=36,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            hover_color=tokens.COLOR_BACKGROUND,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            command=self.update_readiness,
        )
        button.grid(row=1, column=1, sticky="e")

    def _build_output_field(self, row: int) -> None:
        frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(frame, text="Thư mục output", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w")
        label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, tokens.SPACING_XS))

        self.output_var = ctk.StringVar(value="outputs/")
        entry = ctk.CTkEntry(
            frame,
            textvariable=self.output_var,
            height=36,
            corner_radius=tokens.RADIUS_MD,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            fg_color=tokens.COLOR_SURFACE,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            state="disabled",
        )
        entry.grid(row=1, column=0, sticky="ew", padx=(0, tokens.SPACING_SM))

        button = ctk.CTkButton(
            frame,
            text="Chọn...",
            width=96,
            height=36,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            hover_color=tokens.COLOR_BACKGROUND,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            command=self.choose_output_folder,
        )
        button.grid(row=1, column=1, sticky="e")

    def _build_profile_field(self, row: int) -> None:
        frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(frame, text="Profile", font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w")
        label.grid(row=0, column=0, sticky="ew", pady=(0, tokens.SPACING_XS))

        self.profile_menu = ctk.CTkOptionMenu(
            frame,
            values=["default", "custom"],
            height=36,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            button_color=tokens.COLOR_PRIMARY,
            button_hover_color=tokens.COLOR_PRIMARY_HOVER,
            dropdown_fg_color=tokens.COLOR_SURFACE,
            dropdown_hover_color=tokens.COLOR_BACKGROUND,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            command=lambda _value: self.update_readiness(),
        )
        self.profile_menu.set("default")
        self.profile_menu.grid(row=1, column=0, sticky="ew")

    def _build_right_panel(self) -> None:
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(tokens.SPACING_MD, tokens.SPACING_XL),
            pady=tokens.SPACING_XL,
        )
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)

        self._build_readiness_card(right_panel)
        self._build_job_summary_card(right_panel)

    def _build_readiness_card(self, master: ctk.CTkFrame) -> None:
        card = self._create_card(master)
        card.grid(row=0, column=0, sticky="nsew", pady=(0, tokens.SPACING_MD))
        card.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(card, text="Readiness", font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT, anchor="w")
        title.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_XL, tokens.SPACING_MD))

        items = (
            ("pdf_valid", "PDF hợp lệ"),
            ("month_valid", "Tháng báo cáo hợp lệ"),
            ("template_valid", "Workflow template hợp lệ"),
            ("llm_ready", "LLM config ready"),
            ("tts_ready", "TTS config ready"),
            ("output_writable", "Output writable"),
        )
        for index, (key, text) in enumerate(items, start=1):
            row_frame = ctk.CTkFrame(card, fg_color="transparent")
            row_frame.grid(row=index, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_SM))
            row_frame.grid_columnconfigure(1, weight=1)

            indicator = ctk.CTkLabel(
                row_frame,
                text="-",
                width=28,
                height=28,
                corner_radius=999,
                fg_color=tokens.COLOR_NEUTRAL,
                text_color=tokens.COLOR_WHITE,
                font=tokens.FONT_BODY_BOLD,
            )
            indicator.grid(row=0, column=0, sticky="w", padx=(0, tokens.SPACING_SM))

            label = ctk.CTkLabel(row_frame, text=text, font=tokens.FONT_BODY, text_color=tokens.COLOR_MUTED, anchor="w")
            label.grid(row=0, column=1, sticky="ew")
            self.readiness_widgets[key] = (indicator, label)

        self.readiness_hint = ctk.CTkLabel(
            card,
            text="Cần PDF, tháng hợp lệ và tối thiểu 4/6 điều kiện pass để bật Start Job.",
            font=tokens.FONT_SMALL,
            text_color=tokens.COLOR_MUTED,
            anchor="w",
            wraplength=540,
        )
        self.readiness_hint.grid(row=7, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_SM, tokens.SPACING_XL))

    def _build_job_summary_card(self, master: ctk.CTkFrame) -> None:
        card = self._create_card(master)
        card.grid(row=1, column=0, sticky="nsew", pady=(tokens.SPACING_MD, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(card, text="Job hiện tại", font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT, anchor="w")
        title.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_XL, tokens.SPACING_MD))

        self.job_summary_label = ctk.CTkLabel(
            card,
            text="Chưa có job nào",
            font=tokens.FONT_BODY,
            text_color=tokens.COLOR_MUTED,
            anchor="nw",
            justify="left",
        )
        self.job_summary_label.grid(row=1, column=0, sticky="nsew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))

        details_button = ctk.CTkButton(
            card,
            text="Xem chi tiết",
            height=38,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            hover_color=tokens.COLOR_BACKGROUND,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            command=self._view_job_details,
        )
        details_button.grid(row=2, column=0, sticky="w", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_XL))

    def _create_card(self, master: ctk.CTkBaseClass) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            master,
            fg_color=tokens.COLOR_SURFACE,
            corner_radius=tokens.RADIUS_LG,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
        )

    def choose_pdf(self) -> None:
        file_path = ctk.filedialog.askopenfilename(
            title="Chọn file PDF báo cáo",
            filetypes=(("PDF files", "*.pdf"), ("All files", "*.*")),
        )
        if not file_path:
            return

        self.selected_pdf_path = Path(file_path)
        try:
            size_text = self._format_file_size(self.selected_pdf_path.stat().st_size)
        except OSError:
            size_text = "không rõ kích thước"
        self.pdf_status_label.configure(
            text=f"{self.selected_pdf_path.name} ({size_text})",
            text_color=tokens.COLOR_TEXT,
        )
        self.update_readiness()

    def choose_output_folder(self) -> None:
        folder_path = ctk.filedialog.askdirectory(title="Chọn thư mục output")
        if not folder_path:
            return

        self.output_root = Path(folder_path)
        self.output_var.set(str(self.output_root))
        self.update_readiness()

    def validate_month(self, text: str) -> bool:
        """Kiểm tra tháng báo cáo theo định dạng YYYYMM."""
        return bool(MONTH_PATTERN.fullmatch(text.strip()))

    def _handle_month_changed(self) -> None:
        month_text = self.month_entry.get().strip()
        if not month_text:
            self.month_error_label.configure(text="")
            self.month_entry.configure(border_color=tokens.COLOR_BORDER)
        elif self.validate_month(month_text):
            self.month_error_label.configure(text="")
            self.month_entry.configure(border_color=tokens.COLOR_SUCCESS)
        else:
            self.month_error_label.configure(text="Tháng báo cáo phải có dạng YYYYMM, ví dụ 202603.")
            self.month_entry.configure(border_color=tokens.COLOR_ERROR)
        self.update_readiness()

    def update_readiness(self) -> None:
        """Cập nhật readiness checklist từ trạng thái form hiện tại."""
        self.readiness_state["pdf_valid"] = self.selected_pdf_path is not None
        self.readiness_state["month_valid"] = self.validate_month(self.month_entry.get())
        self.readiness_state["template_valid"] = True
        self.readiness_state["output_writable"] = self._is_output_writable()

        for key, state in self.readiness_state.items():
            indicator, label = self.readiness_widgets[key]
            icon, color, text_color = self._readiness_style(state)
            indicator.configure(text=icon, fg_color=color)
            label.configure(text_color=text_color)

        self.check_start_enabled()

    def set_config_ready(self, llm_ready: bool, tts_ready: bool) -> None:
        """Nhận trạng thái cấu hình từ màn hình Cấu hình."""
        self.readiness_state["llm_ready"] = llm_ready
        self.readiness_state["tts_ready"] = tts_ready
        self.update_readiness()

    def check_start_enabled(self) -> None:
        """Bật Start Job khi các điều kiện frontend đủ pass."""
        passed_count = sum(1 for value in self.readiness_state.values() if value is True)
        is_ready = (
            self.selected_pdf_path is not None
            and self.validate_month(self.month_entry.get())
            and passed_count >= 4
        )
        self.start_button.configure(state="normal" if is_ready else "disabled")

    def _is_output_writable(self) -> bool:
        try:
            self.output_root.mkdir(parents=True, exist_ok=True)
            return os.access(self.output_root, os.W_OK)
        except OSError:
            return False

    def _readiness_style(self, state: bool | None) -> tuple[str, str, str]:
        if state is True:
            return "✓", tokens.COLOR_SUCCESS, tokens.COLOR_TEXT
        if state is False:
            return "✗", tokens.COLOR_ERROR, tokens.COLOR_TEXT
        return "-", tokens.COLOR_NEUTRAL, tokens.COLOR_MUTED

    def _view_job_details(self) -> None:
        if self.on_view_job_details is not None:
            self.on_view_job_details()

    def _format_file_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"

    def on_show(self) -> None:
        """Lifecycle hook để giữ tương thích với NavigationController."""
