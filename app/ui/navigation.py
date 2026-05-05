"""Điều phối chuyển màn hình cho CustomTkinter app shell."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import customtkinter as ctk


class ShowableScreen(Protocol):
    """Protocol cho screen có lifecycle callback khi được hiển thị."""

    def on_show(self) -> None:
        """Được gọi sau khi screen được raise."""


class NavigationController:
    """Quản lý screen state và chuyển màn hình bằng tkraise."""

    def __init__(self, container: ctk.CTkFrame) -> None:
        self.container = container
        self.current_screen: str | None = None
        self._screens: dict[str, ctk.CTkFrame] = {}
        self._callbacks: list[Callable[[str], None]] = []

    def register(self, screen_name: str, frame: ctk.CTkFrame) -> None:
        """Đăng ký screen frame, giữ nguyên instance để không mất state khi switch."""
        self._screens[screen_name] = frame
        frame.grid(row=0, column=0, sticky="nsew")

    def add_change_listener(self, callback: Callable[[str], None]) -> None:
        """Thêm listener được gọi sau khi screen thay đổi."""
        self._callbacks.append(callback)

    def show(self, screen_name: str) -> None:
        """Hiển thị screen đã đăng ký bằng tkraise và gọi on_show nếu có."""
        if screen_name not in self._screens:
            raise KeyError(f"Screen '{screen_name}' is not registered")

        frame = self._screens[screen_name]
        frame.tkraise()
        self.current_screen = screen_name

        on_show = getattr(frame, "on_show", None)
        if callable(on_show):
            on_show()

        for callback in self._callbacks:
            callback(screen_name)
