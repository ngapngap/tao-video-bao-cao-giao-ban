"""Screens package cho các màn hình chính của ứng dụng."""

from __future__ import annotations

from app.ui.screens.config_screen import ConfigScreen
from app.ui.screens.create_video_screen import CreateVideoScreen
from app.ui.screens.history_screen import HistoryScreen
from app.ui.screens.job_logs_screen import JobLogsScreen

__all__ = ["ConfigScreen", "CreateVideoScreen", "HistoryScreen", "JobLogsScreen"]
