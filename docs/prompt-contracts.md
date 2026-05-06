# Prompt Contracts - PDF -> Workflow -> Video AI Pipelines

Last updated: 2026-05-06

## 1) Mục tiêu tài liệu
Tài liệu này chuẩn hoá **system prompt**, **input/output contract**, **error format**, và **artifact path** cho toàn bộ luồng AI:
1. AI Pass 1: PDF -> structured data theo chunk-by-chunk.
2. Screen planning: structured data -> screen plan.
3. Workflow composition + validation theo chunk-by-chunk.
4. AI Pass 2: tách nhỏ theo step để tạo video ổn định, có checkpoint/resume.

Áp dụng cùng các quy tắc trong `AGENTS.md`, `PROJECT_PLAN.md`, `plans/03-pdf-to-workflow-pipeline.md`, `plans/04-ai-video-generation-pipeline.md`.

---

## 2) Prompt Contract chung (áp dụng cho mọi step AI)

### 2.1 Role chuẩn
- System role phải mô tả rõ: "Bạn là AI xử lý báo cáo giao ban BHXH, ưu tiên tính đúng dữ liệu, tuyệt đối không bịa số."
- Cấm tạo dữ liệu ngoài nguồn input đã cấp.
- Luôn trả output đúng schema chỉ định.
- Trả duy nhất JSON hợp lệ, không markdown, không giải thích ngoài schema.

### 2.2 LLM response robustness contract
LLM client hiện tại phải được plan/prompt hỗ trợ các đặc điểm sau:
- API OpenAI-compatible, default URL `http://10.48.240.50:20128/v1`.
- Có thể fetch models từ endpoint `/models`.
- Có thể parse response `text/event-stream` hoặc dòng `data:`.
- Strip thinking tags trước khi parse JSON.
- Retry parse JSON khi response lỗi format.

Prompt nên nhắc rõ model trả JSON thuần để giảm lỗi parsing.

### 2.3 Input envelope chuẩn
```json
{
  "job_context": {
    "job_id": "{{job_id}}",
    "report_month": "{{YYYYMM}}",
    "step_id": "{{step_id}}",
    "attempt": 1
  },
  "input_artifacts": {
    "source": ["{{relative_path_1}}", "{{relative_path_2}}"],
    "payload": {}
  },
  "runtime_policy": {
    "timeout_seconds": 120,
    "max_retry": 3,
    "strict_json": true,
    "chunk_cache_enabled": true
  }
}
```

### 2.4 Output envelope chuẩn
```json
{
  "status": "DONE|PARTIAL|FAILED",
  "step_id": "{{step_id}}",
  "data": {},
  "warnings": [],
  "citations": [],
  "validation": {
    "schema_version": "v1",
    "passed": true,
    "errors": []
  }
}
```

### 2.5 Citation/mapping bắt buộc
- Mọi số liệu quan trọng phải có mapping về nguồn PDF:
  - `page_no`
  - `source_snippet`
  - `confidence` (0..1)
- Không xác định được nguồn thì set vào `warnings[]`, không tự suy diễn.

### 2.6 Quy tắc chống bịa số liệu
1. Chỉ dùng số có trong input artifact.
2. Không nội suy khi thiếu số liệu.
3. Nếu thiếu dữ liệu bắt buộc: trả `status=PARTIAL` hoặc `FAILED` theo mức độ.
4. Tách rõ dữ liệu gốc và dữ liệu suy luận (nếu có), mặc định **không suy luận**.

### 2.7 Error format chuẩn
```json
{
  "status": "FAILED",
  "step_id": "{{step_id}}",
  "error": {
    "error_code": "SCHEMA_VALIDATION_ERROR|MISSING_REQUIRED_DATA|LOW_CONFIDENCE|TIMEOUT|UPSTREAM_UNAVAILABLE|CHUNK_PROCESSING_FAILED",
    "error_message": "Mô tả lỗi ngắn gọn, có thể hành động",
    "retryable": true,
    "details": {}
  }
}
```

---

## 3) AI Pass 1 - PDF Analysis & Structured Extraction

### 3.1 Step P1.1 - Chunk extraction (`P1_1_CHUNK_EXTRACTION`)
**Input chính**: một chunk text/table từ parser, kèm `chunk_index`, `total_chunks`, page ranges nếu có.

**Runtime contract bắt buộc**:
- P1.1 chạy qua `ChunkProcessor` trong `app/core/chunk_processor.py`.
- Mỗi chunk thành công được ghi cache JSON riêng trước khi chuyển chunk tiếp theo.
- Khi resume, chunk cache hợp lệ được skip.
- Chỉ retry chunk lỗi/chưa có cache, không chạy lại toàn bộ P1.1.
- Sau khi tất cả chunk DONE, merge thành `parsed/extracted-report.json`.

**System prompt mẫu**:
> Bạn là chuyên gia phân tích báo cáo giao ban bằng tiếng Việt. Đây là MỘT PHẦN của báo cáo (chunk {{chunk_index}}/{{total_chunks}}). Nhiệm vụ: đọc dữ liệu đã trích từ phần này, tìm tất cả số liệu, metrics, bảng và các phần diễn giải quan trọng. Không bịa số liệu. Mỗi metric phải có metric_key, metric_name, value, unit, source_snippet, page_no, confidence. Nếu thiếu dữ liệu hoặc ngữ cảnh nằm ở chunk khác, ghi vào warnings. Trả về duy nhất 1 JSON object hợp lệ, không markdown.

**Input schema lõi cho một chunk**:
```json
{
  "chunk_index": 0,
  "total_chunks": 5,
  "page_start": 1,
  "page_end": 2,
  "text": "string",
  "tables": []
}
```

**Output schema lõi cho một chunk**:
```json
{
  "report_metadata": {
    "title": "string|null",
    "period": "YYYY-MM|null",
    "organization": "string|null"
  },
  "metrics": [
    {
      "metric_key": "string",
      "metric_name": "string",
      "value": "number|string",
      "unit": "string",
      "comparison": {
        "type": "yoy|mom|plan_ratio|none",
        "value": "number|null",
        "unit": "percent|ratio|none"
      },
      "citations": [
        {
          "page_no": 1,
          "source_snippet": "string",
          "confidence": 0.0
        }
      ]
    }
  ],
  "sections": [
    {
      "section_key": "string",
      "summary": "string",
      "citations": []
    }
  ],
  "warnings": []
}
```

**Artifact output**:
- `outputs/YYYYMM/<job_id>/parsed/chunks/chunk_000.json`
- `outputs/YYYYMM/<job_id>/parsed/chunks/chunk_001.json`
- `outputs/YYYYMM/<job_id>/parsed/extracted-report.json`
- `outputs/YYYYMM/<job_id>/parsed/extracted-report.validation.json`

### 3.2 Step P1.1b - Screen planning (`P1_1B_SCREEN_PLANNING`)
**Input chính**:
- `parsed/extracted-report.json`
- report metadata/job context

**System prompt mẫu**:
> Bạn là AI lập kế hoạch video báo cáo. Dựa vào extracted report đã có, hãy đề xuất danh sách screens/frames cho video. Mỗi screen cần screen_id, screen_type, title, data_keys, visual_type, tts_text_draft. BẮT BUỘC screen đầu tiên là intro và screen cuối cùng là closing. Tối thiểu 4 screens, tối đa 12 screens. Không thêm số liệu không có trong extracted report. Trả JSON: {"screens": [...]}.

**Output schema lõi**:
```json
{
  "screens": [
    {
      "screen_id": "screen_intro",
      "screen_type": "intro|content|closing",
      "title": "string",
      "data_keys": ["metric_key"],
      "visual_type": "title_card|kpi_card|bar_chart|line_chart|table|summary_card|closing_card",
      "tts_text_draft": "string",
      "validation": {
        "source_mapping_ok": true,
        "no_new_numbers": true
      }
    }
  ],
  "warnings": []
}
```

**Validation bắt buộc**:
- `screens[0].screen_type` là `intro` hoặc `screens[0].screen_id` thể hiện intro.
- `screens[-1].screen_type` là `closing` hoặc `screens[-1].screen_id` thể hiện closing.
- Mỗi `data_keys[]` phải trỏ về metric/section hợp lệ trong extracted report, trừ intro/closing.
- Không thêm số liệu ngoài extracted report.

**Artifact output**:
- `outputs/YYYYMM/<job_id>/parsed/screen-plan.json`

### 3.3 Step P1.2 - Workflow composition chunk-by-chunk
**Input chính**:
- `parsed/extracted-report.json`
- `parsed/screen-plan.json`
- template `workflow.md`

**Runtime contract bắt buộc**:
- P1.2 được phép chia metrics/sections thành chunks nhưng luôn truyền screen plan cho từng chunk.
- Mỗi workflow chunk thành công ghi cache JSON riêng.
- Resume skip workflow chunk đã done.
- Merge workflow chunks phải dedupe `scene_id` và giữ đúng intro/closing.

**System prompt mẫu**:
> Bạn là AI composer workflow video báo cáo. Hãy tạo workflow máy đọc theo đúng template chuẩn, dùng dữ liệu từ extracted-report.json và screen-plan.json. BẮT BUỘC có đúng 1 scene intro ở đầu video (`scene_type=intro`) và đúng 1 scene closing ở cuối video (`scene_type=closing`). Các scene còn lại là `scene_type=content` và số lượng scene content không cố định cứng. Mỗi scene phải map `source_data_keys` về metric_key tương ứng (riêng intro/closing có thể để rỗng). Không chèn số liệu không có trong dữ liệu đầu vào. TTS phải là tiếng Việt rõ nghĩa, ưu tiên mở rộng từ viết tắt; scene closing có thể tắt TTS (`tts.enabled=false`). Trả JSON workflow object đúng schema.

**Output schema lõi**:
```json
{
  "workflow_metadata": {
    "template_version": "wf.v2",
    "report_month": "YYYYMM",
    "job_id": "string"
  },
  "video_settings": {
    "fps": 30,
    "resolution": "1920x1080",
    "aspect_ratio": "16:9"
  },
  "scenes": [
    {
      "scene_id": "scene_intro",
      "scene_type": "intro|content|closing",
      "title": "string",
      "objective": "string",
      "source_data_keys": ["metric_key_1"],
      "visual_layers": [],
      "motion": {},
      "tts": {
        "enabled": true,
        "text": "string",
        "voice": "vi-VN-NamMinhNeural"
      },
      "duration_policy": {
        "mode": "tts_first|fixed",
        "min_seconds": 4,
        "max_seconds": 20,
        "buffer_seconds": 0.4
      },
      "validation": {
        "required_fields_ok": true,
        "source_mapping_ok": true,
        "tts_non_empty_or_disabled": true
      }
    }
  ]
}
```

**Artifact output**:
- `outputs/YYYYMM/<job_id>/workflow/chunks/chunk_000.json`
- `outputs/YYYYMM/<job_id>/workflow/chunks/chunk_001.json`
- `outputs/YYYYMM/<job_id>/workflow/workflow-<YYYYMM>-<job_id>.json`
- `outputs/YYYYMM/<job_id>/workflow/workflow-<YYYYMM>-<job_id>.md`

### 3.4 Step workflow validation
**System prompt mẫu**:
> Bạn là AI validator workflow video. Kiểm tra workflow theo rule: đủ field bắt buộc, scene_id không trùng, source_data_keys đều tồn tại trong extracted-report.json (intro/closing cho phép rỗng), duration policy hợp lệ, không có số liệu lạ không citation. BẮT BUỘC có đúng 1 intro (`scene_type=intro`) ở scene đầu tiên và đúng 1 closing (`scene_type=closing`) ở scene cuối cùng; nếu thiếu/sai vị trí phải fail. Với TTS: scene có `tts.enabled=true` thì `tts.text` bắt buộc không rỗng, scene có `tts.enabled=false` thì cho phép rỗng. Trả report JSON gồm pass/fail và danh sách lỗi có thể sửa.

**Output schema lõi**:
```json
{
  "passed": true,
  "errors": [
    {
      "code": "MISSING_FIELD|INVALID_SOURCE_KEY|EMPTY_TTS|DURATION_POLICY_INVALID|UNSUPPORTED_VISUAL_TYPE|INTRO_COUNT_INVALID|INTRO_POSITION_INVALID|CLOSING_COUNT_INVALID|CLOSING_POSITION_INVALID|DUPLICATE_SCENE_ID",
      "scene_id": "scene_intro",
      "message": "string",
      "severity": "ERROR|WARN"
    }
  ],
  "suggested_fixes": []
}
```

**Artifact output**:
- `outputs/YYYYMM/<job_id>/workflow/workflow-validation.json`

---

## 4) AI Pass 2 - Video generation theo 8 sub-step tuần tự

> Mỗi step có timeout/retry/checkpoint riêng; chỉ chạy step kế tiếp khi step trước `DONE`.

### S2.1 Scene Planning
- Input: workflow JSON validated.
- Output: scene execution plan chi tiết shot-level.
- Artifact: `remotion/scene-plan.json`.
- System prompt tóm tắt: lập shot plan theo từng scene, bảo toàn `source_data_keys`, không thêm số liệu mới; bắt buộc giữ intro ở đầu timeline và closing ở cuối timeline.

### S2.2 Visual Spec
- Input: scene plan.
- Output: visual spec (chart type, color token, layout blocks).
- Artifact: `remotion/visual-spec.json`.
- System prompt tóm tắt: chọn visual phù hợp từng metric, khai báo layer machine-readable.

### S2.3 TTS Script
- Input: scene plan + workflow tts draft.
- Output: tts final per scene, chuẩn phát âm viết tắt.
- Artifact: `tts/tts-script.json`.
- System prompt tóm tắt: chuẩn hoá câu đọc tiếng Việt, giữ nguyên số liệu, không đổi nghĩa.

#### S2.3 edge-tts mode
- Default engine: `edge-tts` chạy local, không cần API key.
- Default voice: `vi-VN-NamMinhNeural`.
- Input TTS mỗi scene phải có tối thiểu: `scene_id`, `tts.enabled`, `tts.text`, `tts.voice`.
- Khi `tts.enabled=true`, `tts.text` bắt buộc không rỗng và là tiếng Việt đã chuẩn hoá phát âm viết tắt.
- Khi `tts.enabled=false`, bỏ qua sinh audio và cho phép `tts.text` rỗng.
- Artifact `tts/tts-script.json` phải ghi rõ engine, voice, scripts và manifest audio sinh ra.
- Nếu edge-tts lỗi môi trường/mạng, runtime được phép chuyển sang fallback API TTS ngoài khi cấu hình có URL + key; nếu không có fallback thì trả lỗi retryable theo retry policy.

**Output tối thiểu cho edge-tts mode**:
```json
{
  "engine": "edge-tts",
  "default_voice": "vi-VN-NamMinhNeural",
  "scripts": [
    {
      "scene_id": "scene_intro",
      "enabled": true,
      "text": "Xin chào, đây là báo cáo giao ban tháng 03 năm 2026.",
      "voice": "vi-VN-NamMinhNeural"
    }
  ],
  "tts_manifest": {
    "engine": "edge-tts",
    "audio_files": [
      {
        "scene_id": "scene_intro",
        "path": "tts/scene_intro.mp3",
        "voice": "vi-VN-NamMinhNeural",
        "duration_seconds": 4.2
      }
    ]
  },
  "warnings": []
}
```

### S2.4 Component Spec
- Input: scene plan + visual spec + tts script.
- Output: component manifest cho Remotion.
- Artifact: `remotion/component-spec.json`.
- System prompt tóm tắt: xuất danh sách component props đủ để render deterministic.

### S2.5 Asset Plan
- Input: component spec.
- Output: danh sách asset cần tạo/lấy (icons, charts, background, font).
- Artifact: `remotion/asset-plan.json`.
- System prompt tóm tắt: không dùng asset vi phạm bản quyền, ưu tiên asset local/cache.

### S2.6 Render Plan
- Input: tts duration probe + component spec.
- Output: timeline sau sync audio, render plan preview/final.
- Artifact: `remotion/render-plan.json`.
- System prompt tóm tắt: timeline theo nguyên tắc TTS-first, buffer nhỏ giữa scene.

### S2.7 QA Fix
- Input: preview report + validation logs.
- Output: danh sách lỗi sync/visual/text và fix patches.
- Artifact: `remotion/qa-fix.json`.
- System prompt tóm tắt: phát hiện drift audio/text, overlap layer, overflow text.

### S2.8 Final Packaging
- Input: final render outputs + metadata.
- Output: publish manifest.
- Artifact:
  - `final/video.mp4`
  - `final/publish-manifest.json`
- System prompt tóm tắt: xác nhận đủ artifact cuối, checksum, trạng thái phát hành local.

---

## 5) Input/Output schema tối thiểu cho mọi step S2.x

### 5.1 Input schema
```json
{
  "job_context": {
    "job_id": "string",
    "report_month": "YYYYMM",
    "step_id": "S2.x",
    "attempt": 1
  },
  "upstream": {
    "required_artifacts": ["relative/path.json"],
    "payload": {}
  }
}
```

### 5.2 Output schema
```json
{
  "status": "DONE|PARTIAL|FAILED",
  "step_id": "S2.x",
  "artifacts": ["relative/path.json"],
  "data": {},
  "warnings": [],
  "error": null
}
```

---

## 6) Chính sách timeout/retry/checkpoint gợi ý
- Timeout mặc định theo step AI text: cấu hình qua runtime policy.
- Step render/asset nặng: cấu hình riêng nếu cần.
- Retry: `max_retry` từ runtime policy, backoff theo `RetryPolicy`.
- Sau mỗi step `DONE` ghi checkpoint vào:
  - `outputs/YYYYMM/<job_id>/job_state.json`
  - `outputs/YYYYMM/<job_id>/logs/job-events.ndjson`
- Với P1.1/P1.2, checkpoint cấp step kết hợp cache cấp chunk.

---

## 7) Checklist tích hợp vào code
1. Mỗi prompt để dưới dạng hằng số/template riêng theo step.
2. Validate JSON response bằng `pydantic` trước khi ghi artifact.
3. Ghi `error_code` chuẩn để hỗ trợ retry có điều kiện.
4. Không cho step kế tiếp chạy nếu upstream artifact chưa hợp lệ.
5. Có fixture test cho 3 case: đủ dữ liệu, thiếu dữ liệu, lệch schema.
6. Có test chunk resume cho P1.1/P1.2: chunk done được skip, chunk lỗi được retry.
7. Có test prompt P1.1b bắt buộc intro/closing.
8. Không log API key hoặc token-like text.
