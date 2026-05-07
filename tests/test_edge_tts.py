"""Unit tests cho edge-tts integration."""

from __future__ import annotations

import sys
import types

from app.video.remotion_handoff import TTSGenerator


class FakeCommunicate:
    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice

    async def save(self, output_path: str) -> None:
        with open(output_path, "wb") as file:
            file.write(b"fake-mp3")


def test_generate_edge_creates_mp3_file(monkeypatch, tmp_path):
    fake_module = types.SimpleNamespace(Communicate=FakeCommunicate)
    monkeypatch.setitem(sys.modules, "edge_tts", fake_module)
    generator = TTSGenerator(str(tmp_path), mock_mode=False, tts_engine="edge")
    monkeypatch.setattr(generator, "probe_audio_duration", lambda _path: 3.4)

    result = generator._generate_edge("scene_intro", "Xin chào báo cáo giao ban.", "vi-VN-HoaiMyNeural")

    assert result == {"audio_path": "tts/scene_intro.mp3", "duration_seconds": 3.4}
    assert (tmp_path / "tts" / "scene_intro.mp3").read_bytes() == b"fake-mp3"


def test_default_voice_is_nam_minh(tmp_path):
    generator = TTSGenerator(str(tmp_path), mock_mode=False, tts_engine="edge")

    assert generator.default_voice == "vi-VN-NamMinhNeural"
    assert "vi-VN-NamMinhNeural" in TTSGenerator.DEFAULT_VOICES
    assert "vi-VN-HoaiMyNeural" in TTSGenerator.DEFAULT_VOICES


def test_test_connection_edge_mode_import_success(monkeypatch, tmp_path):
    fake_module = types.SimpleNamespace(Communicate=FakeCommunicate)
    monkeypatch.setitem(sys.modules, "edge_tts", fake_module)
    generator = TTSGenerator(str(tmp_path), mock_mode=False, tts_engine="edge")

    ok, message = generator.test_connection()

    assert ok is True
    assert "edge-tts local OK" in message
