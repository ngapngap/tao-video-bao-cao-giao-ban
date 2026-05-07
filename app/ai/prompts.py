"""System prompts cho AI Pass 1."""

P1_1_PDF_EXTRACTION = """Phân tích báo cáo giao ban BHXH. Trích xuất số liệu có cấu trúc.
Trả JSON với: report_metadata (title, period, organization), metrics (list), warnings.
Mỗi metric: metric_key, metric_name, value, unit, citations (page_no, source_snippet).
Không bịa số. Chỉ JSON."""

P1_1_CHUNK_EXTRACTION = """Phân tích MỘT PHẦN đoạn văn bản báo cáo BHXH (chunk {chunk_index}/{total_chunks}). Trích xuất TẤT CẢ số liệu có cấu trúc.
Trả JSON object với key metrics, sections, warnings; metrics=[] nếu không có số liệu.
Mỗi metric: metric_key, metric_name, value, unit, page_no, source_snippet, citations.
Mỗi citation: page_no, source_snippet, confidence; citations là list.
Với chunks nhỏ 1500 chars, ưu tiên trích xuất đầy đủ mọi số liệu trong chunk, không giới hạn số metric/chunk.
Sections ghi các phần diễn giải quan trọng liên quan đến số liệu trong chunk.
Không bịa số liệu. Chỉ dùng số liệu có trong chunk.
Chỉ JSON object, không markdown, không giải thích."""

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
