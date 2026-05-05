"""Màn hình Cấu hình cho LLM, TTS, runtime policy và secure storage mock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import customtkinter as ctk

from app.ui import tokens

MODEL_CREDENTIAL_ID = "tao-video-bao-cao/model/default"
TTS_CREDENTIAL_ID = "tao-video-bao-cao/tts/default"


class ConfigScreen(ctk.CTkFrame):
    """Form cấu hình hệ thống với validation và mô phỏng lưu credential an toàn."""

    def __init__(self, master: ctk.CTkBaseClass, on_config_saved: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color=tokens.COLOR_BACKGROUND, corner_radius=0)
        self.on_config_saved = on_config_saved
        self.has_saved_keys = False
        self.model_key_visible = False
        self.tts_key_visible = False

        self.grid_columnconfigure(0, weight=7, uniform="config_columns")
        self.grid_columnconfigure(1, weight=3, uniform="config_columns")
        self.grid_rowconfigure(0, weight=1)

        self._build_main_form()
        self._build_health_card()
        self.reset_form()

    def _build_main_form(self) -> None:
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=tokens.COLOR_BORDER,
            scrollbar_button_hover_color=tokens.COLOR_NEUTRAL,
        )
        self.scroll_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(tokens.SPACING_XL, tokens.SPACING_MD),
            pady=tokens.SPACING_XL,
        )
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        self.llm_card = self._create_card(self.scroll_frame)
        self.llm_card.grid(row=0, column=0, sticky="ew", pady=(0, tokens.SPACING_LG))
        self.llm_card.grid_columnconfigure(0, weight=1)
        self._build_llm_card()

        self.tts_card = self._create_card(self.scroll_frame)
        self.tts_card.grid(row=1, column=0, sticky="ew", pady=(0, tokens.SPACING_LG))
        self.tts_card.grid_columnconfigure(0, weight=1)
        self._build_tts_card()

        self.runtime_card = self._create_card(self.scroll_frame)
        self.runtime_card.grid(row=2, column=0, sticky="ew", pady=(0, tokens.SPACING_LG))
        self.runtime_card.grid_columnconfigure(0, weight=1)
        self._build_runtime_card()

        self._build_buttons_row(row=3)

    def _build_llm_card(self) -> None:
        self._build_card_heading(self.llm_card, "LLM Model", row=0)
        self.url_model_entry, self.url_model_error = self._build_entry_field(
            self.llm_card,
            row=1,
            label="URL model",
            placeholder="https://api.openai.com/v1",
        )
        self.default_model_entry, self.default_model_error = self._build_entry_field(
            self.llm_card,
            row=2,
            label="Default model",
            placeholder="gpt-4-turbo",
        )
        self.apikey_model_entry, self.apikey_model_error = self._build_key_field(
            self.llm_card,
            row=3,
            label="API key model",
            toggle_command=self.toggle_model_key,
        )
        self.credential_id_model_entry, _ = self._build_entry_field(
            self.llm_card,
            row=4,
            label="Credential ID model",
            placeholder="Chưa lưu",
            readonly=True,
        )
        self.test_llm_button = self._build_secondary_button(self.llm_card, text="Test LLM", command=self.test_llm)
        self.test_llm_button.grid(row=5, column=0, sticky="w", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_XL))

    def _build_tts_card(self) -> None:
        self._build_card_heading(self.tts_card, "TTS Voice", row=0)
        self.url_tts_entry, self.url_tts_error = self._build_entry_field(
            self.tts_card,
            row=1,
            label="URL TTS",
            placeholder="https://api.tts-service.com",
        )
        self.model_tts_entry, self.model_tts_error = self._build_entry_field(
            self.tts_card,
            row=2,
            label="Model TTS",
            placeholder="tts-1",
        )
        self.apikey_tts_entry, self.apikey_tts_error = self._build_key_field(
            self.tts_card,
            row=3,
            label="API key TTS",
            toggle_command=self.toggle_tts_key,
        )
        self.voice_entry, _ = self._build_entry_field(
            self.tts_card,
            row=4,
            label="Voice (optional)",
            placeholder="vi-VN-NamMinhNeural",
        )
        self.credential_id_tts_entry, _ = self._build_entry_field(
            self.tts_card,
            row=5,
            label="Credential ID TTS",
            placeholder="Chưa lưu",
            readonly=True,
        )
        self.test_tts_button = self._build_secondary_button(self.tts_card, text="Test TTS", command=self.test_tts)
        self.test_tts_button.grid(row=6, column=0, sticky="w", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_XL))

    def _build_runtime_card(self) -> None:
        self._build_card_heading(self.runtime_card, "Runtime Policy", row=0)
        self.step_timeout_seconds_entry, self.step_timeout_seconds_error = self._build_entry_field(
            self.runtime_card,
            row=1,
            label="Step timeout seconds",
            placeholder="600",
        )
        self.max_retry_entry, self.max_retry_error = self._build_entry_field(
            self.runtime_card,
            row=2,
            label="Max retry",
            placeholder="3",
        )
        self.retry_backoff_seconds_entry, self.retry_backoff_seconds_error = self._build_entry_field(
            self.runtime_card,
            row=3,
            label="Retry backoff seconds",
            placeholder="30",
        )

        checkbox_frame = ctk.CTkFrame(self.runtime_card, fg_color="transparent")
        checkbox_frame.grid(row=4, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_XL))
        checkbox_frame.grid_columnconfigure(0, weight=1)

        self.enable_resume_var = ctk.BooleanVar(value=True)
        self.enable_resume_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text="Enable resume",
            variable=self.enable_resume_var,
            fg_color=tokens.COLOR_PRIMARY,
            hover_color=tokens.COLOR_PRIMARY_HOVER,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
        )
        self.enable_resume_checkbox.grid(row=0, column=0, sticky="w", pady=(0, tokens.SPACING_SM))

        self.mock_ai_mode_var = ctk.BooleanVar(value=False)
        self.mock_ai_mode_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text="Mock AI mode",
            variable=self.mock_ai_mode_var,
            fg_color=tokens.COLOR_PRIMARY,
            hover_color=tokens.COLOR_PRIMARY_HOVER,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
        )
        self.mock_ai_mode_checkbox.grid(row=1, column=0, sticky="w")

    def _build_health_card(self) -> None:
        self.health_card = self._create_card(self)
        self.health_card.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(tokens.SPACING_MD, tokens.SPACING_XL),
            pady=tokens.SPACING_XL,
        )
        self.health_card.grid_columnconfigure(0, weight=1)

        self._build_card_heading(self.health_card, "Config health", row=0)
        self.last_test_time_value = self._build_status_row(self.health_card, row=1, label="Last test time", value="Chưa test")
        self.llm_result_value = self._build_status_row(self.health_card, row=2, label="LLM result", value="Unknown")
        self.tts_result_value = self._build_status_row(self.health_card, row=3, label="TTS result", value="Unknown")
        self.secret_storage_value = self._build_status_row(
            self.health_card,
            row=4,
            label="Secret storage mode",
            value="Windows Credential Manager (chưa xác minh)",
            wraplength=260,
        )
        self.save_status_value = ctk.CTkLabel(
            self.health_card,
            text="Chưa lưu cấu hình",
            font=tokens.FONT_BODY_BOLD,
            text_color=tokens.COLOR_MUTED,
            anchor="w",
            justify="left",
            wraplength=260,
        )
        self.save_status_value.grid(row=5, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_LG, tokens.SPACING_XL))

    def _build_buttons_row(self, row: int) -> None:
        buttons_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        buttons_frame.grid(row=row, column=0, sticky="ew", pady=(0, tokens.SPACING_XL))
        buttons_frame.grid_columnconfigure(0, weight=1)

        self.save_button = ctk.CTkButton(
            buttons_frame,
            text="Lưu cấu hình",
            height=42,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_CTA,
            hover_color=tokens.COLOR_WARNING,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY_BOLD,
            command=self.save_config,
        )
        self.save_button.grid(row=0, column=0, sticky="w", padx=(0, tokens.SPACING_SM))

        self.reset_button = self._build_secondary_button(buttons_frame, text="Reset", command=self.reset_form)
        self.reset_button.grid(row=0, column=1, sticky="w", padx=(0, tokens.SPACING_SM))

        self.change_key_button = self._build_secondary_button(buttons_frame, text="Thay key", command=self.enable_key_change)
        self.change_key_button.grid(row=0, column=2, sticky="w", padx=(0, tokens.SPACING_SM))

        self.delete_key_button = ctk.CTkButton(
            buttons_frame,
            text="Xóa key",
            height=42,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            hover_color="#FEE2E2",
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_ERROR,
            text_color=tokens.COLOR_ERROR,
            font=tokens.FONT_BODY,
            command=self.delete_keys,
        )
        self.delete_key_button.grid(row=0, column=3, sticky="w")
        self._sync_key_buttons()

    def _build_card_heading(self, master: ctk.CTkFrame, text: str, row: int) -> None:
        label = ctk.CTkLabel(master, text=text, font=tokens.FONT_HEADING_LARGE, text_color=tokens.COLOR_TEXT, anchor="w")
        label.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(tokens.SPACING_XL, tokens.SPACING_LG))

    def _build_entry_field(
        self,
        master: ctk.CTkFrame,
        row: int,
        label: str,
        placeholder: str,
        readonly: bool = False,
    ) -> tuple[ctk.CTkEntry, ctk.CTkLabel]:
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))
        frame.grid_columnconfigure(0, weight=1)

        field_label = ctk.CTkLabel(frame, text=label, font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w")
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
            state="readonly" if readonly else "normal",
        )
        entry.grid(row=1, column=0, sticky="ew")

        error_label = ctk.CTkLabel(frame, text="", font=tokens.FONT_SMALL, text_color=tokens.COLOR_ERROR, anchor="w")
        error_label.grid(row=2, column=0, sticky="ew", pady=(tokens.SPACING_XS, 0))
        return entry, error_label

    def _build_key_field(
        self,
        master: ctk.CTkFrame,
        row: int,
        label: str,
        toggle_command: Callable[[], None],
    ) -> tuple[ctk.CTkEntry, ctk.CTkLabel]:
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))
        frame.grid_columnconfigure(0, weight=1)

        field_label = ctk.CTkLabel(frame, text=label, font=tokens.FONT_BODY_BOLD, text_color=tokens.COLOR_TEXT, anchor="w")
        field_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, tokens.SPACING_XS))

        entry = ctk.CTkEntry(
            frame,
            height=36,
            corner_radius=tokens.RADIUS_MD,
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            fg_color=tokens.COLOR_SURFACE,
            text_color=tokens.COLOR_TEXT,
            placeholder_text="Nhập API key",
            font=tokens.FONT_BODY,
            show="*",
        )
        entry.grid(row=1, column=0, sticky="ew", padx=(0, tokens.SPACING_SM))

        toggle_button = self._build_secondary_button(frame, text="Hiện", command=toggle_command, width=72, height=36)
        toggle_button.grid(row=1, column=1, sticky="e")
        if "model" in label.lower():
            self.toggle_model_key_button = toggle_button
        else:
            self.toggle_tts_key_button = toggle_button

        error_label = ctk.CTkLabel(frame, text="", font=tokens.FONT_SMALL, text_color=tokens.COLOR_ERROR, anchor="w")
        error_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(tokens.SPACING_XS, 0))
        return entry, error_label

    def _build_status_row(self, master: ctk.CTkFrame, row: int, label: str, value: str, wraplength: int = 240) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, tokens.SPACING_MD))
        frame.grid_columnconfigure(0, weight=1)

        label_widget = ctk.CTkLabel(frame, text=label, font=tokens.FONT_SMALL, text_color=tokens.COLOR_MUTED, anchor="w")
        label_widget.grid(row=0, column=0, sticky="ew")

        value_widget = ctk.CTkLabel(
            frame,
            text=value,
            font=tokens.FONT_BODY_BOLD,
            text_color=tokens.COLOR_TEXT,
            anchor="w",
            justify="left",
            wraplength=wraplength,
        )
        value_widget.grid(row=1, column=0, sticky="ew")
        return value_widget

    def _build_secondary_button(
        self,
        master: ctk.CTkBaseClass,
        text: str,
        command: Callable[[], None],
        width: int = 120,
        height: int = 42,
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

    def toggle_model_key(self) -> None:
        self.model_key_visible = not self.model_key_visible
        self.apikey_model_entry.configure(show="" if self.model_key_visible else "*")
        self.toggle_model_key_button.configure(text="Ẩn" if self.model_key_visible else "Hiện")

    def toggle_tts_key(self) -> None:
        self.tts_key_visible = not self.tts_key_visible
        self.apikey_tts_entry.configure(show="" if self.tts_key_visible else "*")
        self.toggle_tts_key_button.configure(text="Ẩn" if self.tts_key_visible else "Hiện")

    def validate_config(self) -> bool:
        valid = True
        valid &= self._validate_url(self.url_model_entry, self.url_model_error)
        valid &= self._validate_url(self.url_tts_entry, self.url_tts_error)
        valid &= self._validate_required(self.default_model_entry, self.default_model_error, "Default model không được rỗng.")
        valid &= self._validate_required(self.model_tts_entry, self.model_tts_error, "Model TTS không được rỗng.")
        return bool(valid)

    def _validate_url(self, entry: ctk.CTkEntry, error_label: ctk.CTkLabel) -> bool:
        value = entry.get().strip()
        if value.startswith(("http://", "https://")):
            entry.configure(border_color=tokens.COLOR_SUCCESS)
            error_label.configure(text="")
            return True
        entry.configure(border_color=tokens.COLOR_ERROR)
        error_label.configure(text="URL phải bắt đầu bằng http:// hoặc https://.")
        return False

    def _validate_required(self, entry: ctk.CTkEntry, error_label: ctk.CTkLabel, message: str) -> bool:
        if entry.get().strip():
            entry.configure(border_color=tokens.COLOR_SUCCESS)
            error_label.configure(text="")
            return True
        entry.configure(border_color=tokens.COLOR_ERROR)
        error_label.configure(text=message)
        return False

    def save_config(self) -> None:
        if not self.validate_config():
            self.save_status_value.configure(text="Cấu hình chưa hợp lệ", text_color=tokens.COLOR_ERROR)
            return

        self._set_readonly_value(self.credential_id_model_entry, MODEL_CREDENTIAL_ID)
        self._set_readonly_value(self.credential_id_tts_entry, TTS_CREDENTIAL_ID)
        self._clear_entry(self.apikey_model_entry)
        self._clear_entry(self.apikey_tts_entry)
        self.apikey_model_entry.configure(placeholder_text="Đã lưu trong secure storage", show="*")
        self.apikey_tts_entry.configure(placeholder_text="Đã lưu trong secure storage", show="*")
        self.model_key_visible = False
        self.tts_key_visible = False
        self.toggle_model_key_button.configure(text="Hiện")
        self.toggle_tts_key_button.configure(text="Hiện")
        self.has_saved_keys = True
        self.save_status_value.configure(text="Đã lưu thành cấu hình", text_color=tokens.COLOR_SUCCESS)
        self.secret_storage_value.configure(text="Windows Credential Manager (mock secure storage)")
        self._sync_key_buttons()

        if self.on_config_saved is not None:
            self.on_config_saved()

    def reset_form(self) -> None:
        self._set_entry_value(self.url_model_entry, "")
        self._set_entry_value(self.default_model_entry, "")
        self._set_entry_value(self.url_tts_entry, "")
        self._set_entry_value(self.model_tts_entry, "")
        self._set_entry_value(self.voice_entry, "")
        self._set_entry_value(self.step_timeout_seconds_entry, "600")
        self._set_entry_value(self.max_retry_entry, "3")
        self._set_entry_value(self.retry_backoff_seconds_entry, "30")
        self._clear_entry(self.apikey_model_entry)
        self._clear_entry(self.apikey_tts_entry)
        self._set_readonly_value(self.credential_id_model_entry, "")
        self._set_readonly_value(self.credential_id_tts_entry, "")
        self.enable_resume_var.set(True)
        self.mock_ai_mode_var.set(False)
        self.has_saved_keys = False
        self.model_key_visible = False
        self.tts_key_visible = False
        self.apikey_model_entry.configure(show="*", placeholder_text="Nhập API key")
        self.apikey_tts_entry.configure(show="*", placeholder_text="Nhập API key")
        self.toggle_model_key_button.configure(text="Hiện")
        self.toggle_tts_key_button.configure(text="Hiện")
        self.last_test_time_value.configure(text="Chưa test")
        self.llm_result_value.configure(text="Unknown", text_color=tokens.COLOR_TEXT)
        self.tts_result_value.configure(text="Unknown", text_color=tokens.COLOR_TEXT)
        self.secret_storage_value.configure(text="Windows Credential Manager (chưa xác minh)")
        self.save_status_value.configure(text="Chưa lưu cấu hình", text_color=tokens.COLOR_MUTED)
        self._clear_validation_state()
        self._sync_key_buttons()

    def test_llm(self) -> None:
        self.llm_result_value.configure(text="Đang kiểm tra...", text_color=tokens.COLOR_WARNING)
        self.test_llm_button.configure(state="disabled")
        self.after(1000, self._finish_llm_test)

    def test_tts(self) -> None:
        self.tts_result_value.configure(text="Đang kiểm tra...", text_color=tokens.COLOR_WARNING)
        self.test_tts_button.configure(state="disabled")
        self.after(1000, self._finish_tts_test)

    def _finish_llm_test(self) -> None:
        self.llm_result_value.configure(text="Mock test: OK", text_color=tokens.COLOR_SUCCESS)
        self.last_test_time_value.configure(text=self._now_text())
        self.test_llm_button.configure(state="normal")

    def _finish_tts_test(self) -> None:
        self.tts_result_value.configure(text="Mock test: OK", text_color=tokens.COLOR_SUCCESS)
        self.last_test_time_value.configure(text=self._now_text())
        self.test_tts_button.configure(state="normal")

    def enable_key_change(self) -> None:
        self._clear_entry(self.apikey_model_entry)
        self._clear_entry(self.apikey_tts_entry)
        self.apikey_model_entry.configure(placeholder_text="Nhập API key mới")
        self.apikey_tts_entry.configure(placeholder_text="Nhập API key mới")
        self.save_status_value.configure(text="Sẵn sàng thay key", text_color=tokens.COLOR_WARNING)

    def delete_keys(self) -> None:
        self._set_readonly_value(self.credential_id_model_entry, "")
        self._set_readonly_value(self.credential_id_tts_entry, "")
        self._clear_entry(self.apikey_model_entry)
        self._clear_entry(self.apikey_tts_entry)
        self.has_saved_keys = False
        self.save_status_value.configure(text="Đã xóa key mock", text_color=tokens.COLOR_WARNING)
        self._sync_key_buttons()

    def _sync_key_buttons(self) -> None:
        if hasattr(self, "change_key_button"):
            state = "normal" if self.has_saved_keys else "disabled"
            self.change_key_button.configure(state=state)
            self.delete_key_button.configure(state=state)

    def _clear_validation_state(self) -> None:
        for entry in (
            self.url_model_entry,
            self.default_model_entry,
            self.url_tts_entry,
            self.model_tts_entry,
            self.step_timeout_seconds_entry,
            self.max_retry_entry,
            self.retry_backoff_seconds_entry,
        ):
            entry.configure(border_color=tokens.COLOR_BORDER)
        for error_label in (
            self.url_model_error,
            self.default_model_error,
            self.apikey_model_error,
            self.url_tts_error,
            self.model_tts_error,
            self.apikey_tts_error,
            self.step_timeout_seconds_error,
            self.max_retry_error,
            self.retry_backoff_seconds_error,
        ):
            error_label.configure(text="")

    def _set_entry_value(self, entry: ctk.CTkEntry, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        if value:
            entry.insert(0, value)

    def _set_readonly_value(self, entry: ctk.CTkEntry, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        if value:
            entry.insert(0, value)
        entry.configure(state="readonly")

    def _clear_entry(self, entry: ctk.CTkEntry) -> None:
        entry.delete(0, "end")

    def _now_text(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def on_show(self) -> None:
        """Lifecycle hook để giữ tương thích với NavigationController."""
