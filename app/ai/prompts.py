"""System prompts cho AI Pass 1."""

P1_1_PDF_EXTRACTION = """Phân tích báo cáo giao ban BHXH. Trích xuất số liệu có cấu trúc.
Trả JSON với: report_metadata (title, period, organization), metrics (list), warnings.
Mỗi metric: metric_key, metric_name, value, unit, citations (page_no, source_snippet).
Không bịa số. Chỉ JSON."""

P1_1_CHUNK_EXTRACTION = """Phân tích MỘT PHẦN văn bản báo cáo giao ban BHXH: chunk {chunk_index}/{total_chunks}.
Mục tiêu: trích xuất số liệu thật từ đúng phần văn bản được cung cấp, hỗ trợ cache/resume theo chunk.
Không bịa số liệu, không suy diễn ngoài nội dung chunk; nếu chunk không có số liệu hợp lệ thì trả metrics=[].
Trả JSON object thuần gồm: report_metadata, metrics, sections, warnings.
Mỗi metric có: metric_key, metric_name, value, unit, citations.
citations là list; mỗi citation có page_no, source_snippet, confidence.
TỐI ĐA 8 metrics. Chỉ JSON, không markdown, ngắn gọn."""

P1_1B_SCREEN_PLANNING = """Đề xuất screens cho video báo cáo.
Mỗi screen: screen_id, title, data_keys, visual_type, tts_text_draft.
BẮT BUỘC: screen đầu tiên là intro, screen cuối cùng là closing. 4-10 screens.
Trả JSON: {"screens": [...]}"""

P1_2_WORKFLOW_COMPOSITION = """Tạo workflow video từ screen plan và extracted data.
YÊU CẦU QUAN TRỌNG:
- Trả JSON workflow, KHÔNG markdown, KHÔNG giải thích.
- Mỗi scene chỉ cần: scene_id, scene_type, title, source_data_keys, tts (text + enabled), duration_policy.
- KHÔNG cần visual_layers, motion, position chi tiết - sẽ tạo sau.
- Giữ intro ở đầu, closing ở cuối.
- Tối đa 8 scenes.
Trả JSON object hợp lệ."""
