"""Auto updater tải bản phát hành mới từ GitHub Releases."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from packaging.version import InvalidVersion, Version

from app.version import VERSION_URL, __version__


class Updater:
    """Kiểm tra và tự cập nhật app từ GitHub Releases."""

    def __init__(self, current_version: str = __version__) -> None:
        self.current_version = current_version

    def check_for_update(self) -> dict | None:
        """Kiểm tra có version mới không. Trả None nếu đã latest hoặc không kiểm tra được."""
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(
                    VERSION_URL,
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "tao-video-bao-cao-giao-ban",
                    },
                )
                if resp.status_code != 200:
                    return None

                release = resp.json()
                remote_tag = str(release.get("tag_name", "")).lstrip("v")
                if not remote_tag:
                    return None

                if Version(remote_tag) > Version(self.current_version):
                    return {
                        "version": remote_tag,
                        "tag_name": release.get("tag_name"),
                        "name": release.get("name", ""),
                        "body": release.get("body", ""),
                        "html_url": release.get("html_url", ""),
                        "assets": [
                            {
                                "name": a.get("name"),
                                "size": a.get("size"),
                                "browser_download_url": a.get("browser_download_url"),
                            }
                            for a in release.get("assets", [])
                        ],
                    }
                return None
        except (httpx.HTTPError, InvalidVersion, ValueError, KeyError):
            return None
        except Exception:
            return None

    def download_and_replace(self, asset_url: str, asset_name: str) -> bool:
        """Tải file mới và tạo script thay thế app hiện tại sau khi app thoát."""
        try:
            if not asset_url or not asset_name:
                return False

            temp_dir = tempfile.mkdtemp(prefix="bcgb_update_")
            temp_file = os.path.join(temp_dir, asset_name)

            with httpx.Client(timeout=300.0, follow_redirects=True) as client:
                with client.stream(
                    "GET",
                    asset_url,
                    headers={"User-Agent": "tao-video-bao-cao-giao-ban"},
                ) as resp:
                    resp.raise_for_status()
                    with open(temp_file, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

            if sys.platform == "win32":
                self._create_update_script_windows(temp_file)
            else:
                self._create_update_script_linux(temp_file)

            return True
        except Exception:
            return False

    def _current_executable(self) -> str:
        """Trả về đường dẫn executable hiện tại khi frozen, hoặc script entrypoint khi chạy source."""
        if getattr(sys, "frozen", False):
            return sys.executable
        return os.path.abspath(sys.argv[0])

    def _create_update_script_windows(self, new_file: str) -> None:
        """Tạo batch script cập nhật cho Windows."""
        current_exe = self._current_executable()
        script = f'''@echo off
echo Dang cap nhat...
timeout /t 2 /nobreak > nul
copy /Y "{new_file}" "{current_exe}"
if errorlevel 1 (
  echo Cap nhat that bai.
  pause
  exit /b 1
)
echo Cap nhat thanh cong!
start "" "{current_exe}"
del "%~f0"
'''
        script_path = os.path.join(os.path.dirname(current_exe), "_update.bat")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(["cmd", "/c", script_path], creationflags=creationflags)

    def _create_update_script_linux(self, new_file: str) -> None:
        """Tạo shell script cập nhật cho Linux/macOS."""
        current_exe = self._current_executable()
        script = f'''#!/bin/sh
echo "Dang cap nhat..."
sleep 2
cp -f "{new_file}" "{current_exe}"
chmod +x "{current_exe}"
echo "Cap nhat thanh cong!"
"{current_exe}" >/dev/null 2>&1 &
rm -- "$0"
'''
        script_path = os.path.join(tempfile.mkdtemp(prefix="bcgb_update_script_"), "update.sh")
        Path(script_path).write_text(script, encoding="utf-8")
        current_mode = os.stat(script_path).st_mode
        os.chmod(script_path, current_mode | stat.S_IXUSR)
        subprocess.Popen([script_path])

    @staticmethod
    def pick_asset_for_current_platform(assets: list[dict]) -> dict | None:
        """Chọn asset phù hợp nhất với nền tảng hiện tại."""
        if not assets:
            return None

        normalized_assets = [asset for asset in assets if asset.get("browser_download_url") and asset.get("name")]
        if not normalized_assets:
            return None

        if sys.platform == "win32":
            for asset in normalized_assets:
                name = str(asset.get("name", "")).lower()
                if name.endswith(".exe") or "windows" in name or "win" in name:
                    return asset
        elif sys.platform == "darwin":
            for asset in normalized_assets:
                name = str(asset.get("name", "")).lower()
                if "mac" in name or "darwin" in name or name.endswith(".dmg"):
                    return asset
        else:
            for asset in normalized_assets:
                name = str(asset.get("name", "")).lower()
                if "linux" in name or name.endswith((".appimage", ".bin")):
                    return asset

        return normalized_assets[0]
