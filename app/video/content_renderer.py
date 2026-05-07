"""Simple ffmpeg renderer for content-bearing scene-card MP4 outputs.

The renderer is intentionally deterministic and local-only. It consumes artifacts
already produced by the pipeline and creates one visible text card per scene,
then concatenates the cards into a final MP4.
"""

from __future__ import annotations

import json
import os
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


class VideoContentRenderer:
    """Render simple scene-card video from existing workflow/remotion/tts artifacts."""

    MIN_TOTAL_DURATION_SECONDS = 10.0

    def __init__(self, job_dir: str | Path):
        self.job_dir = Path(job_dir)

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
            title_file = tmp_dir / f"scene_{index:03d}_title.txt"
            body_file = tmp_dir / f"scene_{index:03d}_body.txt"
            footer_file = tmp_dir / f"scene_{index:03d}_footer.txt"
            title_file.write_text(self._wrap_text(scene.title, 42), encoding="utf-8")
            body_file.write_text(self._wrap_text(scene.tts_text, 58), encoding="utf-8")
            footer_file.write_text(
                f"{index:02d}/{len(scenes):02d} · {scene.scene_type.upper()} · {scene.scene_id}",
                encoding="utf-8",
            )

            color = self._background_color(index, scene.scene_type)
            vf = ",".join(
                [
                    self._drawtext(title_file, fontsize=58, x=120, y=150, box=True),
                    self._drawtext(body_file, fontsize=38, x=120, y=360, box=True, line_spacing=14),
                    self._drawtext(footer_file, fontsize=30, x=120, y=940, box=False),
                ]
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=1920x1080:d={scene.duration_seconds:.3f}",
                "-vf",
                vf,
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(segment),
            ]
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
            tts_text = self._scene_tts_text(scene, tts_by_scene.get(scene_id, {}))
            duration = durations_by_scene.get(scene_id) or self._duration_from_policy(scene, tts_text)
            cards.append(
                SceneCard(
                    scene_id=scene_id,
                    scene_type=str(scene.get("scene_type") or "content"),
                    title=title,
                    tts_text=tts_text or title,
                    duration_seconds=duration,
                )
            )
        return cards

    def _scene_tts_text(self, scene: dict[str, Any], tts_item: dict[str, Any]) -> str:
        text = str(tts_item.get("text") or scene.get("tts", {}).get("text") or "")
        return " ".join(text.split())[:360]

    def _duration_from_policy(self, scene: dict[str, Any], tts_text: str) -> float:
        policy = scene.get("duration_policy") if isinstance(scene.get("duration_policy"), dict) else {}
        min_seconds = self._number(policy.get("min_seconds"), 3.0)
        max_seconds = self._number(policy.get("max_seconds"), 10.0)
        estimated = max(len(tts_text) / 18.0, min_seconds)
        return max(2.0, min(estimated, max_seconds))

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

    def _drawtext(self, text_file: Path, fontsize: int, x: int, y: int, box: bool, line_spacing: int = 8) -> str:
        font_file = self._font_file()
        options = [
            f"textfile='{self._filter_path(text_file)}'",
            "fontcolor=white",
            f"fontsize={fontsize}",
            f"x={x}",
            f"y={y}",
            f"line_spacing={line_spacing}",
        ]
        if font_file:
            options.insert(0, f"fontfile='{self._filter_path(font_file)}'")
        if box:
            options.extend(["box=1", "boxcolor=0x020617@0.62", "boxborderw=24"])
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

    def _wrap_text(self, text: str, width: int) -> str:
        words = " ".join(text.split()).split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            if not current:
                current = word
            elif len(current) + len(word) + 1 <= width:
                current += " " + word
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return "\n".join(lines[:6])

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
