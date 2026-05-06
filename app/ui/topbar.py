"""Top bar cho app shell."""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.ui import tokens


class TopBarFrame(ctk.CTkFrame):
    """Thanh header trên cùng hiển thị tiêu đề, trạng thái và quick actions."""

    STATUS_COLORS: dict[str, str] = {
        "Sẵn sàng": tokens.COLOR_STATUS_IDLE,
        "Đang chạy": tokens.COLOR_STATUS_RUNNING,
        "Thất bại": tokens.COLOR_STATUS_FAILED,
        "Hoàn thành": tokens.COLOR_STATUS_DONE,
        "Đã hủy": tokens.COLOR_NEUTRAL,
    }

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        title: str,
        status: str = "Sẵn sàng",
        on_open_outputs: Callable[[], None] | None = None,
        on_open_config: Callable[[], None] | None = None,
        on_check_update: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            master,
            height=tokens.TOPBAR_HEIGHT,
            fg_color=tokens.COLOR_SURFACE,
            corner_radius=0,
            border_width=0,
        )
        self.grid_propagate(False)
        self.pack_propagate(False)

        self._on_open_outputs = on_open_outputs or (lambda: None)
        self._on_open_config = on_open_config or (lambda: None)
        self._on_check_update = on_check_update or (lambda: None)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        self._title_label = ctk.CTkLabel(
            self,
            text=title,
            font=tokens.FONT_HEADING_LARGE,
            text_color=tokens.COLOR_TEXT,
            anchor="w",
        )
        self._title_label.grid(row=0, column=0, sticky="w", padx=tokens.SPACING_XL, pady=0)

        divider = ctk.CTkFrame(self, height=tokens.BORDER_WIDTH, fg_color=tokens.COLOR_BORDER, corner_radius=0)
        divider.grid(row=1, column=0, columnspan=2, sticky="ew")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=tokens.SPACING_XL, pady=0)

        self._status_pill = ctk.CTkLabel(
            actions,
            text=status,
            height=28,
            width=96,
            corner_radius=999,
            fg_color=self.STATUS_COLORS.get(status, tokens.COLOR_NEUTRAL),
            text_color=tokens.COLOR_WHITE,
            font=tokens.FONT_SMALL,
        )
        self._status_pill.grid(row=0, column=0, padx=(0, tokens.SPACING_SM))

        self._open_outputs_button = ctk.CTkButton(
            actions,
            text="Mở outputs",
            width=108,
            height=34,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            hover_color="#EFF6FF",
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            command=self._on_open_outputs,
        )
        self._open_outputs_button.grid(row=0, column=1, padx=(0, tokens.SPACING_SM))

        self._check_update_button = ctk.CTkButton(
            actions,
            text="Kiểm tra cập nhật",
            width=146,
            height=34,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_SURFACE,
            hover_color="#EFF6FF",
            border_width=tokens.BORDER_WIDTH,
            border_color=tokens.COLOR_BORDER,
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY,
            command=self._on_check_update,
        )
        self._check_update_button.grid(row=0, column=2, padx=(0, tokens.SPACING_SM))

        self._config_button = ctk.CTkButton(
            actions,
            text="Cấu hình",
            width=96,
            height=34,
            corner_radius=tokens.RADIUS_MD,
            fg_color=tokens.COLOR_CTA,
            hover_color="#FBBF24",
            text_color=tokens.COLOR_TEXT,
            font=tokens.FONT_BODY_BOLD,
            command=self._on_open_config,
        )
        self._config_button.grid(row=0, column=3)

    def set_title(self, title: str) -> None:
        """Cập nhật tiêu đề màn hình hiện tại."""
        self._title_label.configure(text=title)

    def set_status(self, status: str) -> None:
        """Cập nhật status pill toàn cục."""
        self._status_pill.configure(
            text=status,
            fg_color=self.STATUS_COLORS.get(status, tokens.COLOR_NEUTRAL),
        )
