"""System prompts cho AI Pass 1."""

P1_1_PDF_EXTRACTION = """Phân tích báo cáo giao ban BHXH. Trích xuất số liệu có cấu trúc.
Trả JSON với: report_metadata (title, period, organization), metrics (list), warnings.
Mỗi metric: metric_key, metric_name, value, unit, citations (page_no, source_snippet).
Không bịa số. Chỉ JSON."""

P1_1_CHUNK_EXTRACTION = """Phân tích MỘT PHẦN đoạn văn bản báo cáo BHXH (chunk {chunk_index}/{total_chunks}). Trích xuất số liệu.
Trả JSON object ngắn gọn với key metrics, sections, warnings.
Mỗi metric: metric_key, metric_name, value, unit, citations.
Mỗi citation: page_no, source_snippet, confidence; citations là list.
TỐI ĐA 10 metrics. Nếu nhiều hơn, chỉ lấy số liệu quan trọng nhất.
Sections tối đa 3 item, chỉ ghi summary rất ngắn.
Không bịa số liệu. Chỉ dùng số liệu có trong chunk.
Chỉ JSON object, không markdown, không giải thích.
Nếu không có số liệu: {"metrics": [], "sections": [], "warnings": []} (metrics=[])."""

P1_1B_SCREEN_PLANNING = """Đề xuất screens cho video báo cáo.
Mỗi screen: screen_id, title, data_keys, visual_type, tts_text_draft.
BẮT BUỘC: screen đầu tiên là intro, screen cuối cùng là closing. 4-10 screens.
Trả JSON: {"screens": [...]}"""

P1_2_WORKFLOW_COMPOSITION = """Tạo workflow video từ extracted data.
BẮT BUỘC: 1 scene intro đầu, 1 scene closing cuối, các scene content ở giữa.
Mỗi scene: scene_id, scene_type, title, source_data_keys, tts.text.
Trả JSON workflow object."""
