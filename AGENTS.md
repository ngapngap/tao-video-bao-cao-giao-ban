# AGENTS.md - Hướng dẫn vận hành agent cho dự án `tao-video-bao-cao-giao-ban`

## 1) Mục tiêu dự án
Xây dựng ứng dụng desktop Python portable (không cần cài đặt) để:
1. Import PDF báo cáo giao ban.
2. Parse PDF bằng PyMuPDF, fallback pdfplumber.
3. AI đọc và trích xuất số liệu có cấu trúc theo chunk-by-chunk để tránh timeout và hỗ trợ resume.
4. Lên kế hoạch screens, sinh workflow máy đọc mới dựa trên mẫu `workflow.md`.
5. Chạy pipeline AI thứ 2 theo từng bước con tuần tự để tạo video hoàn chỉnh có thể tải về.
6. Hỗ trợ phát hành/cập nhật portable, hiện tại đã release `v0.2.0`.

## 2) Source of truth & thứ tự đọc
Agent phải đọc theo thứ tự sau trước khi triển khai:
1. `AGENTS.md` (file này) - quy tắc vận hành.
2. `PROJECT_PLAN.md` - master plan + status register + acceptance.
3. `plans/README.md`.
4. `plans/00-one-shot-runbook.md`.
5. Phase file đang active trong `plans/`.
6. `docs/prompt-contracts.md` nếu đụng tới prompt/schema AI.
7. `noidung.md` và `workflow.md` làm input nghiệp vụ.

Ưu tiên `PROJECT_PLAN.md` + `plans/*.md` khi có xung đột với tài liệu tham khảo khác.

## 3) Phạm vi ở repo này
- Có thể tạo/chỉnh tài liệu điều phối, kế hoạch, checklist, schema, runbook.
- Có thể tạo/chỉnh source code app khi được yêu cầu rõ.
- Không tự ý sửa nội dung nghiệp vụ gốc của `noidung.md` và `workflow.md` trừ khi user yêu cầu rõ.
- Không tự ý commit/push nếu chưa được yêu cầu.
- Không sửa file bị gitignore/local plan ngoài phạm vi yêu cầu nếu không cần thiết.

## 4) Ràng buộc môi trường
- Hệ điều hành chính: Windows.
- Dự án ưu tiên nhẹ, cho phép chạy local build/test hợp lý trực tiếp trên máy Windows hiện tại.
- Được phép chạy các lệnh local phục vụ xác minh: unit test Python (`pytest`), smoke test nhẹ, chạy app dev, build `PyInstaller` khi cần.
- Không yêu cầu deploy server/VPS; verification chính là local + kiểm thử tính portable.
- Không in secret/API key ra terminal/log/chat.

## 5) Kiến trúc hiện tại (high-level)
- Desktop app: Python + `customtkinter` (UI) + đóng gói `PyInstaller --onefile`.
- Entrypoint và phát hành:
  - `app/main.py`: app shell + orchestration UI/job.
  - `app/version.py`: version hiện tại `0.2.0`, GitHub Releases endpoint.
  - `app/updater.py`: auto-updater tải asset release phù hợp nền tảng và thay executable.
- PDF parse: `pymupdf` (ưu tiên) + fallback `pdfplumber`.
- LLM client: HTTP JSON OpenAI-compatible API gateway, default URL `http://10.48.240.50:20128/v1`.
- LLM robustness:
  - Fetch models qua endpoint `/models` khi user click/focus dropdown model.
  - Parse SSE streaming response khi API trả `text/event-stream` hoặc dòng `data:`.
  - Strip thinking tags trước khi parse JSON.
  - Retry parse JSON khi response lỗi format.
- Data validation: `pydantic` schema.
- Job engine: queue tuần tự theo step, có `checkpoint/resume/retry`, event log NDJSON.
- Chunk-by-chunk AI processing:
  - `ChunkProcessor` trong `app/core/chunk_processor.py`.
  - Cache từng chunk thành file JSON riêng.
  - Skip chunk đã done khi resume.
  - Retry chỉ chunk lỗi.
  - Resume từ chunk chưa hoàn thành thay vì chạy lại toàn bộ step.
- TTS engine: `edge-tts` (local, không cần API key) hoặc API TTS ngoài.
- Default voice: `vi-VN-NamMinhNeural`.
- Local storage:
  - Cấu hình không nhạy cảm: file JSON trong app data/config runtime.
  - API keys: lưu qua Windows Credential Manager/DPAPI (không plaintext).
- Remotion flow: app tạo prompt/spec và gọi lane AI thứ 2 theo các step nhỏ để giảm timeout/524.

## 6) Repo structure hiện tại
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

## 7) Quy tắc bảo mật bắt buộc
1. Không lưu `apikey_model`/`apikey_tts` dạng plaintext trong repo.
2. Trên Windows, ưu tiên:
   - `keyring` (Windows Credential Manager), hoặc
   - `pywin32`/DPAPI để mã hoá dữ liệu cục bộ.
3. Log phải mask token (`****`).
4. File export/public không chứa secret.
5. Không commit secrets/API key vào git dưới mọi hình thức.

## 8) Quy ước thư mục output
Dữ liệu chạy phải nằm trong cấu trúc:
- `outputs/YYYYMM/<job_id>/`
  - `input/` (pdf gốc copy)
  - `parsed/` (json trích xuất, screen plan, chunk caches)
  - `workflow/` (workflow đã sinh, workflow chunk caches)
  - `tts/` (audio từng frame/scene)
  - `remotion/` (scene spec, assets, render logs)
  - `final/` (mp4 tải về)
  - `logs/` (event log theo step)

## 9) Trạng thái job chuẩn
`DRAFT -> QUEUED -> RUNNING -> WAITING_RETRY -> PARTIAL_DONE -> DONE | FAILED | CANCELED`

Mỗi step lưu:
- `step_id`, `name`, `status`, `attempt`, `started_at`, `ended_at`, `error_code`, `error_message`, `artifacts[]`.

## 10) Pipeline steps chuẩn hiện tại (15 steps)
> Lưu ý: danh sách hiện tại có 14 step ID thực thi theo mô tả code/session, nhưng được gọi là pipeline 15 steps trong tài liệu điều phối vì P1.1 và P1.2 đều chạy chunk-by-chunk gồm nhiều chunk runtime. Khi cập nhật code/plan tiếp theo, không được quay lại mô hình 13 steps cũ.

1. `S1.1` - Chuẩn bị thư mục output.
2. `S1.2` - Copy PDF đầu vào.
3. `S1.3` - Parse PDF (PyMuPDF + pdfplumber).
4. `P1.1` - Trích xuất dữ liệu (chunk-by-chunk, cache/resume).
5. `P1.1b` - Lên kế hoạch screens.
6. `P1.2` - Sinh workflow (chunk-by-chunk, cache/resume).
7. `S2.1` - Scene planning.
8. `S2.2` - Visual spec.
9. `S2.3` - TTS script.
10. `S2.4` - Component spec.
11. `S2.5` - Asset plan.
12. `S2.6` - Render plan.
13. `S2.7` - QA fix.
14. `S2.8` - Final packaging.

## 11) Tiêu chuẩn thực thi step AI (để tránh 524)
- Chia nhỏ pipeline AI theo step độc lập.
- Với P1.1/P1.2, chia input thành chunks và dùng `ChunkProcessor` để cache/resume từng chunk.
- Mỗi chunk thành công phải ghi cache JSON trước khi chuyển chunk tiếp theo.
- Khi resume, chunk đã done phải được skip; chỉ retry chunk lỗi/chưa có cache hợp lệ.
- Mỗi step có timeout riêng, retry có backoff.
- Có checkpoint file `job_state.json` để resume.
- Chỉ chạy step kế tiếp khi step trước `DONE`.
- Nếu lỗi hard-fail: dừng pipeline, cho phép resume từ step/chunk fail.

## 12) UI contract tối thiểu
Bắt buộc có 4 màn hình desktop:
1. `Tạo video`: import PDF, nhập tháng báo cáo, chọn profile/template/output, readiness checklist, start job, xem trạng thái nhanh.
2. `Cấu hình`: URL -> Key -> Model dropdown auto-fetch cho LLM, cấu hình TTS, runtime policy, test connection, secret storage status.
3. `Job & Logs`: timeline step theo phase, log realtime có filter/search, retry/resume/cancel, artifact panel.
4. `Lịch sử`: danh sách job local theo tháng/trạng thái, mở detail/final video/output folder.

Topbar bắt buộc có quick actions:
- `Mở outputs`.
- `Kiểm tra cập nhật`.
- `Cấu hình`.

Chi tiết design system, layout, fields, validation và smoke evidence nằm tại `PROJECT_PLAN.md`, `plans/02-ui-config-foundation.md`, `design-system/bao-cao-giao-ban-video-generator/MASTER.md`, và `design-system/bao-cao-giao-ban-video-generator/UI_SPEC.md`.

## 13) Định nghĩa hoàn thành (DoD)
Một phase chỉ được tick done khi:
- Checklist phase pass.
- Acceptance criteria có bằng chứng local (log/file/screenshot/path).
- Có bằng chứng chạy local build/test phù hợp phạm vi phase.
- Có bằng chứng portable check: chạy từ thư mục tách biệt hoặc môi trường sạch.
- Không lộ secret.
- Tài liệu trạng thái được cập nhật lại ở `PROJECT_PLAN.md` và phase file tương ứng.

## 14) Quy tắc báo cáo tiến độ
Mỗi lần làm việc:
- Nêu file đã sửa/tạo.
- Nêu checklist item đã hoàn thành.
- Nêu phần còn lại/blocker.
- Nếu chưa commit/push: ghi rõ chưa commit/push.
