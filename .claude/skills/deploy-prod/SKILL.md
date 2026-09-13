---
name: deploy-prod
description: Deploy the current release branch to the real PROD server (SSH, git pull, rebuild Docker image, migrate, perm sync, verify live) — mirrors scripts/deploy.sh exactly, run remotely. Use when user says "deploy to PROD", "lên PROD", "connect to PROD => build docker", "push lên production". Causes a real brief outage window (full container restart) — only run when explicitly asked for THIS deploy, never unattended/scheduled.
---

# Deploy to PROD

**Vai trò bắt buộc:** đây là thao tác ảnh hưởng hệ thống LIVE thật (gây gián đoạn ngắn khi restart container) — luôn xác nhận rõ đang deploy branch nào, commit nào, và báo cáo kết quả đầy đủ như QA Senior Leader, không chỉ "done".

## Trước khi chạy — điều kiện bắt buộc

1. **Code phải đã commit + push lên `origin`** — deploy chỉ `git pull` trên server, không copy file cục bộ. Nếu còn thay đổi chưa commit/push, dừng lại và commit/push trước (không tự ý push nếu user chưa đồng ý).
2. **Test local phải đã pass** — chạy bộ test liên quan trước khi deploy PROD (không phải trách nhiệm của skill này, nhưng phải xác nhận đã làm ở bước trước trong phiên).
3. Xác định branch cần deploy (mặc định `release/2.4.0` nếu không có chỉ định khác trong phiên hiện tại — KHÔNG mặc định `main` dù `scripts/deploy.sh` hardcode `main`, vì PROD hiện đang chạy trên `release/2.4.0`, xem `docs/`/lịch sử phiên để xác nhận branch thật đang deploy).

## Thông tin kết nối (KHÔNG bao giờ in ra chat / commit)

Đọc từ `D:\New-jouney\semir\prod_visual.env` (gitignored): `PROD_ID` (server IP), `PROD_PASS` (root SSH password). Host key đã pin sẵn (xác nhận lần đầu trong phiên trước): `10:f6:df:1c:3f:e7:a7:32:cd:fa:25:75:a1:c8:fd:0a`.

Kết nối qua PuTTY `plink` (Windows, không có `ssh-agent`):
```bash
"/c/Program Files/PuTTY/plink" -ssh -batch -hostkey "10:f6:df:1c:3f:e7:a7:32:cd:fa:25:75:a1:c8:fd:0a" -pw "<PROD_PASS>" root@<PROD_ID> "<remote command>"
```

## Quy trình (mirroring `scripts/deploy.sh`, chạy qua SSH thay vì trực tiếp trên server)

### 1. Kiểm tra trạng thái trước khi động vào (Resource Discipline)
```bash
"...plink..." root@<PROD_ID> "cd /home/semir/semir && git status --short && git log --oneline -3 && docker compose ps"
```
Xác nhận không có gì bất thường (không có container nào đang crash-loop, không có uncommitted local changes trên server tự dưng xuất hiện — nếu có, dừng lại hỏi user).

### 2. Pull code mới
```bash
"...plink..." root@<PROD_ID> "cd /home/semir/semir && git fetch origin && git checkout <branch> && git pull origin <branch>"
```

### 3. Rebuild + restart (ĐÂY LÀ BƯỚC GÂY GIÁN ĐOẠN — nginx/web đều down vài giây đến vài chục giây)
```bash
"...plink..." root@<PROD_ID> "cd /home/semir/semir && docker compose build --no-cache web && docker compose down && docker compose up -d"
```
`--no-cache` khớp với `scripts/deploy.sh` gốc — chậm hơn nhưng đảm bảo không dính layer cache cũ. Nếu cần nhanh hơn và chấp nhận rủi ro cache, có thể dùng `docker compose build web` (không `--no-cache`) — chỉ làm vậy nếu user yêu cầu ưu tiên tốc độ.

### 4. Đợi DB sẵn sàng, chạy migration + perm sync + collectstatic
```bash
"...plink..." root@<PROD_ID> "cd /home/semir/semir && sleep 10 && docker compose exec -T web python manage.py migrate && docker compose exec -T web python manage.py perm sync && docker compose exec -T web python manage.py collectstatic --noinput"
```
`migrate` áp dụng mọi migration mới (vd. `CustomerGradeProgress` nếu đây là lần đầu deploy tính năng đó lên PROD). `perm sync` bắt buộc sau khi thêm permission mới (vd. `data.guideline`, `membership.compute`) để nó xuất hiện trong UI quản lý Role.

### 5. Xác nhận container khỏe
```bash
"...plink..." root@<PROD_ID> "cd /home/semir/semir && docker compose ps"
```
Tất cả phải `Up`/`healthy`. Nếu có container `Exit`/`Restarting`, dừng lại, lấy log (`docker compose logs --tail 100 <service>`) và báo user trước khi coi là xong.

### 6. Verify live — dùng skill `prod-visual` có sẵn, KHÔNG tự viết lại
Sau khi container đã ổn định, dùng `/prod-visual verify` (skill riêng, đã có sẵn trong project) để chụp + so sánh visual regression toàn bộ trang thật. Nếu chưa có baseline từ trước khi deploy, báo rõ cho user là verify lần này không có gì để so sánh (nên chạy `baseline` NGAY TRƯỚC lần deploy kế tiếp).

Nếu chỉ cần smoke test nhanh (không cần visual diff đầy đủ), curl vài URL chính qua domain thật:
```bash
"...plink..." root@<PROD_ID> "curl -s -o /dev/null -w '%{http_code} ' https://analytics-customer-dashboard.com/ ; curl -s -o /dev/null -w '%{http_code} ' https://analytics-customer-dashboard.com/membership/ ; curl -s -o /dev/null -w '%{http_code}\n' https://analytics-customer-dashboard.com/guideline/"
```
Lưu ý các trang có `@requires_perm`/`@login_required` sẽ trả `302` (redirect to login) chứ không phải `200` khi curl không có session — đó là kết quả ĐÚNG, không phải lỗi.

## Báo cáo kết quả (bắt buộc đầy đủ, không rút gọn)

- Branch + commit hash đã deploy.
- Kết quả build (thành công/lỗi, thời gian).
- Kết quả migrate (bao nhiêu migration mới được áp dụng).
- Kết quả perm sync.
- Trạng thái container sau deploy.
- Kết quả verify (visual diff hoặc smoke curl).
- Nếu có bất kỳ bước nào lỗi: DỪNG NGAY, không tiếp tục bước sau, báo rõ lỗi + đề xuất rollback (`git log` để lấy lại commit trước đó, KHÔNG tự ý rollback nếu user chưa xác nhận).

## An toàn

- Không bao giờ chạy bước 3 (rebuild+restart) như một phần của việc "kiểm tra thử" — chỉ chạy khi user thật sự muốn deploy ngay lúc này.
- Không chạy song song với bất kỳ heavy operation nào khác (Resource Discipline, CLAUDE.md).
- Không rollback/force-push/xóa gì trên server mà chưa hỏi user, kể cả khi deploy lỗi giữa chừng.
