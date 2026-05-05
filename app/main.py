"""Entrypoint cho ứng dụng Báo Cáo Giao Ban - Video Generator."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk

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


class App(ctk.CTk):
    """App shell chính gồm sidebar, topbar và content area."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(tokens.WINDOW_SIZE)
        self.minsize(tokens.WINDOW_MIN_WIDTH, tokens.WINDOW_MIN_HEIGHT)
        self.configure(fg_color=tokens.COLOR_BACKGROUND)

        self.grid_columnconfigure(0, minsize=tokens.SIDEBAR_WIDTH, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, minsize=tokens.TOPBAR_HEIGHT, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self.sidebar = SidebarFrame(self, on_nav_change=self.show_screen)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")

        self.topbar = TopBarFrame(
            self,
            title=SCREEN_TITLES["create_video"],
            status="Idle",
            on_open_outputs=self.open_outputs,
            on_open_config=lambda: self.show_screen("config"),
        )
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
        self.create_video_screen = CreateVideoScreen(self.content, on_view_job_details=self._show_job_logs_from_create)
        self.config_screen = ConfigScreen(self.content, on_config_saved=self._handle_config_saved)
        self.job_logs_screen = JobLogsScreen(self.content, on_open_output=self.open_outputs)
        self.history_screen = HistoryScreen(self.content, on_view_details=self._show_job_logs_from_history)
        self.navigation.register("create_video", self.create_video_screen)
        self.navigation.register("config", self.config_screen)
        self.navigation.register("job_logs", self.job_logs_screen)
        self.navigation.register("history", self.history_screen)

    def show_screen(self, screen_name: str) -> None:
        """Chuyển sang screen tương ứng từ sidebar/topbar."""
        self.navigation.show(screen_name)

    def _show_job_logs_from_create(self) -> None:
        self.show_screen("job_logs")

    def _show_job_logs_from_history(self, _job_id: str) -> None:
        self.show_screen("job_logs")

    def _handle_config_saved(self) -> None:
        self.create_video_screen.set_config_ready(llm_ready=True, tts_ready=True)

    def _handle_screen_changed(self, screen_name: str) -> None:
        self.sidebar.set_active(screen_name)
        self.topbar.set_title(SCREEN_TITLES.get(screen_name, screen_name))

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
