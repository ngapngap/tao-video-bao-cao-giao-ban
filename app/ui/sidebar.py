"""Sidebar navigation cho app shell."""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.ui import tokens


class SidebarFrame(ctk.CTkFrame):
    """Sidebar trái chứa điều hướng chính và trạng thái cấu hình."""

    NAV_ITEMS: tuple[tuple[str, str], ...] = (
        ("create_video", "Tạo video"),
        ("config", "Cấu hình"),
        ("job_logs", "Job & Logs"),
        ("history", "Lịch sử"),
    )

    STATUS_COLORS: dict[str, str] = {
        "Not ready": tokens.COLOR_WARNING,
        "Ready": tokens.COLOR_SUCCESS,
        "Error": tokens.COLOR_ERROR,
    }

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        on_nav_change: Callable[[str], None],
        active_screen: str = "create_video",
        config_status: str = "Not ready",
    ) -> None:
        super().__init__(
            master,
            width=tokens.SIDEBAR_WIDTH,
            fg_color=tokens.COLOR_PRIMARY,
            corner_radius=0,
        )
        self.grid_propagate(False)
        self.pack_propagate(False)

        self._on_nav_change = on_nav_change
        self._active_screen = active_screen
        self._nav_buttons: dict[str, ctk.CTkButton] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_brand()
        self._build_nav_buttons()
        self._build_config_status(config_status)
        self.set_active(active_screen)

    def _build_brand(self) -> None:
        brand = ctk.CTkLabel(
            self,
            text="Báo Cáo\nGiao Ban",
            font=("Cascadia Mono", 18, "bold"),
            text_color=tokens.COLOR_WHITE,
            justify="left",
            anchor="w",
        )
        brand.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(24, 8))

        subtitle = ctk.CTkLabel(
            self,
            text="Video Generator",
            font=tokens.FONT_SMALL,
            text_color="#BFDBFE",
            anchor="w",
        )
        subtitle.grid(row=1, column=0, sticky="ew", padx=tokens.SPACING_XL, pady=(0, 18))

    def _build_nav_buttons(self) -> None:
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.grid(row=2, column=0, sticky="new", padx=tokens.SPACING_MD, pady=(0, tokens.SPACING_MD))
        nav_frame.grid_columnconfigure(0, weight=1)

        for row_index, (screen_name, label) in enumerate(self.NAV_ITEMS):
            button = ctk.CTkButton(
                nav_frame,
                text=label,
                height=42,
                corner_radius=tokens.RADIUS_MD,
                anchor="w",
                font=tokens.FONT_BODY_BOLD,
                text_color=tokens.COLOR_WHITE,
                fg_color="transparent",
                hover_color=tokens.COLOR_PRIMARY_HOVER,
                command=lambda name=screen_name: self._handle_nav_click(name),
            )
            button.grid(row=row_index, column=0, sticky="ew", pady=(0, tokens.SPACING_SM))
            self._nav_buttons[screen_name] = button

    def _build_config_status(self, config_status: str) -> None:
        status_frame = ctk.CTkFrame(
            self,
            fg_color=tokens.COLOR_PRIMARY_DARK,
            corner_radius=tokens.RADIUS_LG,
        )
        status_frame.grid(
            row=3,
            column=0,
            sticky="sew",
            padx=tokens.SPACING_MD,
            pady=(tokens.SPACING_MD, tokens.SPACING_LG),
        )
        status_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            status_frame,
            text="Config status",
            font=tokens.FONT_SMALL,
            text_color="#BFDBFE",
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="ew", padx=tokens.SPACING_MD, pady=(tokens.SPACING_MD, 2))

        self._config_status_label = ctk.CTkLabel(
            status_frame,
            text=config_status,
            font=tokens.FONT_BODY_BOLD,
            text_color=self.STATUS_COLORS.get(config_status, tokens.COLOR_WARNING),
            anchor="w",
        )
        self._config_status_label.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=tokens.SPACING_MD,
            pady=(0, tokens.SPACING_MD),
        )

    def _handle_nav_click(self, screen_name: str) -> None:
        self.set_active(screen_name)
        self._on_nav_change(screen_name)

    def set_active(self, screen_name: str) -> None:
        """Cập nhật active state cho nav button."""
        self._active_screen = screen_name
        for name, button in self._nav_buttons.items():
            if name == screen_name:
                button.configure(fg_color=tokens.COLOR_PRIMARY_ACTIVE, hover_color=tokens.COLOR_SECONDARY)
            else:
                button.configure(fg_color="transparent", hover_color=tokens.COLOR_PRIMARY_HOVER)

    def set_config_status(self, status: str) -> None:
        """Cập nhật trạng thái cấu hình ở cuối sidebar."""
        self._config_status_label.configure(
            text=status,
            text_color=self.STATUS_COLORS.get(status, tokens.COLOR_WARNING),
        )
