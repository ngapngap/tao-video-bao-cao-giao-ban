# workflow.md - Template workflow máy đọc cho pipeline tạo video

## 1) Metadata
```yaml
template_version: "wf.v2"
workflow_id: "{{workflow_id}}"
job_id: "{{job_id}}"
report_month: "{{report_month_yyyymm}}"
language: "vi-VN"
created_at: "{{iso_datetime}}"
source_pdf_name: "{{source_pdf_name}}"
source_pdf_hash: "{{source_pdf_sha256}}"
owner_org: "{{owner_org}}"
```

## 2) Input assumptions
- Input đã qua bước parse PDF và chuẩn hóa số liệu.
- Dữ liệu nguồn chính nằm tại `outputs/{{report_month_yyyymm}}/{{job_id}}/parsed/extracted-report.json`.
- Tất cả số liệu trong scene phải truy vết được qua `source_data_keys`.
- Không chèn số liệu ngoài dữ liệu đã trích xuất.

## 3) Data contract từ PDF (tham chiếu máy đọc)
```yaml
data_contract:
  extracted_report_schema_version: "v1"
  required_keys:
    - report_metadata.title
    - report_metadata.period
    - metrics[]
  metric_item_fields:
    - metric_key
    - metric_name
    - value
    - unit
    - comparison
    - citations[]
  citation_required_fields:
    - page_no
    - source_snippet
    - confidence
```

## 4) Video global settings
```yaml
video_settings:
  fps: 30
  resolution:
    width: 1920
    height: 1080
  aspect_ratio: "16:9"
  safe_margin_px: 64
  style_preset: "{{style_preset}}"
  brand:
    logo_path: "{{logo_path_or_empty}}"
    primary_color: "{{primary_color_hex}}"
    secondary_color: "{{secondary_color_hex}}"
  audio:
    tts_first: true
    default_voice: "vi-VN-NamMinhNeural"
    sample_rate: 24000
```

## 5) Scene/frame schema bắt buộc

Mỗi scene **bắt buộc** theo schema sau:

```yaml
scene:
  scene_id: "SC{{nnn}}"
  scene_type: "intro|content|closing"
  title: "{{scene_title}}"
  objective: "{{scene_objective}}"
  source_data_keys:
    - "{{metric_key_1}}"
    - "{{metric_key_2}}"
  visual_layers:
    - layer_id: "{{layer_id}}"
      type: "chart|table|kpi|text|icon|image|background"
      data_key: "{{metric_key_or_empty}}"
      content_template: "{{content_template_or_empty}}"
      position:
        x: "{{x}}"
        y: "{{y}}"
        w: "{{w}}"
        h: "{{h}}"
      style_token: "{{style_token}}"
      priority: 1
  motion:
    preset: "fade_in|slide_up|grow|none"
    duration_ms: 800
    easing: "easeOutCubic"
  tts:
    enabled: true
    text: "{{tts_text_vi_or_empty}}"
    normalize_abbreviation: true
    voice: "{{voice_name}}"
  duration_policy:
    mode: "tts_first|fixed"
    min_seconds: 4
    max_seconds: 24
    buffer_seconds: 0.4
  validation:
    required_fields_ok: true
    source_mapping_ok: true
    tts_non_empty_or_disabled: true
    visual_non_empty: true
```

### 5.1) Validation rules bắt buộc (workflow-level)

```yaml
workflow_validation_rules:
  - code: "INTRO_COUNT_EXACTLY_ONE"
    rule: "Có đúng 1 scene_type=intro trong toàn bộ workflow"
  - code: "INTRO_MUST_BE_FIRST"
    rule: "Scene đầu tiên (index 0) bắt buộc là intro"
  - code: "CLOSING_COUNT_EXACTLY_ONE"
    rule: "Có đúng 1 scene_type=closing trong toàn bộ workflow"
  - code: "CLOSING_MUST_BE_LAST"
    rule: "Scene cuối cùng (index cuối) bắt buộc là closing"
```

## 6) Danh sách scenes (template)

> Lưu ý bắt buộc:
> - Không cố định cứng tổng số scene là 10; số scene nội dung được phép thay đổi theo dữ liệu thực tế.
> - `scene_intro` phải là scene đầu tiên.
> - `scene_closing` phải là scene cuối cùng.

```yaml
scenes:
  - scene_id: "SC001"
    scene_type: "intro"
    title: "{{scene_intro_title}}"
    objective: "Giới thiệu video báo cáo kỳ {{report_period_label}} của {{owner_org_display_name}}"
    source_data_keys: []
    visual_layers:
      - layer_id: "L1"
        type: "text"
        data_key: ""
        content_template: "{{report_title}}"
        position: { x: 96, y: 120, w: 1728, h: 220 }
        style_token: "headline"
        priority: 1
      - layer_id: "L2"
        type: "text"
        data_key: ""
        content_template: "Kỳ báo cáo: {{report_period_label}}"
        position: { x: 96, y: 360, w: 1728, h: 100 }
        style_token: "subhead"
        priority: 2
      - layer_id: "L3"
        type: "text"
        data_key: ""
        content_template: "Đơn vị: {{owner_org_display_name}}"
        position: { x: 96, y: 480, w: 1728, h: 100 }
        style_token: "subhead"
        priority: 3
    motion: { preset: "fade_in", duration_ms: 900, easing: "easeOutCubic" }
    tts:
      enabled: true
      text: "{{scene_intro_tts}}"
      normalize_abbreviation: true
      voice: "vi-VN-NamMinhNeural"
    duration_policy: { mode: "tts_first", min_seconds: 5, max_seconds: 18, buffer_seconds: 0.4 }
    validation: { required_fields_ok: true, source_mapping_ok: true, tts_non_empty_or_disabled: true, visual_non_empty: true }

  - scene_id: "SC{{content_seq}}"
    scene_type: "content"
    title: "{{scene_content_title}}"
    objective: "{{scene_content_objective}}"
    source_data_keys:
      - "{{metric_key_x}}"
    visual_layers: []
    motion: { preset: "slide_up", duration_ms: 850, easing: "easeOutCubic" }
    tts:
      enabled: true
      text: "{{scene_content_tts}}"
      normalize_abbreviation: true
      voice: "vi-VN-NamMinhNeural"
    duration_policy: { mode: "tts_first", min_seconds: 5, max_seconds: 22, buffer_seconds: 0.5 }
    validation: { required_fields_ok: true, source_mapping_ok: true, tts_non_empty_or_disabled: true, visual_non_empty: true }

  - scene_id: "SC{{last_seq}}"
    scene_type: "closing"
    title: "{{scene_closing_title}}"
    objective: "Tổng kết và thông điệp kết thúc"
    source_data_keys: []
    visual_layers:
      - layer_id: "L1"
        type: "text"
        data_key: ""
        content_template: "{{closing_message}}"
        position: { x: 120, y: 380, w: 1680, h: 220 }
        style_token: "headline"
        priority: 1
      - layer_id: "L2"
        type: "text"
        data_key: ""
        content_template: "{{closing_signature_or_unit}}"
        position: { x: 120, y: 640, w: 1680, h: 100 }
        style_token: "subhead"
        priority: 2
    motion: { preset: "fade_in", duration_ms: 900, easing: "easeOutCubic" }
    tts:
      enabled: false
      text: ""
      normalize_abbreviation: true
      voice: "vi-VN-NamMinhNeural"
    duration_policy: { mode: "fixed", min_seconds: 4, max_seconds: 10, buffer_seconds: 0.0 }
    validation: { required_fields_ok: true, source_mapping_ok: true, tts_non_empty_or_disabled: true, visual_non_empty: true }
```

## 7) TTS-first & timeline sync rules
1. Bắt buộc sinh TTS cho từng scene trước khi chốt timeline.
2. Đo duration thực tế từng file audio (`scene_id.mp3`).
3. Duration scene = duration audio + `buffer_seconds` (0.2-0.6s), không kéo dài vô lý.
4. Nếu TTS vượt `max_seconds`, phải rút gọn câu chữ hoặc tách scene.
5. Không render final khi chưa pass kiểm tra sync audio-video.

## 8) Remotion handoff requirements

```yaml
remotion_handoff:
  required_files:
    - "workflow/workflow-{{report_month_yyyymm}}-{{job_id}}.json"
    - "remotion/scene-plan.json"
    - "remotion/visual-spec.json"
    - "remotion/component-spec.json"
    - "remotion/render-plan.json"
    - "tts/tts-script.json"
  render_inputs:
    composition_id: "{{composition_id}}"
    fps: 30
    width: 1920
    height: 1080
    audio_tracks:
      - "tts/{{scene_id}}.mp3"
```

## 9) Output checklist (máy đọc)
- [ ] Có đủ metadata và template_version.
- [ ] Tất cả scene có `scene_id` duy nhất.
- [ ] Tất cả scene có `tts.text` không rỗng.
- [ ] `source_data_keys` map được về `extracted-report.json` (trừ scene intro/outro cho phép rỗng có chú thích).
- [ ] Không có số liệu hard-code kỳ cũ trong template.
- [ ] Có thể chuyển đổi 1-1 sang JSON để Remotion tiêu thụ.

## 10) Placeholder convention
- Mọi biến động theo kỳ báo cáo dùng placeholder dạng `{{field_name}}`.
- Tên placeholder viết `snake_case`, không dấu.
- Ví dụ:
  - `{{report_month_yyyymm}}`
  - `{{metric_key_a}}`
  - `{{scene_2_tts}}`
  - `{{primary_color_hex}}`
