---
name: sync-guideline
description: Đồng bộ nội dung trang Guideline (curriculum tĩnh HTML) từ D:\New-jouney\predictor\guideline vào D:\New-jouney\semir\SemirDashboard\App\templates\guideline, deploy vào container đang chạy, và smoke-test. Dùng khi user nói "sync guideline", "cập nhật guideline", "đồng bộ bài học mới".
---

# Sync Guideline Content

## Bối cảnh

Trang `/guideline/` (`App/views/guideline.py`) serve các file HTML tĩnh trong `App/templates/guideline/` trực tiếp bằng byte, không qua Django template engine — vì vậy **không cần sửa code** khi nội dung thay đổi, chỉ cần ghi đè folder. View đọc file từ đĩa ở mỗi request (không cache), nên sau khi copy vào container **không cần restart** — chỉ cần `docker compose cp`.

Nguồn nội dung gốc: `D:\New-jouney\predictor\guideline` (dự án khác, không phải semir). Đích: `D:\New-jouney\semir\SemirDashboard\App\templates\guideline`.

## Quy trình

### 1. Kiểm tra nguồn tồn tại
```powershell
Test-Path "D:\New-jouney\predictor\guideline\index.html"
```
Nếu không có, dừng lại và hỏi user đường dẫn đúng.

### 2. Xem trước thay đổi (BẮT BUỘC trước khi ghi đè — đây là thao tác có thể mất dữ liệu cũ)
```powershell
robocopy "D:\New-jouney\predictor\guideline" "D:\New-jouney\semir\SemirDashboard\App\templates\guideline" /L /E /NJH /NJS
```
`/L` = list-only (không copy thật). Đọc output: file nào sẽ bị **ghi đè** (`*EXTRA File` bên đích nếu dùng `/MIR` — mặc định KHÔNG dùng `/MIR` để không xóa file cũ không còn trong nguồn, trừ khi user xác nhận muốn mirror-xóa). Báo cáo tóm tắt cho user (số file mới/thay đổi) nếu danh sách dài, không cần liệt kê hết.

### 3. Copy thật (mặc định: KHÔNG xóa file thừa ở đích — an toàn hơn)
```powershell
robocopy "D:\New-jouney\predictor\guideline" "D:\New-jouney\semir\SemirDashboard\App\templates\guideline" /E /NJH /NJS
```
Chỉ dùng `/MIR` (mirror, xóa file đích không còn trong nguồn) nếu user **explicitly** yêu cầu "xóa bài cũ"/"mirror sạch" — robocopy exit code ≥8 nghĩa là lỗi thật (0-7 đều là "thành công" theo quy ước robocopy, kể cả khi 0 file thay đổi).

### 4. Verify sanity
```powershell
Test-Path "D:\New-jouney\semir\SemirDashboard\App\templates\guideline\index.html"
```
Phải `True` — nếu `False`, dừng lại, đây là dấu hiệu sync hỏng.

### 5. Kiểm tra Docker trước khi deploy (Resource Discipline — CLAUDE.md)
```bash
docker ps --format "{{.Names}}: {{.Status}}"
```
Nếu `semir_web` không chạy, dừng lại và báo user cần bật Docker trước (không tự ý `docker compose up`).

### 6. Deploy vào container (copy nguyên folder, KHÔNG cần restart)
```bash
cd /d/New-jouney/semir && docker compose cp SemirDashboard/App/templates/guideline web:/app/App/templates/guideline
```

### 7. Smoke test
```bash
docker compose exec -T web python manage.py shell -c "
from django.test import Client, override_settings
from django.contrib.auth.models import User
with override_settings(ALLOWED_HOSTS=['*']):
    c = Client()
    c.force_login(User.objects.filter(is_superuser=True).first())
    for p in ['/guideline/', '/guideline/glossary.html', '/guideline/interview_50_qa.html']:
        r = c.get(p, SERVER_NAME='localhost')
        print(f'[{r.status_code}] {p}')
    print('banner present:', b'Back to Dashboard' in c.get('/guideline/', SERVER_NAME='localhost').content)
"
```
Tất cả phải `200` và `banner present: True`. Nếu nội dung mới thêm file ảnh/js/font (trước giờ guideline chỉ có html+css), kiểm tra thêm 1 request tới file đó để chắc `mimetypes.guess_type` trả đúng content-type — `guideline_view()` đã generic (dùng `mimetypes.guess_type`), không cần sửa code cho loại file mới, chỉ cần xác nhận qua smoke test.

### 8. Báo cáo cho user
Số file thay đổi/mới, kết quả smoke test, và nhắc: nếu muốn lên PROD, cần lặp lại bước 6-7 qua SSH vào server thật (không tự làm nếu user chưa cấp quyền/context PROD trong phiên này).

## Lưu ý an toàn
- Không bao giờ tự ý dùng `/MIR` (xóa file đích) khi chưa được user xác nhận rõ ràng — mặc định chỉ thêm/ghi đè.
- Không restart container — không cần thiết cho thay đổi file tĩnh, và restart có thể gây gián đoạn nếu có job async khác đang chạy.
- Đây là nội dung tĩnh, không đụng đến DB/migration — không cần `manage.py migrate`.
