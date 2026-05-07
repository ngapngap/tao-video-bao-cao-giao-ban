"""Create a content-bearing MP4 from existing pipeline artifacts only.

This script intentionally skips PDF/LLM/P1/P2 execution. It reads artifacts from
``outputs/202603/20260507-162142-real-app-flow`` and renders a simple but visible
video with one text card per scene.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.video.content_renderer import VideoContentRenderer

DEFAULT_JOB_DIR = Path("outputs/202603/20260507-162142-real-app-flow")
DEFAULT_OUTPUT = Path("final/video_with_tts.mp4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render video-only test from existing artifacts with real non-silent TTS validation.")
    parser.add_argument(
        "--job-dir",
        type=Path,
        default=DEFAULT_JOB_DIR,
        help="Existing job output directory containing workflow/remotion/tts artifacts.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output MP4 path. Relative paths are resolved inside --job-dir.",
    )
    parser.add_argument(
        "--allow-silent-fallback",
        action="store_true",
        help="Allow missing/invalid audio to fall back to silence. Intended only for explicit mock tests.",
    )
    return parser.parse_args()


def _run(cmd: list[str], error_prefix: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(f"{error_prefix}: {detail}")
    return result


def _probe_duration(path: Path) -> float:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        f"ffprobe duration failed for {path}",
    )
    return float(result.stdout.strip())


def _probe_volume(path: Path) -> tuple[float, float]:
    result = _run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        f"volumedetect failed for {path}",
    )
    output = f"{result.stdout}\n{result.stderr}"
    mean_match = re.search(r"mean_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", output)
    max_match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", output)
    if not mean_match or not max_match:
        raise RuntimeError(f"Cannot parse volumedetect output for {path}")
    mean_raw = mean_match.group(1)
    max_raw = max_match.group(1)
    mean_volume = float("-inf") if mean_raw == "-inf" else float(mean_raw)
    max_volume = float("-inf") if max_raw == "-inf" else float(max_raw)
    if mean_volume == float("-inf"):
        raise RuntimeError(f"Audio is silent: {path}")
    return mean_volume, max_volume


def _has_audio_stream(path: Path) -> bool:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ],
        f"ffprobe audio stream failed for {path}",
    )
    data = json.loads(result.stdout or "{}")
    return bool(data.get("streams"))


def _validate_final_video(path: Path) -> tuple[float, float, float]:
    if not path.exists() or path.stat().st_size <= 1024:
        raise RuntimeError(f"Final video missing/too small: {path}")
    if not _has_audio_stream(path):
        raise RuntimeError(f"Final video has no audio stream: {path}")
    duration = _probe_duration(path)
    if duration <= 30:
        raise RuntimeError(f"Final video duration must be > 30s, got {duration:.2f}s")
    mean_volume, max_volume = _probe_volume(path)
    return duration, mean_volume, max_volume


def main() -> int:
    args = parse_args()
    job_dir = args.job_dir

    if not args.allow_silent_fallback and not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required for real-audio validation")
    if not args.allow_silent_fallback and not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for real-audio validation")

    renderer = VideoContentRenderer(job_dir, require_real_audio=not args.allow_silent_fallback)
    result = renderer.render(args.output)
    final_duration, final_mean, final_max = _validate_final_video(result.path)

    print(f"Video-only render OK: {result.path}")
    print(f"Size bytes: {result.size_bytes}")
    print(f"Duration seconds: {result.duration_seconds:.2f}")
    print(f"Scene count: {result.scene_count}")
    print(f"Visible text: {result.has_visible_text}")
    print(f"Final audio mean_volume: {final_mean:.1f} dB")
    print(f"Final audio max_volume: {final_max:.1f} dB")
    print(f"Final validated duration seconds: {final_duration:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
