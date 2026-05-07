from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

import edge_tts

JOB_DIR = Path("outputs/202603/20260507-162142-real-app-flow")
WORKFLOW_PATH = JOB_DIR / "workflow" / "workflow-202603-20260507-162142-real-app-flow.json"
TTS_SCRIPT_PATH = JOB_DIR / "tts" / "tts-script.json"
VOICE = "vi-VN-NamMinhNeural"


def run(cmd: list[str], error_prefix: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(f"{error_prefix}: {detail}")
    return result


def duration(path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], f"ffprobe duration failed for {path}")
    return float(result.stdout.strip())


def volume(path: Path) -> tuple[float, float]:
    result = run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], f"volumedetect failed for {path}")
    output = f"{result.stdout}\n{result.stderr}"
    mean_match = re.search(r"mean_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", output)
    max_match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", output)
    if not mean_match or not max_match:
        raise RuntimeError(f"Cannot parse volume for {path}")
    mean_raw, max_raw = mean_match.group(1), max_match.group(1)
    mean = float("-inf") if mean_raw == "-inf" else float(mean_raw)
    maxv = float("-inf") if max_raw == "-inf" else float(max_raw)
    if mean == float("-inf"):
        raise RuntimeError(f"Silent audio detected: {path}")
    return mean, maxv


def load_scene_texts() -> list[dict[str, str]]:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    tts_script = json.loads(TTS_SCRIPT_PATH.read_text(encoding="utf-8")) if TTS_SCRIPT_PATH.exists() else {}
    items = (tts_script.get("data") or {}).get("items") or tts_script.get("items") or []
    item_text = {str(item.get("scene_id")): str(item.get("text") or "").strip() for item in items if isinstance(item, dict)}
    scenes = []
    for scene in workflow.get("scenes", []):
        scene_id = str(scene.get("scene_id") or "").strip()
        if not scene_id:
            continue
        text = item_text.get(scene_id) or str((scene.get("tts") or {}).get("text") or "").strip()
        if not text:
            raise RuntimeError(f"Scene {scene_id} has no TTS text")
        scenes.append({"scene_id": scene_id, "text": text, "voice": VOICE})
    return scenes


async def generate_scene(scene: dict[str, str]) -> dict[str, object]:
    out_path = JOB_DIR / "tts" / f"{scene['scene_id']}.mp3"
    out_path.unlink(missing_ok=True)
    communicate = edge_tts.Communicate(scene["text"], scene.get("voice") or VOICE)
    await communicate.save(str(out_path))
    size = out_path.stat().st_size if out_path.exists() else 0
    dur = duration(out_path)
    mean, maxv = volume(out_path)
    if size <= 1024 or dur <= 0 or mean == float("-inf"):
        raise RuntimeError(f"Invalid generated audio for {scene['scene_id']}: size={size}, duration={dur}, mean={mean}")
    return {
        "scene_id": scene["scene_id"],
        "text_length": len(scene["text"]),
        "path": str(out_path).replace("\\", "/"),
        "size_bytes": size,
        "duration_seconds": round(dur, 3),
        "mean_volume_db": mean,
        "max_volume_db": maxv,
    }


async def main() -> None:
    scenes = load_scene_texts()
    print(f"Generating real edge-tts audio for {len(scenes)} scenes using {VOICE}")
    results = []
    for scene in scenes:
        result = await generate_scene(scene)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))
    report_path = JOB_DIR / "tts" / "audio-validation-real-tts.json"
    report_path.write_text(json.dumps({"voice": VOICE, "items": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
