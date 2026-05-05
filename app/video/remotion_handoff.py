"""Remotion handoff helpers for manifest, TTS, readiness, and final packaging."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional


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
        """Tạo manifest cuối cùng cho Remotion."""
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
    """Tạo TTS audio cho từng scene (mock mode + real mode)."""

    def __init__(
        self,
        output_dir: str,
        tts_url: str = "",
        tts_api_key: str = "",
        tts_model: str = "",
        mock_mode: bool = True,
    ):
        self.output_dir = output_dir
        self.tts_url = tts_url
        self.tts_api_key = tts_api_key
        self.tts_model = tts_model
        self.mock_mode = mock_mode

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

            if self.mock_mode:
                result = self._generate_mock(scene_id, text)
            else:
                result = self._generate_real(scene_id, text, tts.get("voice", ""))
            manifest[scene_id] = result

        return manifest

    def _generate_mock(self, scene_id: str, text: str) -> dict:
        """Tạo file mock TTS placeholder."""
        tts_dir = os.path.join(self.output_dir, "tts")
        os.makedirs(tts_dir, exist_ok=True)

        audio_path = os.path.join(tts_dir, f"{scene_id}.mp3")
        word_count = len(text.split())
        duration = max(2.0, word_count / 2.5)

        with open(audio_path, "wb") as file:
            file.write(b"")

        return {"audio_path": f"tts/{scene_id}.mp3", "duration_seconds": round(duration, 1)}

    def _generate_real(self, scene_id: str, text: str, voice: str) -> dict:
        """Gọi TTS API thật (placeholder cho tương lai)."""
        raise NotImplementedError("Real TTS generation chưa được implement. Dùng mock_mode=True.")

    def probe_audio_duration(self, audio_path: str) -> float:
        """Đo duration audio file. Mock mode trả ước tính."""
        if self.mock_mode:
            return 5.0
        raise NotImplementedError("Real audio probe chưa được implement.")


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
        """Tạo file video MP4 mock placeholder."""
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
