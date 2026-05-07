"""Remotion handoff helpers for manifest, TTS, readiness, and final packaging."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


class RemotionManifest:
    """Manifest để Remotion renderer biết cách render video."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def build_manifest(
        self,
        workflow_data: dict,
        component_spec: dict,
        render_plan: dict,
        tts_manifest: dict,
    ) -> dict:
        """Tạo manifest cuối cùng để renderer biết scene/component/timing/audio."""
        scenes = workflow_data.get("scenes", [])
        manifest = {
            "version": "1.0",
            "video_settings": workflow_data.get("video_settings", {}),
            "scenes": [],
            "tts_audio": tts_manifest,
            "render_config": {
                "output_path": os.path.join("final", "video.mp4"),
                "preview": False,
            },
        }

        for scene in scenes:
            scene_id = scene.get("scene_id", "")
            component = self._find_component(component_spec, scene_id)
            timing = self._find_timing(render_plan, scene_id)

            manifest["scenes"].append(
                {
                    "scene_id": scene_id,
                    "scene_type": scene.get("scene_type", "content"),
                    "title": scene.get("title", ""),
                    "component": component,
                    "timing": timing,
                    "tts": scene.get("tts", {}),
                }
            )

        return manifest

    def save_manifest(self, manifest: dict, filename: str = "remotion-manifest.json") -> str:
        """Lưu manifest ra file."""
        path = os.path.join(self.output_dir, "remotion", filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2)
        return path

    def _find_component(self, component_spec: dict, scene_id: str) -> dict:
        components = component_spec.get("components", [])
        for component in components:
            if component.get("scene_id") == scene_id:
                return component
        return {"scene_id": scene_id, "type": "default"}

    def _find_timing(self, render_plan: dict, scene_id: str) -> dict:
        timeline = render_plan.get("timeline", [])
        for timing in timeline:
            if timing.get("scene_id") == scene_id:
                return timing
        return {"start_frame": 0, "duration_frames": 90}


class TTSGenerator:
    """Tạo TTS audio cho từng scene bằng edge-tts, API TTS hoặc mock."""

    DEFAULT_VOICES = ("vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural")

    def __init__(
        self,
        output_dir: str,
        tts_url: str = "",
        tts_api_key: str = "",
        tts_model: str = "",
        mock_mode: bool = True,
        timeout: float = 120.0,
        tts_engine: str = "mock",
        default_voice: str = "vi-VN-NamMinhNeural",
    ):
        self.output_dir = output_dir
        self.tts_url = tts_url.rstrip("/")
        self.tts_api_key = tts_api_key
        self.tts_model = tts_model
        self.mock_mode = mock_mode
        self.tts_engine = self._normalize_engine(tts_engine, mock_mode)
        self.default_voice = default_voice or "vi-VN-NamMinhNeural"
        self.timeout = timeout

    def generate_all(self, scenes: list[dict]) -> dict:
        """Tạo TTS cho tất cả scene có tts.enabled=true.

        Trả manifest: {"scene_id": {"audio_path": "...", "duration_seconds": float}}
        """
        manifest = {}
        for scene in scenes:
            scene_id = scene.get("scene_id", "")
            tts = scene.get("tts", {})
            if not tts.get("enabled", False):
                manifest[scene_id] = {"audio_path": None, "duration_seconds": 0}
                continue

            text = tts.get("text", "")
            if not text:
                manifest[scene_id] = {"audio_path": None, "duration_seconds": 0}
                continue

            voice = tts.get("voice") or self.default_voice
            if self.tts_engine == "mock":
                result = self._generate_mock(scene_id, text)
            elif self.tts_engine == "edge":
                result = self._generate_edge(scene_id, text, voice)
            elif self.tts_engine == "api":
                result = self._generate_real(scene_id, text, voice)
            else:
                raise ValueError(f"TTS engine không hỗ trợ: {self.tts_engine}")
            manifest[scene_id] = result

        return manifest

    def _generate_mock(self, scene_id: str, text: str) -> dict:
        """Tạo file mock TTS placeholder."""
        tts_dir = os.path.join(self.output_dir, "tts")
        os.makedirs(tts_dir, exist_ok=True)

        audio_path = os.path.join(tts_dir, f"{scene_id}.mp3")
        duration = self._estimate_duration_seconds(text)

        with open(audio_path, "wb") as file:
            file.write(b"")

        return {"audio_path": f"tts/{scene_id}.mp3", "duration_seconds": round(duration, 1)}

    def _generate_edge(self, scene_id: str, text: str, voice: str) -> dict:
        """Tạo MP3 bằng edge-tts local-compatible async client."""
        try:
            edge_tts = importlib.import_module("edge_tts")
        except ImportError as exc:
            raise ImportError("edge-tts không khả dụng trong runtime hiện tại. Cài dependency bằng: python -m pip install edge-tts") from exc
        tts_dir = Path(self.output_dir) / "tts"
        tts_dir.mkdir(parents=True, exist_ok=True)
        audio_file = tts_dir / f"{scene_id}.mp3"
        selected_voice = voice or self.default_voice

        async def _save() -> None:
            communicate = edge_tts.Communicate(text, selected_voice)
            await communicate.save(str(audio_file))

        try:
            asyncio.run(_save())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_save())
            finally:
                loop.close()

        duration = self.probe_audio_duration(str(audio_file)) or self._estimate_duration_seconds(text)
        return {"audio_path": f"tts/{scene_id}.mp3", "duration_seconds": round(duration, 1)}

    def _generate_real(self, scene_id: str, text: str, voice: str) -> dict:
        """Gọi TTS API thật theo kiểu OpenAI-compatible hoặc JSON/base64 phổ biến."""
        if not self.tts_url or not self.tts_api_key:
            raise ValueError("Thiếu URL hoặc API key TTS để tạo audio thật")

        tts_dir = Path(self.output_dir) / "tts"
        tts_dir.mkdir(parents=True, exist_ok=True)
        audio_file = tts_dir / f"{scene_id}.mp3"
        endpoint = self._speech_endpoint()
        payload = {
            "model": self.tts_model or "tts-1",
            "input": text,
            "voice": voice or "alloy",
            "response_format": "mp3",
        }
        headers = {"Authorization": f"Bearer {self.tts_api_key}", "Content-Type": "application/json"}

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                self._write_audio_from_json(audio_file, response.json())
            else:
                audio_file.write_bytes(response.content)

        duration = self.probe_audio_duration(str(audio_file)) or self._estimate_duration_seconds(text)
        return {"audio_path": f"tts/{scene_id}.mp3", "duration_seconds": round(duration, 1)}

    def _speech_endpoint(self) -> str:
        if self.tts_url.endswith("/audio/speech") or self.tts_url.endswith("/tts"):
            return self.tts_url
        return self.tts_url + "/audio/speech"

    def _write_audio_from_json(self, audio_file: Path, data: dict[str, Any]) -> None:
        audio_b64 = data.get("audio") or data.get("audio_base64") or data.get("data")
        if isinstance(audio_b64, str):
            audio_file.write_bytes(base64.b64decode(audio_b64))
            return
        audio_url = data.get("audio_url") or data.get("url")
        if isinstance(audio_url, str):
            headers = {"Authorization": f"Bearer {self.tts_api_key}"}
            with httpx.Client(timeout=self.timeout) as client:
                audio_response = client.get(audio_url, headers=headers)
                audio_response.raise_for_status()
                audio_file.write_bytes(audio_response.content)
            return
        raise ValueError("TTS API trả JSON nhưng không có audio/audio_base64/audio_url")

    def probe_audio_duration(self, audio_path: str) -> float:
        """Đo duration audio bằng ffprobe nếu có; fallback trả 0 để caller ước tính."""
        if self.mock_mode:
            return 5.0
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            return 0.0
        return 0.0

    def test_connection(self) -> tuple[bool, str]:
        """Kiểm tra engine TTS hiện tại."""
        if self.tts_engine == "mock":
            return True, "Mock test: OK"
        if self.tts_engine == "edge":
            try:
                importlib.import_module("edge_tts")
                return True, f"edge-tts local OK! Voice: {self.default_voice}"
            except ImportError as exc:
                return False, f"edge-tts chưa khả dụng trong runtime hiện tại. Cài dependency bằng: python -m pip install edge-tts. Chi tiết: {exc}"
        try:
            result = self._generate_real("healthcheck", "Kiểm tra kết nối TTS.", self.default_voice)
            path = Path(self.output_dir) / str(result["audio_path"])
            if path.exists():
                path.unlink(missing_ok=True)
            return True, f"Kết nối thành công! Model: {self.tts_model or 'tts-1'}"
        except httpx.TimeoutException:
            return False, "Không kết nối được: timeout khi gọi TTS API"
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            return False, f"Không kết nối được: HTTP {exc.response.status_code} - {detail}"
        except Exception as exc:  # noqa: BLE001 - hiển thị lỗi cụ thể cho UI
            return False, f"Không kết nối được: {exc}"

    @staticmethod
    def _normalize_engine(tts_engine: str, mock_mode: bool) -> str:
        if mock_mode:
            return "mock"
        normalized = (tts_engine or "api").strip().lower()
        return normalized if normalized in {"edge", "api", "mock"} else "api"

    @staticmethod
    def _estimate_duration_seconds(text: str) -> float:
        word_count = len(text.split())
        return max(2.0, word_count / 2.5)


class RenderGate:
    """Kiểm tra readiness trước khi render final."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def check_preview_ready(self, manifest: dict) -> tuple[bool, list[str]]:
        """Kiểm tra manifest đủ điều kiện render preview."""
        errors = []

        if not manifest.get("scenes"):
            errors.append("Manifest không có scene")

        for scene in manifest.get("scenes", []):
            scene_id = scene.get("scene_id", "?")
            if not scene.get("component"):
                errors.append(f"Scene {scene_id} thiếu component spec")
            if not scene.get("timing"):
                errors.append(f"Scene {scene_id} thiếu timing")

        return len(errors) == 0, errors

    def check_final_ready(self, manifest: dict, tts_manifest: dict) -> tuple[bool, list[str]]:
        """Kiểm tra đủ điều kiện render final."""
        _, errors = self.check_preview_ready(manifest)

        for scene in manifest.get("scenes", []):
            scene_id = scene.get("scene_id", "?")
            tts = scene.get("tts", {})
            if tts.get("enabled", False):
                tts_info = tts_manifest.get(scene_id, {})
                if not tts_info.get("audio_path"):
                    errors.append(f"Scene {scene_id} có TTS enabled nhưng không có audio")

        return len(errors) == 0, errors


class FinalPackager:
    """Đóng gói video final + metadata."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def create_publish_manifest(
        self,
        job_id: str,
        report_month: str,
        video_path: str,
        manifest: dict,
    ) -> dict:
        """Tạo publish-manifest.json."""
        publish = {
            "job_id": job_id,
            "report_month": report_month,
            "video_file": video_path,
            "created_at": self._now_iso(),
            "scene_count": len(manifest.get("scenes", [])),
            "status": "published",
            "checksum": self._compute_checksum(video_path),
        }

        final_dir = os.path.join(self.output_dir, "final")
        os.makedirs(final_dir, exist_ok=True)
        path = os.path.join(final_dir, "publish-manifest.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(publish, file, ensure_ascii=False, indent=2)

        return publish

    def create_mock_video(self) -> str:
        """Tạo file video MP4 mock placeholder cho mock/dev mode."""
        final_dir = os.path.join(self.output_dir, "final")
        os.makedirs(final_dir, exist_ok=True)
        video_path = os.path.join(final_dir, "video.mp4")
        with open(video_path, "wb") as file:
            file.write(b"\x00" * 1024)
        return "final/video.mp4"

    def _compute_checksum(self, relative_path: str) -> str:
        """Compute MD5 checksum của file."""
        full_path = os.path.join(self.output_dir, relative_path)
        if not os.path.exists(full_path):
            return "mock-checksum"
        with open(full_path, "rb") as file:
            return hashlib.md5(file.read()).hexdigest()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
