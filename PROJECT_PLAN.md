# PROJECT_PLAN - tao-video-bao-cao-giao-ban

Last updated: 2026-05-06

## 1. Source of truth
Tài liệu điều phối chính của dự án là:
1. `PROJECT_PLAN.md` (master plan + status register + acceptance)
2. `plans/*.md` (kế hoạch thực thi theo phase)
3. `AGENTS.md` (quy tắc vận hành agent)
4. `docs/prompt-contracts.md` (prompt/schema AI khi đụng tới AI contracts)

`docs/*` còn lại là tài liệu tham khảo. Ưu tiên `PROJECT_PLAN.md` + `plans/*.md` khi có xung đột với tài liệu khác.

## 2. Mục tiêu dự án
Xây dựng ứng dụng Python desktop portable để:
- Import PDF báo cáo giao ban.
- Parse PDF bằng PyMuPDF, fallback pdfplumber.
- AI đọc dữ liệu số liệu/diễn giải và chuẩn hoá thành structured data theo chunk-by-chunk để tránh timeout/524.
- Lên kế hoạch screens trước khi sinh workflow.
- Sinh workflow máy đọc mới từ template `workflow.md`, có cache/resume theo chunk.
- Chạy pipeline AI thứ 2 theo nhiều bước con tuần tự để sinh video bằng Remotion workflow.
- Xuất video hoàn chỉnh (MP4) cho người dùng tải về.
- Phát hành bản portable có thể copy sang máy khác để chạy, không cần triển khai VPS/server.
- Hỗ trợ auto-updater từ GitHub Releases; hiện tại version/release codebase là `v0.2.0`.

## 3. Trạng thái điều phối hiện tại
- [x] Đã xác nhận yêu cầu nghiệp vụ từ `noidung.md`.
- [x] Đã xác nhận template workflow từ `workflow.md`.
- [x] Đã tạo GitHub private repo: `https://github.com/ngapngap/tao-video-bao-cao-giao-ban`.
- [x] Đã triển khai source code app desktop nền tảng.
- [x] Đã có 4 màn hình UI nền tảng: `Tạo video`, `Cấu hình`, `Job & Logs`, `Lịch sử`.
- [x] Đã có job engine checkpoint/resume/retry và event log NDJSON.
- [x] Đã có `ChunkProcessor` cho P1.1/P1.2 chunk-by-chunk.
- [x] Đã có LLM client robustness: SSE parser, thinking tag stripper, retry parse JSON, fetch models.
- [x] Đã có auto-updater và version `0.2.0`.
- [x] Đã có release `v0.2.0` theo context vận hành.
- [ ] Cần tiếp tục hardening E2E thật, portable verification và artifact evidence cho từng phase.

## 4. Tech stack triển khai thực tế
### 4.1 Desktop app
- Python 3.11+
- UI framework: `customtkinter`.
- Async/background jobs: `concurrent.futures`, background thread và queue nội bộ.

### 4.2 PDF & dữ liệu
- PDF parser chính: `pymupdf`.
- Fallback parser: `pdfplumber`.
- Schema validation: `pydantic`.
- Chunk cache/resume: `app/core/chunk_processor.py`.

### 4.3 AI gateway
- API kiểu OpenAI-compatible cho model đọc nội dung.
- Default LLM URL hiện tại: `http://10.48.240.50:20128/v1`.
- HTTP client: `httpx`.
- Model dropdown auto-fetch qua endpoint `/models` khi user click/focus dropdown.
- Có parser cho response `text/event-stream` hoặc stream dạng `data:`.
- Có stripper cho thinking tags trước khi parse JSON.
- Có retry parse JSON khi model trả format lỗi.

### 4.4 TTS Engine
- Default: edge-tts local (không cần API key).
- Fallback: API TTS ngoài (cần URL + key).
- Config: dropdown chọn engine trong màn hình Cấu hình.
- Default voice: `vi-VN-NamMinhNeural`.
- Issues: #39, #40, #41, #42.

### 4.5 Bảo mật key
- Ưu tiên `keyring` (Windows Credential Manager).
- Fallback: DPAPI qua `pywin32` hoặc backend an toàn tương đương.
- Không lưu plaintext trong file config, log, export hoặc repo.

### 4.6 Packaging & update
- `PyInstaller --onefile` cho bản portable.
- `app/version.py`: version hiện tại `0.2.0`, GitHub Releases endpoint.
- `app/updater.py`: kiểm tra release mới, chọn asset phù hợp nền tảng, tải và thay executable.
- Topbar có quick action `Kiểm tra cập nhật`.

## 5. Cấu trúc repo hiện tại
```text
app/
  main.py, updater.py, version.py
  ai/          # llm_client, prompts, schemas
  core/        # job_runner, checkpoint, retry_policy, event_logger, chunk_processor, models
  pdf/         # parser, normalizer
  workflow/    # composer, validator
  video/       # orchestrator, prompts, remotion_handoff
  security/    # credential_store
  ui/          # screens, sidebar, topbar, tokens, navigation
scripts/       # build.py, smoke_test.py, test_llm_extract.py
tests/         # 11 test files
```

## 6. Thiết kế UI cụ thể

Thiết kế UI chi tiết được chuẩn hoá trong [`design-system/bao-cao-giao-ban-video-generator/UI_SPEC.md`](design-system/bao-cao-giao-ban-video-generator/UI_SPEC.md). Agent triển khai UI phải đọc file này cùng [`design-system/bao-cao-giao-ban-video-generator/MASTER.md`](design-system/bao-cao-giao-ban-video-generator/MASTER.md) trước khi viết code nếu các file này có trong workspace.

### 6.1 Design system bắt buộc
- Phong cách: data-dense dashboard cho công cụ nội bộ, không landing page, không trang marketing.
- Palette chính: xanh dữ liệu `#1E40AF` + accent amber `#F59E0B` + nền `#F8FAFC`.
- Font: Fira Code/Fira Sans nếu bundle được; fallback Windows là Cascadia Mono/Segoe UI/Consolas.
- Component: card trắng, border rõ, status pill, timeline, log monospace; không dùng emoji làm icon chính.
- Desktop window default: `1280x820`, minimum `1100x720`.

### 6.2 App shell
- Sidebar trái 220px: `Tạo video`, `Cấu hình`, `Job & Logs`, `Lịch sử`.
- Top header 64px: tên màn hình, status tổng, quick actions `Mở outputs`, `Kiểm tra cập nhật`, `Cấu hình`.
- Content area dùng card/panel nhất quán theo token trong UI spec.

### 6.3 Screen `Tạo video`
Layout 12 cột:
- Trái 5 cột: input package.
- Phải 7 cột: readiness checklist + current job summary + mini timeline.

Bắt buộc có:
- PDF dropzone/chọn file với state empty/selected.
- `report_month` theo `YYYYMM`, ví dụ `202603`.
- `report_title`, `owner_org`, `workflow_template`, `output_root`, `profile`.
- Readiness checklist: PDF hợp lệ, tháng hợp lệ, workflow template hợp lệ, LLM ready, TTS ready, output writable.
- CTA `Start Job` màu amber, chỉ enable khi checklist pass.
- Current job card hiển thị `job_id`, `status`, `current_step`, `elapsed`, step progress, nút `Xem chi tiết`, `Resume`, `Mở output`.

### 6.4 Screen `Cấu hình`
Layout gồm 3 card chính và 1 status card:
- `LLM Model`: `url_model`, `apikey_model`, `default_model` dropdown auto-fetch, `credential_id_model`, `Test LLM`.
- `TTS Voice`: `url_tts`, `model_tts`, `apikey_tts`, `voice`, `credential_id_tts`, `Test TTS`.
- `Runtime policy`: `step_timeout_seconds`, `max_retry`, `retry_backoff_seconds`, `enable_resume`.
- `Config health`: last test, LLM/TTS result, secret storage mode.

LLM config UX bắt buộc:
- URL mặc định: `http://10.48.240.50:20128/v1`.
- Luồng nhập: URL -> Key -> Model dropdown.
- Dropdown model tự gọi `/models` khi click/focus nếu URL và key đã có.
- Nếu fetch lỗi hoặc không có model, cho phép nhập model thủ công.

Secret UX bắt buộc:
- API key luôn masked.
- Sau khi lưu không hiển thị lại key thật.
- Có `Thay key` và `Xoá key khỏi máy này`.
- Config file chỉ lưu credential id/reference.

### 6.5 Screen `Job & Logs`
Layout:
- Header job: `job_id`, `status`, actions `Resume`, `Retry failed step`, `Cancel`, `Open output`.
- Trái 320px: step timeline nhóm theo phase.
- Phải: tab `Logs`, `Artifacts`, `Job state JSON`.

Timeline row bắt buộc có:
- Step id/name/status/attempt/duration/last error short.
- Status colors: DONE green, RUNNING blue, WAITING_RETRY amber, FAILED red, PENDING slate.

Log panel bắt buộc có:
- Filter level All/Info/Warn/Error.
- Search text.
- Auto-scroll toggle.
- `Copy selected`, `Open log file`.
- Format row: `[HH:mm:ss] [LEVEL] [step_id] message`.
- Không in API key/token; token-like text phải mask.

Artifact panel bắt buộc có:
- Input PDF, extracted JSON, screen plan, workflow MD/JSON, chunk caches, TTS audio, Remotion manifest, preview render, final MP4.
- Mỗi artifact có `Open`, `Reveal`, `Copy path`.

### 6.6 Screen `Lịch sử`
Phase đầu có thể đơn giản nhưng phải có thiết kế sẵn:
- Table jobs theo tháng/job_id/status/PDF/duration/final video.
- Filters: month, status, keyword.
- Row actions: `Open detail`, `Open final video`, `Reveal output`, `Delete local job`.

### 6.7 UI acceptance bắt buộc
- Main screen có readiness checklist, không chỉ form nhập.
- Start Job disabled khi thiếu PDF/config/template/output.
- Config screen không bao giờ hiển thị lại API key thật sau khi lưu.
- LLM model dropdown auto-fetch khi click/focus và có fallback nhập thủ công.
- Topbar có `Mở outputs`, `Kiểm tra cập nhật`, `Cấu hình`.
- Job & Logs screen có timeline theo phase, log filter, artifact panel.
- Failed state có retry/resume rõ ràng.
- Screenshot 4 màn hình được lưu làm evidence phase 02.

Job states chuẩn:
`DRAFT -> QUEUED -> RUNNING -> WAITING_RETRY -> PARTIAL_DONE -> DONE | FAILED | CANCELED`

## 7. Workflow máy đọc (schema + naming)
### 7.1 Output path
`outputs/YYYYMM/<job_id>/...`

### 7.2 File naming
- `input/report-source.pdf`
- `parsed/pdf-text.json`
- `parsed/chunks/chunk_000.json`
- `parsed/extracted-report.json`
- `parsed/extracted-report.validation.json`
- `parsed/screen-plan.json`
- `workflow/chunks/chunk_000.json`
- `workflow/workflow-<YYYYMM>-<job_id>.md`
- `workflow/workflow-<YYYYMM>-<job_id>.json`
- `workflow/workflow-validation.json`
- `logs/job-events.ndjson`
- `job_state.json`

### 7.3 Schema đề xuất (rút gọn, đồng bộ `workflow.md`)
```json
{
  "job_id": "20260505-001",
  "report_month": "202603",
  "source_pdf": "outputs/202603/20260505-001/input/report-source.pdf",
  "extracted_data": {
    "report_metadata": {
      "title": "Báo cáo giao ban tháng 03/2026",
      "period": "2026-03",
      "organization": "BHXH ..."
    },
    "metrics": [],
    "sections": [],
    "warnings": []
  },
  "screen_plan": {
    "screens": [
      {
        "screen_id": "screen_intro",
        "screen_type": "intro",
        "title": "Giới thiệu báo cáo",
        "data_keys": [],
        "visual_type": "title_card",
        "tts_text_draft": "..."
      }
    ]
  },
  "workflow": {
    "workflow_metadata": {
      "template_version": "wf.v2",
      "job_id": "20260505-001",
      "report_month": "202603"
    },
    "video_settings": {
      "resolution": "1920x1080",
      "fps": 30,
      "aspect_ratio": "16:9"
    },
    "scenes": [
      {
        "scene_id": "scene_intro",
        "scene_type": "intro",
        "title": "Giới thiệu báo cáo",
        "objective": "Mở đầu video",
        "source_data_keys": [],
        "visual_layers": [],
        "motion": {},
        "tts": { "enabled": true, "text": "..." },
        "duration_policy": { "mode": "tts_first", "min_seconds": 4, "max_seconds": 12 }
      },
      {
        "scene_id": "scene_content_01",
        "scene_type": "content",
        "title": "...",
        "source_data_keys": ["metric_key"],
        "visual_layers": [],
        "motion": {},
        "tts": { "enabled": true, "text": "..." },
        "duration_policy": { "mode": "tts_first", "min_seconds": 5, "max_seconds": 20 }
      },
      {
        "scene_id": "scene_closing",
        "scene_type": "closing",
        "title": "Kết thúc",
        "source_data_keys": [],
        "visual_layers": [],
        "motion": {},
        "tts": { "enabled": false, "text": "" },
        "duration_policy": { "mode": "fixed", "min_seconds": 4, "max_seconds": 8 }
      }
    ]
  }
}
```

Validation bắt buộc:
- Screen plan có screen đầu tiên là intro và screen cuối cùng là closing.
- Đúng 1 scene `intro` và nằm đầu danh sách.
- Đúng 1 scene `closing` và nằm cuối danh sách.
- Mọi scene `content` có `source_data_keys` trỏ về metric/section hợp lệ, trừ khi là scene chuyển tiếp được đánh dấu rõ.
- Scene có `tts.enabled=true` phải có `tts.text` không rỗng; scene `tts.enabled=false` được phép không có lời đọc.

## 8. Pipeline tổng chuẩn hiện tại (15 steps)
> Lưu ý điều phối: danh sách có 14 step ID cố định, nhưng tài liệu gọi là pipeline 15 steps vì `P1.1` và `P1.2` là chunk-by-chunk gồm nhiều chunk runtime. Không quay lại mô hình 13 steps cũ.

| Step ID | Tên | Artifact chính | Ghi chú |
|---|---|---|---|
| `S1.1` | Chuẩn bị thư mục output | `outputs/YYYYMM/<job_id>/` | Tạo cấu trúc folder |
| `S1.2` | Copy PDF đầu vào | `input/report-source.pdf` | Không sửa PDF gốc |
| `S1.3` | Parse PDF | `parsed/pdf-text.json` | PyMuPDF + pdfplumber fallback |
| `P1.1` | Trích xuất dữ liệu | `parsed/chunks/*.json`, `parsed/extracted-report.json` | Chunk-by-chunk, cache/resume |
| `P1.1b` | Lên kế hoạch screens | `parsed/screen-plan.json` | Mới, trước workflow composition |
| `P1.2` | Sinh workflow | `workflow/chunks/*.json`, `workflow/*.json`, `workflow/*.md` | Chunk-by-chunk, cache/resume |
| `S2.1` | Scene planning | `remotion/scene-plan.json` | Video pass 2 |
| `S2.2` | Visual spec | `remotion/visual-spec.json` | Video pass 2 |
| `S2.3` | TTS script | `tts/tts-script.json` | Video pass 2 |
| `S2.4` | Component spec | `remotion/component-spec.json` | Video pass 2 |
| `S2.5` | Asset plan | `remotion/asset-plan.json` | Video pass 2 |
| `S2.6` | Render plan | `remotion/render-plan.json` | Video pass 2 |
| `S2.7` | QA fix | `remotion/qa-fix.json` | Video pass 2 |
| `S2.8` | Final packaging | `final/video.mp4`, `final/publish-manifest.json` | Video pass 2 |

## 9. Pipeline 1: PDF -> Structured Data -> Screen Plan -> Workflow mới
Bước tuần tự:
1. `S1.1` validate input & tạo job folder.
2. `S1.2` copy PDF gốc vào output.
3. `S1.3` parse PDF text + bảng, normalizer chuẩn hoá số liệu/ngày tháng.
4. `P1.1` chia text/table thành chunks, gọi LLM từng chunk với `P1_1_CHUNK_EXTRACTION`.
5. Mỗi chunk thành công ghi cache JSON riêng trước khi sang chunk tiếp theo.
6. Resume skip chunk đã done, chỉ retry chunk lỗi/chưa có cache hợp lệ.
7. Merge chunk results thành `parsed/extracted-report.json`.
8. `P1.1b` gọi LLM lập `parsed/screen-plan.json` từ extracted report.
9. `P1.2` chia workflow composition theo chunks metrics/sections + screen plan, cache/resume từng chunk.
10. Merge workflow chunks, dedupe scene, giữ intro/closing.
11. Sinh workflow mới `.md` + `.json`.
12. Validate workflow output.

Acceptance:
- Có file `parsed/extracted-report.json` hợp lệ schema.
- Có file `parsed/screen-plan.json`, screen đầu intro và screen cuối closing.
- Có file workflow mới trong `workflow/`.
- Có local test với fixture PDF mẫu hoặc test chunk pipeline ghi nhận kết quả.

## 10. Pipeline 2: AI video generation tách bước con tuần tự

## TTS Engine
- Default: edge-tts local (không cần API key)
- Fallback: API TTS ngoài (cần URL + key)
- Config: dropdown chọn engine trong màn hình Cấu hình
- Issues: #39, #40, #41, #42

Mục tiêu: tránh timeout/524 bằng cách chia nhỏ, mỗi step có system prompt/schema/artifact riêng theo `docs/prompt-contracts.md`.

Step breakdown chuẩn:
1. `S2.1_scene_planning` - tạo `remotion/scene-plan.json`, giữ intro đầu và closing cuối.
2. `S2.2_visual_spec` - tạo `remotion/visual-spec.json`, chọn chart/layout/layer theo metric.
3. `S2.3_tts_script` - tạo `tts/tts-script.json`, chuẩn hoá câu đọc tiếng Việt, không đổi số liệu.
4. `S2.4_component_spec` - tạo `remotion/component-spec.json`, khai báo component props deterministic.
5. `S2.5_asset_plan` - tạo `remotion/asset-plan.json`, liệt kê chart/icon/font/background/cache asset.
6. `S2.6_render_plan` - tạo `remotion/render-plan.json`, TTS-first, duration probe, timeline sync.
7. `S2.7_qa_fix` - tạo `remotion/qa-fix.json`, kiểm preview sync/overflow/text drift và patch nếu cần.
8. `S2.8_final_packaging` - tạo `final/video.mp4` + `final/publish-manifest.json`.

Chính sách chạy step:
- Timeout mỗi step: cấu hình.
- Retry: tối đa `max_retry` với exponential/backoff policy.
- Checkpoint: cập nhật `job_state.json` sau mỗi step DONE.
- Resume: đọc checkpoint, chạy từ step/chunk chưa DONE.

Evidence local:
- `logs/job-events.ndjson`
- `remotion/render-report.json`
- `final/video.mp4` hoặc artifact mock ở test mode
- Log chạy retry/resume từ môi trường local

## 11. Bảo mật, config & local storage

### 11.1 Config file không nhạy cảm
Config runtime nằm ngoài secret store, ví dụ:
- Dev/source run: `configs/profile.default.json` hoặc app data local.
- Portable build: tự tạo `configs/profile.default.json` cạnh executable nếu chưa có.

Config chỉ được lưu các trường không nhạy cảm:
```json
{
  "llm": {
    "url_model": "http://10.48.240.50:20128/v1",
    "default_model": "...",
    "credential_id_model": "tao-video-bao-cao/model/default"
  },
  "tts": {
    "url_tts": "https://...",
    "model_tts": "...",
    "voice": "...",
    "credential_id_tts": "tao-video-bao-cao/tts/default"
  },
  "runtime_policy": {
    "step_timeout_seconds": 600,
    "max_retry": 3,
    "retry_backoff_seconds": 30,
    "enable_resume": true
  }
}
```

### 11.2 Secret storage
- Lưu API key qua Windows Credential Manager bằng `keyring` hoặc backend an toàn tương đương.
- Fallback DPAPI qua `pywin32` nếu `keyring` không khả dụng.
- Không lưu `apikey_model`/`apikey_tts` plaintext trong repo/config/log/export.
- UI sau khi lưu chỉ hiển thị credential id/reference, không render lại key thật.
- Log masking toàn bộ token/key và token-like text.

### 11.3 Job state
Mỗi job có `outputs/YYYYMM/<job_id>/job_state.json`:
```json
{
  "job_id": "string",
  "status": "RUNNING",
  "report_month": "YYYYMM",
  "current_step_id": "P1.1",
  "steps": [
    {
      "step_id": "string",
      "name": "string",
      "status": "DONE|RUNNING|WAITING_RETRY|FAILED|PENDING",
      "attempt": 1,
      "started_at": "ISO-8601",
      "ended_at": "ISO-8601|null",
      "error_code": null,
      "error_message": null,
      "artifacts": []
    }
  ],
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

## 12. Prompt contract & AI step design
### 12.1 Prompt contract chung
- Áp dụng chuẩn role/input/output/error format cho mọi step AI.
- Cấm bịa số liệu; mọi số liệu quan trọng phải có citation/mapping về nguồn PDF (`page_no`, `source_snippet`, `confidence`).
- Mọi phản hồi AI phải parse được về JSON schema trước khi ghi artifact.
- LLM client phải xử lý được SSE streaming, thinking tags và retry parse JSON.

### 12.2 Prompt theo pipeline
- `P1_1_CHUNK_EXTRACTION`: đọc một chunk PDF, trích xuất metrics/sections/citations.
- `P1_1B_SCREEN_PLANNING`: lập screen plan, bắt buộc intro đầu và closing cuối.
- `P1_2_WORKFLOW_COMPOSITION`: map structured data + screen plan + template -> workflow scenes.
- Workflow validation: kiểm field bắt buộc + mapping nguồn dữ liệu, bao gồm rule bắt buộc đúng 1 intro ở đầu và đúng 1 closing ở cuối video.
- AI Pass 2: tách nhỏ theo S2.1-S2.8 cho scene planning, visual spec, TTS script, component spec, asset plan, render plan, QA fix, final packaging.

### 12.3 Tài liệu chi tiết
- Chi tiết prompt + schema + artifact path: `docs/prompt-contracts.md`.

## 13. Phase plan & checklist chi tiết
Chi tiết execution nằm trong các file:
- `plans/01-repo-and-docs-foundation.md`
- `plans/02-ui-config-foundation.md`
- `plans/03-pdf-to-workflow-pipeline.md`
- `plans/04-ai-video-generation-pipeline.md`
- `plans/05-packaging-release.md`

## 14. Acceptance criteria end-to-end (local-first)
Một run E2E được chấp nhận khi:
1. User import 1 PDF hợp lệ trên local app.
2. Hệ thống tạo được structured data đúng schema bằng P1.1 chunk-by-chunk.
3. Hệ thống tạo được screen plan đúng intro/closing bằng P1.1b.
4. Hệ thống tạo workflow mới đúng naming/path và pass rule scene bắt buộc (đúng 1 intro ở đầu, đúng 1 closing ở cuối).
5. P1.1/P1.2 có cache chunk JSON và resume skip chunk đã done.
6. Pipeline AI #2 chạy tuần tự qua checkpoint/resume.
7. Có MP4 final tải được từ thư mục output local.
8. Không lộ secret trong log/file.
9. Job detail thể hiện đầy đủ timeline + trạng thái step.
10. Build được binary portable bằng PyInstaller và chạy được từ thư mục tách biệt.
11. App không phụ thuộc path tuyệt đối; tự tạo output/config ở môi trường mới.
12. Màn hình `Lịch sử` tìm được job vừa chạy và mở được final/output folder.
13. Auto-updater kiểm tra được release endpoint và xử lý không phá app khi offline/lỗi mạng.

## 14.1 Portable verification matrix
| Case | Mục tiêu | Evidence |
|---|---|---|
| Dev run | Chạy app từ source trên máy hiện tại | log dev run + screenshot |
| Mock E2E | Không gọi AI thật, vẫn chạy đủ state/artifact mock | `job_state.json`, `job-events.ndjson` |
| Chunk resume | Fail giữa P1.1/P1.2 rồi resume chỉ chạy chunk lỗi | chunk cache + log skip cached |
| Real/sample E2E | PDF mẫu -> workflow -> video hoặc preview thật | output folder + final/preview artifact |
| Portable isolated folder | Copy build sang thư mục khác rồi chạy | screenshot + output tự tạo |
| Clean user profile | Config mới không có key plaintext, secret store hoạt động | config JSON masked/reference |
| Update check | Check release/latest và asset selection | updater log/screenshot |
| Path independence | Không phụ thuộc `D:\Tao video bao cao giao ban` | log path runtime |

Ghi chú:
- Không có gate bắt buộc về VPS/deploy server.
- CI/GitHub Actions nếu có chỉ là tùy chọn hỗ trợ, không phải điều kiện bắt buộc để pass phase.

## 15. Risks / blockers
1. PDF nguồn đa dạng format -> parse sai bảng.
2. LLM output lệch schema -> cần guard + repair pass.
3. Chunk merge có thể dedupe sai nếu `metric_key`/`scene_id` không ổn định.
4. TTS endpoint chậm/timeout -> cần retry/backoff.
5. Render Remotion lâu -> cần preview gate trước final.
6. Secret handling sai -> rò rỉ key.
7. Workflow template thay đổi format -> mapping fail.
8. Build onefile lớn/chậm -> cần tối ưu packaging profile.
9. Auto-updater thay executable cần test kỹ trên Windows portable/frozen mode.

## 16. Status register (điều phối)
- [x] Phase 01 Docs foundation completed enough for coordination.
- [x] Phase 02 UI design & foundation substantially implemented.
  - [x] 4-screen UI shell/screens.
  - [x] Config URL -> Key -> Model dropdown auto-fetch.
  - [x] Topbar quick action `Kiểm tra cập nhật`.
  - [ ] Screenshot/evidence local cần lưu lại nếu chưa có.
- [/] Phase 03 PDF pipeline in progress.
  - [x] Parser/normalizer foundation.
  - [x] P1.1 chunk extraction prompt.
  - [x] P1.1b screen planning prompt.
  - [x] ChunkProcessor cache/resume.
  - [ ] Strict schema validation and full artifact evidence.
- [/] Phase 04 AI video pipeline in progress.
  - [x] Video orchestration/handoff foundation.
  - [ ] Full S2.1-S2.8 prompt/schema/artifact evidence.
- [/] Phase 05 Packaging/release in progress.
  - [x] Build script foundation.
  - [x] Auto-updater foundation.
  - [x] Version `0.2.0` and release `v0.2.0` noted.
  - [ ] Portable isolated verification evidence.
