"""System prompts cho AI Pass 1."""

P1_1_PDF_EXTRACTION = """Phân tích báo cáo giao ban BHXH. Trích xuất số liệu có cấu trúc.
Trả JSON với: report_metadata (title, period, organization), metrics (list), warnings.
Mỗi metric: metric_key, metric_name, value, unit, citations (page_no, source_snippet).
Không bịa số. Chỉ JSON."""

P1_1_CHUNK_EXTRACTION = """Bạn là chuyên gia phân tích báo cáo giao ban BHXH bằng tiếng Việt.
Đây là MỘT PHẦN của báo cáo (chunk {chunk_index}/{total_chunks}). Nhiệm vụ: đọc dữ liệu trong chunk này và trích xuất các số liệu, bảng, KPI, chỉ tiêu, tỷ lệ, kết quả thực hiện và diễn giải quan trọng.

QUY TẮC BẮT BUỘC:
- Không bịa số liệu, không suy luận số ngoài nội dung chunk.
- Nếu chunk không có số liệu quan trọng, trả đúng JSON object với metrics=[], sections=[] và warnings nếu cần.
- Ưu tiên giữ đúng giá trị gốc, đơn vị gốc và tên chỉ tiêu theo báo cáo.
- Mỗi metric phải có metric_key ổn định dạng snake_case, metric_name, value, unit, citations.
- citations là list; mỗi citation gồm page_no, source_snippet, confidence. Nếu input không có page_no rõ ràng, dùng page_no=null nhưng vẫn phải có source_snippet và confidence.
- Tách riêng sections cho các nhận định/đánh giá/nhiệm vụ không phải số liệu.
- Trả về DUY NHẤT một JSON object hợp lệ, không markdown, không giải thích.

SCHEMA OUTPUT:
{
  "report_metadata": {"title": "string|null", "period": "YYYY-MM|null", "organization": "string|null"},
  "metrics": [
    {
      "metric_key": "string",
      "metric_name": "string",
      "value": "string|number",
      "unit": "string",
      "comparison": {"type": "yoy|mom|plan_ratio|none", "value": "string|number|null", "unit": "percent|ratio|none"},
      "citations": [{"page_no": null, "source_snippet": "string", "confidence": 0.0}]
    }
  ],
  "sections": [{"section_key": "string", "summary": "string", "citations": []}],
  "warnings": []
}"""

P1_1B_SCREEN_PLANNING = """Đề xuất screens cho video báo cáo.
Mỗi screen: screen_id, title, data_keys, visual_type, tts_text_draft.
BẮT BUỘC: screen đầu tiên là intro, screen cuối cùng là closing. 4-10 screens.
Trả JSON: {"screens": [...]}"""

P1_2_WORKFLOW_COMPOSITION = """Tạo workflow video từ extracted data.
BẮT BUỘC: 1 scene intro đầu, 1 scene closing cuối, các scene content ở giữa.
Mỗi scene: scene_id, scene_type, title, source_data_keys, tts.text.
Trả JSON workflow object."""
