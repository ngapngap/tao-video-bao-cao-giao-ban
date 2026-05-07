"""Simple ffmpeg renderer for content-bearing scene-card MP4 outputs.

The renderer is intentionally deterministic and local-only. It consumes artifacts
already produced by the pipeline and creates one visible text card per scene,
then concatenates the cards into a final MP4.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RenderResult:
    """Summary of a generated content video."""

    path: Path
    size_bytes: int
    duration_seconds: float
    scene_count: int
    has_visible_text: bool


@dataclass(frozen=True)
class SceneCard:
    """Normalized scene fields needed by the ffmpeg text-card renderer."""

    scene_id: str
    scene_type: str
    title: str
    tts_text: str
    duration_seconds: float
    audio_path: Path | None = None


class VideoContentRenderer:
    """Render simple scene-card video from existing workflow/remotion/tts artifacts."""

    MIN_TOTAL_DURATION_SECONDS = 10.0

    def __init__(self, job_dir: str | Path, require_real_audio: bool = True):
        self.job_dir = Path(job_dir)
        self.require_real_audio = require_real_audio

    def render(self, output_path: str | Path = "final/video.mp4") -> RenderResult:
        """Render all workflow scenes to an MP4 and validate the output with ffprobe."""
        if not self._ffmpeg_available():
            raise RuntimeError("ffmpeg not found, cannot render content video")

        workflow = self._load_workflow()
        tts_script = self._load_optional_json(self.job_dir / "tts" / "tts-script.json")
        render_plan = self._load_optional_json(self.job_dir / "remotion" / "render-plan.json")
        scenes = self._normalize_scenes(workflow, tts_script, render_plan)
        if not scenes:
            raise RuntimeError("workflow artifact has no scenes to render")

        target = Path(output_path)
        if not target.is_absolute():
            target = self.job_dir / target
        target.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="video_content_", dir=str(target.parent)) as tmp_name:
            tmp_dir = Path(tmp_name)
            segments = self._render_segments(scenes, tmp_dir)
            self._concat_segments(segments, tmp_dir / "concat.txt", target)

        duration = self.probe_duration(target)
        size = target.stat().st_size if target.exists() else 0
        if duration < self.MIN_TOTAL_DURATION_SECONDS:
            raise RuntimeError(f"rendered video duration is too short: {duration:.2f}s")
        if size <= 1024:
            raise RuntimeError(f"rendered video is unexpectedly small: {size} bytes")

        return RenderResult(
            path=target,
            size_bytes=size,
            duration_seconds=duration,
            scene_count=len(scenes),
            has_visible_text=True,
        )

    def _render_segments(self, scenes: list[SceneCard], tmp_dir: Path) -> list[Path]:
        segments: list[Path] = []
        for index, scene in enumerate(scenes, start=1):
            segment = tmp_dir / f"scene_{index:03d}.mp4"
            duration = max(2.0, scene.duration_seconds)
            vf = self._scene_filter(scene, index, len(scenes), tmp_dir)
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={self._background_color(index, scene.scene_type)}:s=1920x1080:d={duration:.3f}",
            ]
            audio_path = self._valid_audio_path(scene.audio_path)
            if audio_path:
                cmd.extend(["-i", str(audio_path), "-t", f"{duration:.3f}"])
            else:
                cmd.extend(["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"])
            cmd.extend(
                [
                    "-vf",
                    vf,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-r",
                    "30",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-shortest",
                    "-movflags",
                    "+faststart",
                    str(segment),
                ]
            )
            self._run(cmd, f"ffmpeg failed to render segment {scene.scene_id}")
            segments.append(segment)
        return segments

    def _concat_segments(self, segments: list[Path], list_file: Path, target: Path) -> None:
        lines = [f"file '{self._concat_file_path(segment)}'" for segment in segments]
        list_file.write_text("\n".join(lines), encoding="utf-8")
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(target),
        ]
        self._run(cmd, "ffmpeg failed to concatenate video segments")

    def _normalize_scenes(self, workflow: dict[str, Any], tts_script: dict[str, Any], render_plan: dict[str, Any]) -> list[SceneCard]:
        tts_by_scene = self._tts_items_by_scene(tts_script)
        durations_by_scene = self._durations_by_scene(render_plan)
        cards: list[SceneCard] = []
        for index, scene in enumerate(workflow.get("scenes", []), start=1):
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("scene_id") or f"scene_{index:03d}")
            title = str(scene.get("title") or scene.get("objective") or f"Scene {index}")
            tts_item = tts_by_scene.get(scene_id, {})
            tts_text = self._scene_tts_text(scene, tts_item)
            tts_enabled = bool(scene.get("tts", {}).get("enabled", False) or tts_item.get("enabled", False))
            audio_path = self._resolve_audio_path(tts_item.get("audio_path") or scene.get("tts", {}).get("audio_path"))
            if audio_path is None:
                audio_path = self.job_dir / "tts" / f"{scene_id}.mp3"
            audio_duration = self._probe_audio_duration(audio_path) if audio_path else 0.0
            if tts_enabled and self.require_real_audio:
                if not audio_path or not audio_path.exists() or audio_path.stat().st_size <= 1024:
                    raise RuntimeError(f"Scene {scene_id} has TTS enabled but audio file is missing/too small: {audio_path}")
                if audio_duration <= 0:
                    raise RuntimeError(f"Scene {scene_id} audio has invalid duration: {audio_path}")
                volume = self._probe_audio_volume(audio_path)
                if volume is None or volume[0] == float("-inf"):
                    raise RuntimeError(f"Scene {scene_id} audio is silent or volume cannot be parsed: {audio_path}")
            duration = audio_duration or durations_by_scene.get(scene_id) or self._duration_from_policy(scene, tts_text)
            cards.append(
                SceneCard(
                    scene_id=scene_id,
                    scene_type=str(scene.get("scene_type") or "content"),
                    title=title,
                    tts_text=tts_text or title,
                    duration_seconds=duration,
                    audio_path=audio_path if audio_duration > 0 else None,
                )
            )
        return cards

    def _scene_tts_text(self, scene: dict[str, Any], tts_item: dict[str, Any]) -> str:
        text = str(tts_item.get("text") or scene.get("tts", {}).get("text") or "")
        return " ".join(text.split())[:360]

    def _duration_from_policy(self, scene: dict[str, Any], tts_text: str) -> float:
        policy = scene.get("duration_policy") if isinstance(scene.get("duration_policy"), dict) else {}
        min_seconds = self._number(policy.get("min_seconds"), 5.0)
        max_seconds = self._number(policy.get("max_seconds"), 18.0)
        estimated = max(len(tts_text.split()) / 2.55, min_seconds)
        return max(3.5, min(estimated, max_seconds))

    def _tts_items_by_scene(self, tts_script: dict[str, Any]) -> dict[str, dict[str, Any]]:
        items = tts_script.get("items")
        if not isinstance(items, list):
            data = tts_script.get("data") if isinstance(tts_script.get("data"), dict) else {}
            items = data.get("items", [])
        result: dict[str, dict[str, Any]] = {}
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("scene_id"):
                result[str(item["scene_id"])] = item
        return result

    def _durations_by_scene(self, render_plan: dict[str, Any]) -> dict[str, float]:
        data = render_plan.get("data") if isinstance(render_plan.get("data"), dict) else render_plan
        timeline = data.get("timeline") if isinstance(data, dict) else None
        if not isinstance(timeline, list):
            timeline = data.get("items") if isinstance(data, dict) else []
        fps = self._number(data.get("fps") if isinstance(data, dict) else None, 30.0)
        result: dict[str, float] = {}
        for item in timeline if isinstance(timeline, list) else []:
            if not isinstance(item, dict) or not item.get("scene_id"):
                continue
            duration = self._number(item.get("duration_seconds"), 0.0)
            if duration <= 0:
                duration_frames = self._number(item.get("duration_frames"), 0.0)
                duration = duration_frames / fps if fps > 0 and duration_frames > 0 else 0.0
            if duration > 0:
                result[str(item["scene_id"])] = max(2.0, min(duration, 30.0))
        return result

    def _load_workflow(self) -> dict[str, Any]:
        workflow_dir = self.job_dir / "workflow"
        candidates = sorted(path for path in workflow_dir.glob("*.json") if path.name != "workflow-validation.json")
        if not candidates:
            raise FileNotFoundError(f"No workflow JSON found in {workflow_dir}")
        return self._load_json(candidates[0])

    def _load_optional_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return self._load_json(path)

    def _load_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise RuntimeError(f"JSON artifact must be an object: {path}")
        return data

    def probe_duration(self, video_path: str | Path) -> float:
        if not self._ffprobe_available():
            raise RuntimeError("ffprobe not found, cannot validate MP4 duration")
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "ffprobe failed").strip()
            raise RuntimeError(f"ffprobe validation failed: {detail}")
        try:
            return float(result.stdout.strip())
        except ValueError as exc:
            raise RuntimeError(f"ffprobe returned invalid duration: {result.stdout!r}") from exc

    def _scene_filter(self, scene: SceneCard, index: int, total: int, tmp_dir: Path) -> str:
        filters = [
            "drawbox=x=0:y=0:w=1920:h=1080:color=0x020617@0.18:t=fill",
            "drawbox=x=74:y=70:w=1772:h=92:color=0x0F172A@0.55:t=fill",
            "drawbox=x=88:y=214:w=1744:h=760:color=0x0B1220@0.66:t=fill",
            "drawbox=x=88:y=214:w=1744:h=760:color=0x60A5FA@0.22:t=2",
            "drawbox=x=118:y=300:w=530:h=196:color=0x1E40AF@0.42:t=fill",
            "drawbox=x=692:y=300:w=530:h=196:color=0x0F766E@0.40:t=fill",
            "drawbox=x=1266:y=300:w=530:h=196:color=0x92400E@0.38:t=fill",
        ]
        filters.extend(self._draw_lines(tmp_dir, f"scene_{index:03d}_eyebrow", ["BÁO CÁO GIAO BAN · THÁNG 03/2026"], 96, 96, 28, "0xBFDBFE"))
        filters.extend(self._draw_lines(tmp_dir, f"scene_{index:03d}_title", self._wrap_lines(scene.title, 34, 2), 118, 226, 52, "white", 62))
        cards = self._metric_cards(scene)
        card_x = [150, 724, 1298]
        for card_index, card in enumerate(cards):
            filters.extend(self._draw_lines(tmp_dir, f"scene_{index:03d}_metric_{card_index}", [card], card_x[card_index], 352, 36, "white", 46))
        body_lines = self._wrap_lines(scene.tts_text, 72, 5)
        filters.extend(self._draw_lines(tmp_dir, f"scene_{index:03d}_body", body_lines, 142, 568, 34, "0xE5E7EB", 48))
        footer = f"{index:02d}/{total:02d} · {scene.scene_type.upper()} · {scene.scene_id}"
        filters.extend(self._draw_lines(tmp_dir, f"scene_{index:03d}_footer", [footer], 118, 1006, 24, "0xCBD5E1"))
        return ",".join(filters)

    def _draw_lines(
        self,
        tmp_dir: Path,
        stem: str,
        lines: list[str],
        x: int,
        y: int,
        fontsize: int,
        color: str,
        line_height: int | None = None,
    ) -> list[str]:
        filters: list[str] = []
        step = line_height or int(fontsize * 1.35)
        for line_index, line in enumerate(lines):
            text_file = tmp_dir / f"{stem}_{line_index:02d}.txt"
            text_file.write_text(line, encoding="utf-8")
            filters.append(self._drawtext(text_file, fontsize=fontsize, x=x, y=y + line_index * step, color=color))
        return filters

    def _drawtext(self, text_file: Path, fontsize: int, x: int, y: int, color: str = "white") -> str:
        font_file = self._font_file()
        options = [
            f"textfile='{self._filter_path(text_file)}'",
            f"fontcolor={color}",
            f"fontsize={fontsize}",
            f"x={x}",
            f"y={y}",
        ]
        if font_file:
            options.insert(0, f"fontfile='{self._filter_path(font_file)}'")
        return "drawtext=" + ":".join(options)

    def _font_file(self) -> Path | None:
        candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/calibri.ttf"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _filter_path(self, path: Path) -> str:
        resolved = str(path.resolve()).replace("\\", "/")
        return resolved.replace(":", "\\:").replace("'", "\\'")

    def _concat_file_path(self, path: Path) -> str:
        return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")

    def _wrap_lines(self, text: str, width: int, max_lines: int) -> list[str]:
        words = " ".join(text.split()).split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            if not word:
                continue
            if not current:
                current = word
            elif len(current) + len(word) + 1 <= width:
                current += " " + word
            else:
                lines.append(current)
                current = word
                if len(lines) >= max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        if not lines:
            lines.append(" ")
        if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
            lines[-1] = lines[-1].rstrip(" .,;") + "…"
        return lines

    def _metric_cards(self, scene: SceneCard) -> list[str]:
        numbers = re.findall(r"\b\d+[\d\s]*(?:[,\.]\d+)?(?:\s*(?:%|phần trăm|tỷ|triệu|nghìn|hồ sơ|người|lượt))?", scene.tts_text)
        cleaned = [" ".join(item.split()) for item in numbers if len(item.strip()) >= 2]
        defaults = [scene.scene_type.upper(), "TTS-FIRST", "KHÔNG CHỒNG FRAME"]
        cards: list[str] = []
        for value in cleaned[:3]:
            cards.append(value[:28])
        while len(cards) < 3:
            cards.append(defaults[len(cards)])
        return cards[:3]

    def _resolve_audio_path(self, audio_path: Any) -> Path | None:
        if not isinstance(audio_path, str) or not audio_path.strip():
            return None
        path = Path(audio_path)
        if not path.is_absolute():
            path = self.job_dir / path
        return path

    def _valid_audio_path(self, audio_path: Path | None) -> Path | None:
        if not audio_path or not audio_path.exists() or audio_path.stat().st_size <= 1024:
            if self.require_real_audio:
                raise RuntimeError(f"Audio file is missing or too small: {audio_path}")
            return None
        if self._probe_audio_duration(audio_path) <= 0:
            if self.require_real_audio:
                raise RuntimeError(f"Audio duration is invalid: {audio_path}")
            return None
        volume = self._probe_audio_volume(audio_path)
        if volume is None or volume[0] == float("-inf"):
            if self.require_real_audio:
                raise RuntimeError(f"Audio is silent or volume cannot be parsed: {audio_path}")
            return None
        return audio_path

    def _probe_audio_duration(self, audio_path: Path | None) -> float:
        if not audio_path or not audio_path.exists() or audio_path.stat().st_size <= 1024 or not self._ffprobe_available():
            return 0.0
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            return 0.0
        try:
            duration = float(result.stdout.strip())
        except ValueError:
            return 0.0
        return duration if duration > 0 else 0.0

    def _probe_audio_volume(self, audio_path: Path) -> tuple[float, float] | None:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(audio_path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return None
        output = f"{result.stdout}\n{result.stderr}"
        mean_match = re.search(r"mean_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", output)
        max_match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", output)
        if not mean_match or not max_match:
            return None
        mean_raw = mean_match.group(1)
        max_raw = max_match.group(1)
        mean_volume = float("-inf") if mean_raw == "-inf" else float(mean_raw)
        max_volume = float("-inf") if max_raw == "-inf" else float(max_raw)
        return mean_volume, max_volume

    def _background_color(self, index: int, scene_type: str) -> str:
        if scene_type == "intro":
            return "0x1E3A8A"
        if scene_type == "closing":
            return "0x14532D"
        palette = ["0x0B1220", "0x172554", "0x312E81", "0x134E4A", "0x3B0764"]
        return palette[(index - 1) % len(palette)]

    def _number(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _ffmpeg_available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def _ffprobe_available(self) -> bool:
        return shutil.which("ffprobe") is not None

    def _run(self, cmd: list[str], error_prefix: str) -> None:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(f"{error_prefix}: {detail}") from exc
