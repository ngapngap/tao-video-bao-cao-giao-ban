# Báo Cáo Giao Ban - Video Generator

Ứng dụng Python desktop portable dùng để tạo video báo cáo giao ban từ dữ liệu báo cáo.

## Tải về (repo private)

Repo này đang ở chế độ private, vì vậy link download trực tiếp bằng curl/PowerShell có thể trả `Not Found` nếu chưa có xác thực GitHub.

### Cách 1: Dùng GitHub CLI (khuyến nghị)

Đăng nhập GitHub CLI trước nếu máy chưa đăng nhập:

```bash
gh auth login
```

Tải bản portable từ release mới nhất:

```bash
gh release download v0.3.2 --repo ngapngap/tao-video-bao-cao-giao-ban --pattern "BaoCaoGiaoBan-VideoGenerator.exe"
```

Chạy file sau khi tải:

```bash
BaoCaoGiaoBan-VideoGenerator.exe
```

### Cách 2: Tải từ browser

Vào https://github.com/ngapngap/tao-video-bao-cao-giao-ban/releases/latest và tải file `.exe`.

### Cách 3: Chạy từ source

```bash
git clone https://github.com/ngapngap/tao-video-bao-cao-giao-ban.git
cd tao-video-bao-cao-giao-ban
pip install -r requirements.txt
python app/main.py
```

### Tự động cập nhật

App có tính năng tự kiểm tra phiên bản mới. Khi có bản cập nhật, app sẽ thông báo và tải tự động.

Hoặc kiểm tra thủ công bằng GitHub CLI:

```bash
gh release view --repo ngapngap/tao-video-bao-cao-giao-ban
```

## Chạy dev

```bash
python app/main.py
```

## Cấu trúc thư mục

```text
app/
  main.py
  ui/
  core/
  pdf/
  ai/
  workflow/
  video/
  security/
  assets/
configs/
tests/
```

## GitHub Issues

Theo dõi tiến độ tại: https://github.com/ngapngap/tao-video-bao-cao-giao-ban/issues

## Kiểm thử AI thật

1. Mở màn hình `Cấu hình`.
2. Tắt `Chế độ AI mock`.
3. Nhập URL OpenAI-compatible, model và API key cho LLM.
4. Nhập URL/model/key cho TTS. Endpoint TTS mặc định được gọi theo dạng `/audio/speech` nếu URL chưa trỏ trực tiếp tới `/audio/speech` hoặc `/tts`.
5. Bấm `Kiểm tra LLM` và `Kiểm tra TTS`; khi thành công UI hiển thị `Kết nối thành công! Model: ...`.
6. Lưu cấu hình, chọn PDF ở màn hình `Tạo video`, rồi chạy job. Pipeline sẽ gọi LLM thật cho P1.1/P1.2 và S2.1-S2.8; TTS sẽ tạo audio thật trong `outputs/YYYYMM/<job_id>/tts/`.

Nếu muốn chạy không tốn API hoặc thiếu cấu hình thật, bật lại `Chế độ AI mock`; mock mode vẫn sinh đủ artifact fallback để smoke test local.
