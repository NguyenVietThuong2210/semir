# Plan — Tối ưu tab "Active Zalo Mini App" (ca_zalo) bằng phân trang

**Ngày:** 2026-09-26 · **Trạng thái:** Chờ duyệt (chưa code) · **Liên quan:** [prod.md](prod.md) history 2026-09-26

---

## Phần 1 — Giải thích dễ hiểu (không cần biết code)

### Chuyện gì đang xảy ra?
Tab **"Active Zalo Mini App"** hiển thị danh sách khách hàng có kết nối Zalo. Vấn đề: nó cố
**hiện TẤT CẢ 108,241 khách trong CÙNG một trang, cùng một lúc**.

> **Ví dụ:** Giống như bạn mở 1 file Excel có 108 nghìn dòng, nhưng thay vì xem 50 dòng đầu, máy
> phải vẽ hết cả 108 nghìn dòng ra màn hình mới cho bạn nhìn. Vừa lâu, vừa nặng.

Kết quả:
- Trang web nặng **~46 MB** cho một lần bấm (bình thường 1 trang web chỉ vài trăm KB).
- Mất **~30 giây** mới hiện ra.
- Server RAM yếu (1.9GB) bị **quá tải → tiến trình bị hệ điều hành "giết"** → phải làm lại từ đầu → càng lâu.

Chúng ta **đã** dán một "miếng vá" tạm (thêm swap) để server **không bị sập** nữa. Nhưng swap chỉ
chống sập, **không làm nhanh hơn**. Trang vẫn 46MB / 30 giây. Plan này để làm nó **thật sự nhanh**.

### Ý tưởng sửa (một câu)
**Đừng hiện hết 108k dòng cùng lúc. Chỉ hiện 50 dòng mỗi lần, có nút "Trang sau" để xem tiếp** —
đúng như cách Google hiển thị kết quả tìm kiếm theo trang.

> **Ví dụ:** Thay vì bê cả kho hàng ra sân, ta chỉ lấy 1 kệ (50 món) cho bạn xem; xem xong bấm
> "kệ tiếp theo". Nhanh, nhẹ, mà hàng trong kho vẫn còn nguyên.

### Điều quan trọng nhất: KHÔNG mất/đổi dữ liệu nào
Đây là cam kết số 1 của plan. Cụ thể:
- **Số liệu thống kê** (các thẻ đếm "Zalo Mini App: 55,190…") → **giữ nguyên tuyệt đối**.
- **Nút "Download" Excel** → vẫn xuất **đầy đủ 108k dòng** (nó đi bằng một đường code riêng, không
  bị đụng tới). Nên nếu ai cần xem toàn bộ, họ tải Excel.
- **Thứ tự và giá trị từng dòng** → không đổi. Ghép tất cả các trang lại = đúng bằng danh sách cũ.
- Chúng ta có **bài test tự động** so sánh "trước vs sau" để **chứng minh bằng máy** là không có dòng
  nào bị thay đổi (không phải nói miệng).

### Làm xong thì được gì?

| | Trước | Sau |
|---|---|---|
| Kích thước trang | ~46 MB | < 0.2 MB |
| Thời gian hiện | ~30 giây | < 1 giây |
| Server bị sập (OOM) | Có | Không (sửa tận gốc) |
| Dữ liệu / thống kê / Excel | — | **Giữ nguyên 100%** |

### Rủi ro?
Rất thấp. Chỗ sửa rất hẹp (chỉ đúng tab này), **không đụng** tới export Excel, app điện thoại, hay
các tab khác. Nếu có sự cố, chỉ cần hoàn tác (revert) đoạn code là xong — server vẫn an toàn nhờ đã có swap.

---

## Phần 2 — Plan kỹ thuật chi tiết

### A. Mục tiêu & Non-goals
- **Mục tiêu:** fragment 46MB/~30s → **<200KB / <1s**, loại OOM tại gốc (swap thành lớp bảo hiểm).
- **KHÔNG đụng:** logic đếm/thống kê, thứ tự sắp xếp, giá trị từng dòng, **export Excel** (vẫn full),
  mobile API, các tab khác.

### B. Phát hiện then chốt (đã verify trong code)
1. `_customer_ca_zalo` **chỉ** được gọi bởi `get_customer_tab('ca_zalo')` → dùng ở (a) view AJAX
   `customer_tab`, (b) snapshot test `test_tab_snapshot_ca_zalo`. Không nơi nào khác.
2. **Export Excel đi đường riêng** (`get_cnv_comparison_data` → `compute_cnv_breakdown` trong
   `App/cnv/service.py` → `App/analytics/excel_export.py`). ⇒ sửa `_customer_ca_zalo` **không** ảnh
   hưởng export → full list luôn có qua Download. **Chốt chặn "no data change".**
3. Mobile API không dùng zalo list → 0 tác động mobile.
4. Snapshot test assert **full** `zalo_mini_app_list` + `zalo_oa_list`.

### C. Thiết kế được chọn
**Tham số hoá phân trang trong `_customer_ca_zalo`; mặc định (không truyền tham số) = full,
byte-identical như hiện tại.** View production luôn truyền tham số trang → chỉ build 1 trang.

```
_customer_ca_zalo(start, end, app_page=None, oa_page=None, page_size=50)
  ├─ counts/aggregates      → GIỮ NGUYÊN (rẻ, luôn cần)
  ├─ nếu app_page is None   → build FULL list (test + caller cũ) → snapshot KHÔNG đổi
  └─ nếu có app_page        → Django Paginator, chỉ build rows của trang đó
                              + POS lookup chỉ cho ~50 phone của trang (IN nhỏ, thay vì quét toàn bộ)
```
**Vì sao thắng:** snapshot test gọi không tham số → full → **xanh, không regen**; prod luôn phân
trang → chỉ ~100 dict → **OOM biến mất tại gốc**; 2 bảng phân trang độc lập (`app_page`/`oa_page`),
thứ tự giữ nguyên nên trang 1 = N dòng đầu của snapshot (dễ assert đối chiếu).

**Loại bỏ:** DataTables client-side (vẫn 108k dòng trong DOM); DataTables serverSide (phức tạp,
rủi ro cao, thừa); cap cứng top-N + đổi snapshot (vi phạm "no data change" ở tầng test).

### D. Change set (file-by-file)

| File | Thay đổi |
|---|---|
| `App/analytics/customer_tabs.py` (`_customer_ca_zalo`, ~L226) | thêm `app_page/oa_page/page_size`; nhánh full giữ nguyên; nhánh paginated dùng `Paginator`, POS lookup theo phone của trang; trả thêm `app_page/app_num_pages/app_total` + tương tự OA |
| `App/analytics/customer_tabs.py` (`get_customer_tab`, ~L60) | chuyển tham số phân trang xuống (default None → hành vi cũ) |
| `App/cnv/views.py` (`customer_tab`, ~L165) | với `tab=='ca_zalo'`, đọc `?app_page=&oa_page=` (default 1), truyền vào |
| `App/templates/cnv/tabs/ca_zalo.html` | render trang hiện tại + pager mỗi bảng ("Trang X/Y — tổng N — Download để lấy đầy đủ"); cards & export **giữ nguyên** |
| `App/templates/cnv/customer_analytics.html` (~L379) | JS nhỏ: click pager → `fetch(.../ca_zalo/?app_page=k)` → thay nội dung pane (tái dùng cơ chế lazy sẵn có) |
| `tests/test_customer.py` (~L572) | **không sửa** test snapshot cũ (phải tự xanh); **thêm** test phân trang (mục F) |

### E. Definition of Done (DoD)
- [ ] Tab `ca_zalo` trả fragment **<200KB**, render **<1s** (đo local + prod).
- [ ] Không còn `SIGKILL ... out of memory` sau khi mở tab (theo dõi log prod sau deploy).
- [ ] Snapshot cũ `test_tab_snapshot_ca_zalo` **xanh, không regen**.
- [ ] Export Excel tab zalo vẫn ra **đủ 55,190 + 53,051 dòng**.
- [ ] 4 KPI cards + %/counts **không đổi giá trị**.
- [ ] Ghép mọi trang qua pager = full list, đúng thứ tự.
- [ ] Full test suite xanh; visual snapshot 0 token issue (vì sửa template).
- [ ] Cập nhật `docs/prod.md` history + `docs/project_cnv.md`/`project_ui.md` nếu cần.

### F. QA Gate — chứng minh "KHÔNG data nào đổi"
1. **Snapshot bất biến:** `test_tab_snapshot_ca_zalo` không `UPDATE_SNAPSHOTS` → xanh (nhánh full byte-identical).
2. **Round-trip completeness (test mới):** ghép mọi trang `app_page=1..N` == full `zalo_mini_app_list` (cùng thứ tự, giá trị); tương tự OA.
3. **Parity trang-1:** `page(app_page=1, size=50).rows == full_list[:50]`.
4. **Counts bất biến:** `zalo_app_all_count/pct`, `oa`, period — so snapshot cũ.
5. **Export bất biến:** workbook tab zalo trước/sau → cùng số sheet, cùng số data-row.
6. **Full snapshot regen diff:** chỉ khác dòng `_last_run`; field khác đổi = regression.

### G. Plan kiểm thử LOCAL (tuân thủ Resource Discipline — 1 heavy op/lúc, coordinator chạy)
**Chuẩn bị (fast-iteration):**
```bash
docker ps                              # xác nhận chưa có heavy op
docker compose up -d db redis
docker compose stop web                # free port 8000
cd SemirDashboard && ../venv/Scripts/python.exe manage.py runserver
```
**Vòng lặp:**
1. Sửa `_customer_ca_zalo` (nhánh paginated) + thêm test round-trip → chạy **chỉ test đó**.
2. Đo trước/sau: peak RSS + `len(html)` full vs paginated (script `manage.py shell` → scratchpad).
3. Mở `http://localhost:8000/cnv/customer-analytics/` → tab Active Zalo → bấm pager, kiểm dữ liệu & tốc độ (skill `/verify` hoặc `/run`).
4. Sửa template → **bắt buộc** regen visual snapshot (host venv + Chrome) → mở `tests/render/png/*.png`, `_index.md` 0 issue.

**Gate cuối (1 lần):**
5. `python manage.py test tests.test_customer -v 2`.
6. Snapshot bất biến check (F.1 & F.6).
7. (Trước release) full `manage.py test tests` + Testing-for-Release theo CLAUDE.md.

### H. Rollout & Rollback
- **Deploy:** merge `main` → `bash scripts/deploy.sh` (theo `docs/prod.md`) → theo dõi `docker compose logs -f web`, mở tab zalo, xác nhận size nhỏ + không SIGKILL.
- **Rollback:** thuần code → `git revert` + deploy. Swap vẫn còn nên không tái diễn OOM.

### I. Rủi ro & giảm thiểu
| Rủi ro | Giảm thiểu |
|---|---|
| Người dùng quen cuộn xem tất cả | Pager rõ + nhấn mạnh nút Download (full) sẵn có |
| POS lookup theo trang lệch giá trị `in_pos`/`registration_store` | Test round-trip so từng dòng (F.2) |
| Sửa template vỡ token màu | Bắt buộc visual snapshot (G.4) |
| RAM căng khi build `--no-cache` lúc deploy | Đã có 4GB swap; deploy ngoài giờ cao điểm, theo dõi `free -m` |

### J. Ước lượng
~**0.5–1 ngày**: BE + template + JS ~2–3h, tests ~2h, verify local + visual ~1–2h. Rủi ro thấp.
