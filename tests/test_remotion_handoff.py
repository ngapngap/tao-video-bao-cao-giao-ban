"""Unit tests cho Remotion/video handoff helpers."""

from __future__ import annotations

import json
import os

from app.video import FinalPackager, RemotionManifest, RenderGate, TTSGenerator


def _workflow_data() -> dict:
    return {
        "video_settings": {"fps": 30, "width": 1920, "height": 1080},
        "scenes": [
            {
                "scene_id": "scene_intro",
                "scene_type": "intro",
                "title": "Mở đầu",
                "tts": {"enabled": True, "text": "Xin chào báo cáo giao ban tháng năm.", "voice": "vi_female"},
            },
            {
                "scene_id": "scene_content_01",
                "scene_type": "content",
                "title": "Nội dung chính",
                "tts": {"enabled": True, "text": "Sản lượng tháng này tăng so với cùng kỳ.", "voice": "vi_female"},
            },
            {
                "scene_id": "scene_closing",
                "scene_type": "closing",
                "title": "Kết thúc",
                "tts": {"enabled": False, "text": ""},
            },
        ],
    }


def _component_spec() -> dict:
    return {
        "components": [
            {"scene_id": "scene_intro", "type": "TitleScene", "props": {"variant": "hero"}},
            {"scene_id": "scene_content_01", "type": "MetricScene", "props": {"variant": "chart"}},
            {"scene_id": "scene_closing", "type": "ClosingScene", "props": {"variant": "summary"}},
        ]
    }


def _render_plan() -> dict:
    return {
        "timeline": [
            {"scene_id": "scene_intro", "start_frame": 0, "duration_frames": 120},
            {"scene_id": "scene_content_01", "start_frame": 120, "duration_frames": 180},
            {"scene_id": "scene_closing", "start_frame": 300, "duration_frames": 90},
        ]
    }


def _manifest(tmp_path, tts_manifest: dict | None = None) -> dict:
    builder = RemotionManifest(str(tmp_path))
    return builder.build_manifest(
        _workflow_data(),
        _component_spec(),
        _render_plan(),
        tts_manifest or {},
    )


def test_remotion_manifest_build_manifest_has_all_scenes(tmp_path):
    tts_manifest = {
        "scene_intro": {"audio_path": "tts/scene_intro.mp3", "duration_seconds": 2.8},
        "scene_content_01": {"audio_path": "tts/scene_content_01.mp3", "duration_seconds": 3.2},
        "scene_closing": {"audio_path": None, "duration_seconds": 0},
    }
    builder = RemotionManifest(str(tmp_path))

    manifest = builder.build_manifest(_workflow_data(), _component_spec(), _render_plan(), tts_manifest)
    path = builder.save_manifest(manifest)

    assert manifest["version"] == "1.0"
    assert manifest["video_settings"] == {"fps": 30, "width": 1920, "height": 1080}
    assert len(manifest["scenes"]) == 3
    assert [scene["scene_id"] for scene in manifest["scenes"]] == [
        "scene_intro",
        "scene_content_01",
        "scene_closing",
    ]
    assert manifest["scenes"][0]["component"]["type"] == "TitleScene"
    assert manifest["scenes"][1]["timing"]["start_frame"] == 120
    assert manifest["tts_audio"] == tts_manifest
    assert manifest["render_config"]["output_path"] == os.path.join("final", "video.mp4")
    assert os.path.exists(path)


def test_tts_generator_generate_all_mock_mode_creates_audio_and_duration(tmp_path):
    generator = TTSGenerator(str(tmp_path), mock_mode=True)

    tts_manifest = generator.generate_all(_workflow_data()["scenes"])

    assert tts_manifest["scene_intro"]["audio_path"] == "tts/scene_intro.mp3"
    assert tts_manifest["scene_intro"]["duration_seconds"] >= 2.0
    assert tts_manifest["scene_content_01"]["audio_path"] == "tts/scene_content_01.mp3"
    assert tts_manifest["scene_content_01"]["duration_seconds"] >= 2.0
    assert tts_manifest["scene_closing"] == {"audio_path": None, "duration_seconds": 0}
    assert os.path.exists(tmp_path / "tts" / "scene_intro.mp3")
    assert os.path.exists(tmp_path / "tts" / "scene_content_01.mp3")


def test_render_gate_check_preview_ready_passes_with_valid_manifest(tmp_path):
    gate = RenderGate(str(tmp_path))
    manifest = _manifest(tmp_path)

    ok, errors = gate.check_preview_ready(manifest)

    assert ok is True
    assert errors == []


def test_render_gate_check_final_ready_fails_when_tts_audio_missing(tmp_path):
    gate = RenderGate(str(tmp_path))
    manifest = _manifest(tmp_path, tts_manifest={})

    ok, errors = gate.check_final_ready(manifest, tts_manifest={})

    assert ok is False
    assert "Scene scene_intro có TTS enabled nhưng không có audio" in errors
    assert "Scene scene_content_01 có TTS enabled nhưng không có audio" in errors


def test_final_packager_create_mock_video_creates_video_file(tmp_path):
    packager = FinalPackager(str(tmp_path))

    video_path = packager.create_mock_video()

    assert video_path == "final/video.mp4"
    full_path = tmp_path / "final" / "video.mp4"
    assert full_path.exists()
    assert full_path.stat().st_size == 1024


def test_final_packager_create_publish_manifest_creates_file(tmp_path):
    packager = FinalPackager(str(tmp_path))
    video_path = packager.create_mock_video()
    manifest = _manifest(tmp_path)

    publish = packager.create_publish_manifest("job-11", "202605", video_path, manifest)

    assert publish["job_id"] == "job-11"
    assert publish["report_month"] == "202605"
    assert publish["video_file"] == "final/video.mp4"
    assert publish["scene_count"] == 3
    assert publish["status"] == "published"
    assert publish["checksum"] != "mock-checksum"

    publish_path = tmp_path / "final" / "publish-manifest.json"
    assert publish_path.exists()
    saved = json.loads(publish_path.read_text(encoding="utf-8"))
    assert saved == publish
