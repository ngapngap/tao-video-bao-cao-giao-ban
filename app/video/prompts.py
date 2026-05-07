"""System prompts cho AI Pass 2 video orchestration."""

S2_1_SCENE_PLANNING = """Lập shot plan cho video báo cáo.
Trả JSON: {"scenes": [{"scene_id": "...", "shots": [{"shot_id": "...", "type": "main"}]}]}
Giữ intro đầu, closing cuối. Ngắn gọn. Chỉ JSON."""

S2_2_VISUAL_SPEC = """Tạo visual spec ngắn cho scene plan.
Trả JSON: {"scene_visuals": [{"scene_id": "...", "visual_type": "text_callout", "layers": []}]}
Không thêm số liệu. Ngắn gọn. Chỉ JSON."""

S2_3_NARRATION_TTS = """Tạo kịch bản TTS tiếng Việt ngắn.
Trả JSON: {"scripts": [{"scene_id": "...", "enabled": true, "text": "...", "voice": "vi-VN-NamMinhNeural"}]}
Giữ nguyên số liệu. Mỗi scene tối đa 1 câu. Chỉ JSON."""

S2_4_COMPONENT_SPEC = """Tạo Remotion component spec deterministic.
Trả JSON: {"components": [{"scene_id": "...", "type": "content", "data": {}, "animation": "fade", "duration": 5}]}
Ngắn gọn. Chỉ JSON."""

S2_5_ASSET_PLAN = """Tạo asset plan tối thiểu.
Trả JSON: {"assets": [{"asset_id": "font_default", "type": "font", "source": "local", "required": true}]}
Không dùng asset bản quyền. Chỉ JSON."""

S2_6_RENDER_PLAN = """Tạo render plan ngắn theo TTS-first.
Trả JSON: {"fps": 30, "timeline": [{"scene_id": "...", "start_frame": 0, "duration_frames": 150, "duration_seconds": 5}], "total_frames": 150}
Chỉ JSON."""

S2_7_QA_FIX = """Tạo QA fix report ngắn.
Trả JSON: {"issues": [], "patches": [], "status": "passed"}
Chỉ JSON."""

S2_8_FINAL_PACKAGING = """Tạo publish manifest ngắn.
Trả JSON: {"status": "ready", "artifacts": []}
Chỉ JSON."""
