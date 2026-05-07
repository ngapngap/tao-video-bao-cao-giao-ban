"""Create a content-bearing MP4 from existing pipeline artifacts only.

This script intentionally skips PDF/LLM/P1/P2 execution. It reads artifacts from
``outputs/202603/20260507-162142-real-app-flow`` and renders a simple but visible
video with one text card per scene.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.video.content_renderer import VideoContentRenderer

DEFAULT_JOB_DIR = Path("outputs/202603/20260507-162142-real-app-flow")
DEFAULT_OUTPUT = Path("final/video_content_test.mp4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render video-only test from existing artifacts.")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    job_dir = args.job_dir

    renderer = VideoContentRenderer(job_dir)
    result = renderer.render(args.output)

    print(f"Video-only render OK: {result.path}")
    print(f"Size bytes: {result.size_bytes}")
    print(f"Duration seconds: {result.duration_seconds:.2f}")
    print(f"Scene count: {result.scene_count}")
    print(f"Visible text: {result.has_visible_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
