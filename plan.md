# PLAN.md — Kế hoạch Fix Bug Pre-Refactor (QA-Verified)

> **Ngày lập:** 2026-07-11 · **Branch:** release/2.2.5 · **Trạng thái:** ✅ **ĐÃ THỰC THI + QA SIGN-OFF: APPROVED-WITH-NOTES (2026-07-12)** — 28/28 hạng mục verify pass. Evidence + checklist đầy đủ: `SemirDashboard/tests/output/bugfix_evidence/EVIDENCE.md`. CHƯA COMMIT — chờ user approve 3 thay đổi số (A-04, C-02, A-07) + regen 8 snapshot parity.
> **Môi trường xác nhận:** Django 6.0.2 · pandas 3.0.0 · Cache prod: Redis (django_redis) · Cache dev: LocMem · DB prod: PostgreSQL 16 · DB dev: SQLite
> **Nguồn:** Audit 5 agent + QA leader verify từng bug bằng code thực (1 bug bị bác bỏ: A-03)
> **Artifact chi tiết:** https://claude.ai/code/artifact/a4310b89-a3b3-4374-9053-9fbcece8e8e9

---

## ⛔ NGUYÊN TẮC VÀNG — BẢO TOÀN SỐ LIỆU

Đây là app tính toán số liệu. **Số hiện tại đã được chấp nhận là ĐÚNG. Không một fix nào được phép làm thay đổi số cuối cùng**, trừ các bug được đánh dấu `[SỐ SẼ ĐỔI — CÓ CHỦ ĐÍCH]` bên dưới (số hiện tại là SAI, fix để về đúng — phải có approval trước khi merge).

### Quy trình bắt buộc cho MỌI fix:

```
1. TRƯỚC KHI SỬA — chụp baseline:
   cd SemirDashboard && python manage.py test tests -v 2          # tất cả phải GREEN
   → Lưu log vào tests/output/bugfix_evidence/_baseline/

2. VIẾT TEST TRƯỚC (test-first):
   - Test GUARD (khóa số): assert số liệu hiện tại — phải PASS trên code HIỆN TẠI
   - Test BUG (chứng minh bug): phải FAIL trên code hiện tại, PASS sau khi fix

3. FIX — chỉ sửa đúng phạm vi mô tả trong plan, không sửa lan man.

4. SAU KHI SỬA — verify:
   - Test BUG chuyển từ FAIL → PASS
   - Test GUARD vẫn PASS (số không đổi)
   - Chạy lại: python manage.py test tests -v 2 → tất cả GREEN
   - Snapshot diff: CHỈ dòng `_last_run` được khác
     (ngoại lệ: bug [SỐ SẼ ĐỔI] — diff phải khớp ĐÚNG delta đã dự báo trong plan)

5. EVIDENCE — lưu vào tests/output/bugfix_evidence/<BUG-ID>/:
   - test_run.log (full output)
   - snapshot_diff.txt (git diff tests/snapshots/)
   - before_after.md (số liệu trước/sau nếu có thay đổi)
   - Đánh dấu checklist trong plan này
```

### Các bug ĐƯỢC PHÉP đổi số (cần approval từng cái trước khi merge):
| Bug | Số nào đổi | Từ (sai) → Về (đúng) |
|-----|-----------|---------------------|
| A-04 | `coupon_amount` trên trang **Customer Detail** (web + API) | Tính từ `settlement_amount` → Tính từ `sales_amount` |
| C-02 | Grade donut trên **Mobile API** charts | Rỗng vĩnh viễn → Có dữ liệu grade thật |
| A-07 | Nhãn hiển thị mùa (text, không phải số) | `"M11-1"` → `"M11-1 2024-2025"` |

> **A-01 đã RECLASSIFY sau verify (2026-07-11):** grep toàn bộ call sites cho thấy KHÔNG caller nào truyền `max_invoices` — API gọi `get_customer_detail_data(customer, include_coupons=False)` (api/views.py:963), web gọi default (customer.py:60). Docstring nói "API calls with max_invoices=50" là **STALE** — cap đã bị bỏ. Bug là LATENT (code sai tồn tại nhưng không path nào kích hoạt) → fix A-01 **KHÔNG đổi số nào hôm nay**, chuyển thành fix an toàn + sửa docstring stale.

**Web Analytics / Coupon / Shop Detail / mọi snapshot số liệu khác: KHÔNG ĐƯỢC ĐỔI.**

---

## PHASE 0 — BASELINE + GUARD TESTS (làm TRƯỚC mọi fix)

Mục tiêu: khóa toàn bộ rule nghiệp vụ + số liệu hiện tại bằng test, để mọi fix sau đó có lưới an toàn.

### 0.1 Baseline evidence
- [ ] Chạy `python manage.py test tests -v 2` → all green → lưu log `_baseline/test_run.log`
- [ ] `git status tests/snapshots/` sạch (commit các snapshot đang modified trước, hoặc ghi nhận trạng thái)
- [ ] Chạy visual snapshot: `snapshot_render.py` + `snapshot_visual.py` → PNG baseline (hiện đang RỖNG — UI-12)

### 0.2 Guard tests P1 (file mới `tests/test_business_rules.py`)
| # | Test | Khóa rule | Expect trên code hiện tại |
|---|------|-----------|---------------------------|
| G1 | `test_return_visits_reg_day_purchase_not_counted` + `test_return_visits_pre_reg_all_count` | Công thức return visit (calculations.py) — cả 2 nhánh | PASS |
| G2 | `test_january_belongs_to_prev_year_season` — Jan 2025 → `"M11-1 2024-2025"` | M11-1 cross-year (season_utils.py) | PASS |
| G3 | `test_parse_cnv_period_filter_empty_returns_dict` — trả `({}, False)` không phải `None` | CLAUDE.md rule | PASS |
| G4 | `test_vip_zero_excluded_from_grade_analytics` — vip_id="0" không vào active_customers, có trong buyer_without_info | VIP-0 rule | PASS |
| G5 | `test_shop_detail_ajax_unauthenticated_returns_4xx` — partial trả 401/403, KHÔNG phải 302 | AJAX guard pattern | PASS |
| G6 | `test_grade_hierarchy_order` — No Grade < Member < Silver < Gold < Diamond trong output tab grade | Grade order | PASS |
| G7 | `test_session_sort_key_order` — M2-4=0, M5-7=1, M8-10=2, M11-1=3 | Season sort | PASS |

- [ ] Tất cả G1–G7 viết xong và PASS trên code hiện tại (nếu FAIL → phát hiện bug mới, dừng lại báo cáo)
- [ ] Evidence: `_baseline/guard_tests.log`

---

## PHASE 1 — CRITICAL (4 fix, làm ngay sau Phase 0)

### BUG U-01 — Inventory truncate khi 0 dòng hợp lệ → mất toàn bộ data
- **File:** `App/services/inventory_import.py:130-145`
- **Quyết định:** FIX ngay.
- **Ảnh hưởng số:** KHÔNG (chỉ chặn ca hủy diệt; ca hợp lệ giữ nguyên hành vi).
- **Test TRƯỚC fix** (thêm vào `tests/test_upload.py`):
  - `test_inventory_zero_valid_rows_preserves_existing_data`: seed 5 dòng inventory → upload file đúng header nhưng mọi dòng thiếu shop_id → **expect hiện tại: FAIL (data bị xóa còn 0)** → sau fix: PASS (ValueError raised, DB vẫn 5 dòng)
  - `test_inventory_empty_dataframe_preserves_existing_data`: file chỉ có header → tương tự
  - GUARD `test_inventory_valid_file_still_replaces`: file hợp lệ → truncate+insert như cũ, count khớp file
- **Fix:** trước `transaction.atomic()`: `if not to_create: raise ValueError(f"No valid rows (skipped={skipped}, errors={len(errors)}). Inventory NOT modified.")`
- **Expect sau fix:** job báo error rõ ràng trên UI; bảng inventory nguyên vẹn; file hợp lệ hành vi không đổi.
- **Checklist evidence:**
  - [ ] 2 test bug: FAIL trước → PASS sau (log cả 2 lần chạy)
  - [ ] Test guard PASS
  - [ ] `tests.test_upload` + `tests.test_pages` green
  - [ ] Snapshot diff chỉ `_last_run`
  - [ ] Cập nhật template inventory.html nếu message đổi (đồng bộ U-11)

### BUG C-01 — 4 CNV AJAX view dùng @requires_perm (redirect thay vì 401)
- **File:** `App/cnv/views.py:138, 238, 309, 382`
- **Quyết định:** FIX — thay bằng `_ajax_perm_check` (pattern của shop_detail.py).
- **Ảnh hưởng số:** KHÔNG (chỉ đổi hành vi khi CHƯA đăng nhập; user hợp lệ không đổi gì).
- **Test TRƯỚC fix** (file mới `tests/test_cnv_auth.py`):
  - `test_customer_tab_unauthenticated_returns_4xx_not_redirect`: client chưa login GET customer_tab → **hiện tại: 302 (FAIL)** → sau fix: 401/403
  - Tương tự cho `sync_cnv_points`, `trigger_sync`, `trigger_zalo_sync` (POST)
  - GUARD `test_customer_tab_authenticated_still_200`: user có quyền cnv.view → 200, nội dung tab không đổi
- **Fix:** thêm helper `_ajax_perm_check` vào cnv/views.py (đã verify pattern gốc shop_detail.py:25-37 — copy được). ⚠️ **Amendment sau verify:** pattern gốc trả HTML fragment — đúng cho `customer_tab` (caller render HTML), nhưng 3 endpoint JSON (`sync_cnv_points`, `trigger_sync`, `trigger_zalo_sync`) phải trả `JsonResponse({'error': 'Session expired'}, status=401)` / `({'error': 'Permission denied'}, status=403)` để JS caller parse được. Viết 2 biến thể helper: `_ajax_perm_check` (HTML) + `_json_perm_check` (JSON).
- **Expect sau fix:** fetch() nhận 401 khi hết session → JS có thể hiện "Phiên hết hạn"; user hợp lệ: y nguyên.
- **Checklist:**
  - [ ] 4 test bug FAIL→PASS · [ ] guard PASS · [ ] full suite green · [ ] snapshot chỉ `_last_run`

### BUG C-08 — Phone search rỗng/ngắn match toàn bảng → lộ data khách lạ
- **File:** `App/api/views.py:950-951`
- **Quyết định:** FIX — bắt buộc ≥ 9 chữ số.
- **Ảnh hưởng số:** KHÔNG (search bằng SĐT đầy đủ hành vi không đổi; chỉ chặn input ngắn/rác).
- **Test TRƯỚC fix** (thêm `tests/test_api.py`):
  - `test_customer_search_short_phone_returns_400`: phone="999" → **hiện tại: 200 + data khách bất kỳ (FAIL)** → sau fix: 400
  - `test_customer_search_no_digit_phone_returns_400`: phone="abc" → hiện tại: 200 + khách ĐẦU TIÊN trong bảng (nghiêm trọng) → sau fix: 400
  - GUARD `test_customer_search_full_phone_still_works`: SĐT 10 số hợp lệ → 200, đúng khách, data y hệt trước fix
- **Fix:** `if len(digits) < 9: return Response({'detail': 'Phone must be at least 9 digits'}, status=400)`
- **Checklist:** [ ] bug FAIL→PASS · [ ] guard PASS (so sánh response JSON trước/sau) · [ ] `tests.test_api` green

### BUG UI-01 + UI-02 — showLoading/hideLoading không tồn tại (8 call sites, coupons.html crash on load)
- **File:** `App/templates/base.html` (thêm), `upload/coupons.html:193`
- **Quyết định:** FIX — define 2 hàm global trong base.html.
- **Ảnh hưởng số:** KHÔNG (pure JS UX).
- **Test TRƯỚC fix:** JS không có unit test trong project → dùng **manual evidence**:
  - Mở coupons.html → console có `ReferenceError` (chụp màn hình TRƯỚC)
- **Fix:** thêm vào base.html block JS: `function showLoading(msg){...}` overlay spinner đơn giản + `function hideLoading(){...}`. Màu dùng CSS token, không hardcode.
- **Expect sau fix:** console sạch lỗi trên cả 5 trang; bấm filter thấy spinner.
- **Checklist:**
  - [ ] Console sạch trên: /coupons/upload, /analytics/, /coupons/, /coupons/chart/, /customer detail (chụp màn hình SAU)
  - [ ] Chạy lại visual snapshot render → 0 token issues
  - [ ] Smoke test 200 cho các trang liên quan

---

## PHASE 2 — LỚP VALIDATION UPLOAD THỐNG NHẤT (quyết định của user)

> **Yêu cầu user:** "tạo 1 lớp validation đủ mạnh để cover data" — gom các bug U-02→U-09, U-11 vào một khung validation chung thay vì vá lẻ tẻ.

### Thiết kế: module mới `App/services/upload_validation.py`

```
validate_upload(file_bytes, filename, upload_type) → ValidationResult
  ├─ 1. Extension check (đã có — giữ)
  ├─ 2. Header check (required columns, strip + case rule thống nhất per type)
  ├─ 3. dtype=str đọc toàn bộ (chặn float-ID, mất số 0 đầu)   ← U-03, U-06
  ├─ 4. Duplicate-key check trong file:                        ← U-04 (user decision)
  │     coupons: coupon_id trùng → RAISE lỗi, liệt kê ID trùng + số dòng
  │     customers: (vip_id, phone) trùng → RAISE, liệt kê
  │     sales: invoice_number trùng → WARN (upsert là chủ đích)
  │     inventory: (shop_id, product_code) trùng → RAISE
  │     sale_detail: (invoice, product, barcode) trùng → WARN (chèn as-is là chủ đích)
  ├─ 5. Zero-valid-rows check (file chỉ có header / toàn dòng rác) ← U-01, U-11
  └─ 6. Trả ValidationResult{ok, errors: list[str], warnings: list[str], row_count}
```

View gọi `validate_upload()` TRƯỚC `create_job()` — lỗi hiện popup/messages ngay, KHÔNG start job.

### Các fix trong phase này:

| Bug | Fix | Test bug (FAIL→PASS) | Test guard (số không đổi) |
|-----|-----|---------------------|---------------------------|
| **U-02** | customers.html Used Points: "Phone Number" → `PHONE NO.` (2 chỗ: bullet + sample table) | `test_used_points_template_shows_correct_header` (parse HTML) | Upload file thật used points vẫn OK |
| **U-03** | coupon_import: `pd.read_*(dtype=str)` | `test_coupon_numeric_id_no_float_suffix`: file có ID số → DB lưu `"123..."` không phải `"123....0"` — **hiện tại FAIL** | `test_real_coupon_file_totals_unchanged`: import file coupon thật → created/updated/tổng face_value **y hệt baseline** |
| **U-04** | (a) Migration `unique=True` cho `Coupon.coupon_id`; (b) validation layer chặn trùng trong file | `test_coupon_dup_in_file_rejected_before_job`: file 2 dòng cùng ID → view trả lỗi, job KHÔNG start — hiện tại FAIL | ⚠️ **TIỀN ĐỀ BẮT BUỘC:** chạy audit script đếm coupon_id trùng trong DB prod + dev TRƯỚC khi migrate. Nếu có trùng → phải có script dedup (giữ bản mới nhất) + backup + approval. Migration unique trên data có trùng sẽ CHẾT giữa chừng. ✅ Verify: `coupon_id` là CharField(max_length=1000) — unique index trên varchar(1000) OK với PostgreSQL 16 (btree limit ~2704 bytes, coupon ID thực tế ngắn + ASCII). |
| **U-05** | Đếm `created` chính xác (dedup trước khi build batch, hoặc dùng return value bulk_create) | `test_created_counter_accurate_with_dup_rows` | Import file thật: counter khớp `Model.objects.count()` delta |
| **U-06** | `file_reader.read_file()`: thêm `dtype=str` — ⚠️ **CÓ TIỀN ĐỀ BẮT BUỘC (verify 2026-07-11):** `safe_int("28.0")` hiện tại raise ValueError → trả **0**! Excel cell float 28.0 đọc với dtype=str thành chuỗi "28.0" → **MỌI QUANTITY VỀ 0** nếu áp dtype=str thô. **BƯỚC 1 (làm trước):** sửa `safe_int` thành fallback `int(float(value))`; viết unit test `safe_int("28")==28`, `safe_int("28.0")==28`, `safe_int("abc")==0`, `safe_decimal("1234.56")`, `parse_date("2026-05-01 00:00:00")` (đã verify parse_date XỬ LÝ ĐƯỢC string datetime — có sẵn format `%Y-%m-%d %H:%M:%S` + fallback pd.to_datetime, dòng 48-57). **BƯỚC 2:** mới thêm dtype=str. Môi trường: pandas 3.0.0. | `test_vip_id_leading_zero_preserved` — hiện tại FAIL | Chạy lại TOÀN BỘ import test với 6 file thật, so từng số với baseline — KHỚP 100% |
| **U-07** | coupon_import: strip headers sau khi đọc | `test_coupon_header_with_whitespace_accepted` — hiện tại FAIL ở service | File thật vẫn import đúng số |
| **U-08** | `create_job()` atomic bằng `cache.add(f"upload_lock_{type}", ...)`, view check kết quả | `test_concurrent_upload_second_rejected` (mock 2 request) | Upload đơn lẻ không đổi hành vi |
| **U-09** | coupon errors: int → list chi tiết | `test_coupon_errors_returned_as_list` | Job result structure các type khác không đổi |
| **U-10** | File-hash guard: lưu SHA256 vào job record, warn nếu trùng hash trong 24h (sale_detail) | `test_same_file_hash_warns` | Upload file mới không đổi |
| **U-11** | Sửa text inventory.html khớp hành vi mới của U-01 | Review thủ công | — |
| **U-12** | (Defer sang refactor) sales_import chỉ load VIP IDs có trong file | — | Ghi nhận, không làm phase này |

- **Ảnh hưởng số toàn phase:** KHÔNG ĐƯỢC ĐỔI. Sau khi xong toàn phase: import lại **cả 5 file input thật** (`customer.xlsx`, `Sale 2024/2025/2026.xlsx`, `coupon_1 (1).xlsx`, `inventory.xlsx`, `sale detail.xlsx`, `1.5 - 10.5.xlsx`) → mọi tổng (count/qty/amount) khớp baseline 100%. Evidence: bảng so sánh before/after từng file.
- **Checklist phase:**
  - [ ] Audit coupon_id trùng trong DB (script + kết quả đính kèm evidence) — TRƯỚC migration
  - [ ] Toàn bộ test bug FAIL→PASS
  - [ ] Toàn bộ test guard PASS
  - [ ] Import 6 file thật → số khớp baseline (bảng evidence)
  - [ ] Full suite green · [ ] Snapshot chỉ `_last_run` · [ ] Docs cập nhật (project_business_logic.md — upload flow)

---

## PHASE 3 — CNV / API (theo quyết định user)

### BUG C-02 — Grade donut mobile luôn rỗng `[SỐ SẼ ĐỔI — CÓ CHỦ ĐÍCH]`
- **Quyết định:** FIX — dùng `_compute_grade_rows()` như web.
- **Số đổi:** donut từ `slices: []` → slices có Member/Silver/Gold/Diamond thật. **Số phải KHỚP với web Customer Analytics cùng khoảng ngày** (parity test).
- **Test TRƯỚC:** `test_customer_chart_grade_donut_not_empty` — hiện tại FAIL; `test_grade_donut_matches_web_analytics` — parity với `_compute_grade_rows` trực tiếp.
- **Checklist:** [ ] FAIL→PASS · [ ] parity web==API · [ ] approval số mới trước merge

### BUG C-03 — Sync crash TypeError khi record thiếu ngày
- **Quyết định user:** "bỏ qua nhưng vẫn raise warning" — skip record + `logger.warning`, KHÔNG crash.
- **Test TRƯỚC:** `test_sync_range_record_without_dates_skipped_with_warning`: mock 3 records (1 thiếu cả 2 ngày) → **hiện tại: TypeError (FAIL)** → sau fix: 2 records xử lý, 1 skip, có warning log (assertLogs).
- **Fix:** lọc bằng walrus/guard, đếm `skipped_no_date`, log warning kèm customer id.
- **Checklist:** [ ] FAIL→PASS · [ ] sync bình thường không đổi (guard với records đủ ngày)

### BUG C-04 — JWT refresh không rotate
- **Quyết định:** FIX nhưng ⚠️ **CÓ RỦI RO TƯƠNG THÍCH MOBILE APP**: nếu blacklist token cũ ngay, app cũ (không lưu refresh mới) sẽ bị logout ở lần refresh sau.
- **Kế hoạch an toàn:** (1) API trả THÊM field `refresh` mới trong response (app cũ bỏ qua field lạ — không hỏng), (2) CHƯA blacklist token cũ ở release này, (3) sau khi app mobile update lưu refresh mới → bật blacklist ở release sau. 2 bước, có feature flag.
- **Test:** `test_refresh_returns_new_refresh_token`; `test_old_refresh_still_valid_phase1` (giai đoạn 1).
- **Checklist:** [ ] test pass · [ ] mobile app team được thông báo (ghi vào docs/project_mobile.md)

### BUG C-05 — OAuth GET lộ client_secret
- **Fix:** `requests.get(params=)` → `requests.post(data=)`.
- **Test:** `test_token_exchange_uses_post` (mock requests, assert method + secret không nằm trong URL).
- **Checklist:** [ ] test pass · [ ] verify flow SSO thật trên staging nếu có

### BUG C-06 — sync_cnv_points không giới hạn
- **Quyết định user:** KHÔNG hard-chặn. (a) FE: popup confirm hiển thị số lượng ID trước khi gửi (chống spam vô ý), (b) BE: chuyển sang background job (dùng pattern `upload_jobs`) để không nghẽn request thread.
- **Test:** `test_sync_points_returns_job_id` (BE trả job id ngay, xử lý nền); FE confirm — manual evidence (screenshot).
- **Checklist:** [ ] BE job pattern hoạt động + progress · [ ] FE confirm popup screenshot · [ ] số điểm sync ra vẫn đúng (so 1 mẫu khách trước/sau)

### BUG C-07 — Zalo sync race đa process
- **Quyết định user:** production solution — lock thật.
- **Fix:** (1) `cache.add("zalo_sync_lock", timestamp, timeout=3600)` làm distributed lock. ✅ **Đã verify settings.py:197-220:** PROD dùng **Redis** (django_redis) → `cache.add` atomic cross-process, giải pháp ĐỨNG VỮNG trên production. Dev dùng locmem (single-process runserver — không sao). (2) tạo DB log TRƯỚC khi set flag in-memory, (3) release lock trong `finally` (test cả exception path).
- **Test:** `test_second_zalo_sync_rejected_while_running` (tạo log running → gọi trigger → expect từ chối).
- **Checklist:** [ ] test pass · [ ] xác nhận cache backend prod (đọc settings prod) · [ ] lock được giải phóng khi sync crash (test exception path)

### BUG C-09 — Scheduler chạy 1h thay vì 10 phút
- **Quyết định user:** sửa code thành ĐÚNG 10 phút/lần.
- **Fix:** customers `minute="5,15,25,35,45,55"`, orders `minute="0,10,20,30,40,50"`.
- ⚠️ **Lưu ý QA:** tải API CNV tăng 6× — xác nhận rate limit CNV chịu được (hiện có _RateLimiter 50/s và checkpoint incremental nên mỗi lần sync sẽ nhỏ hơn — chấp nhận được, nhưng ghi nhận).
- **Test:** `test_scheduler_cron_config_every_10_min` (assert trigger fields, không cần chạy thật).
- **Checklist:** [ ] test pass · [ ] docstring/log message sửa khớp · [ ] theo dõi sync log 1 giờ đầu sau deploy (6 lần chạy/giờ/loại)

### BUG C-10 — TTL cache lệch 600 vs 300
- **Fix:** `timeout=600` → `timeout=300` tại service.py:70.
- **Test guard:** KPI CNV trước/sau fix giống hệt (chỉ đổi thời gian sống cache).
- **Checklist:** [ ] guard pass · [ ] snapshot CNV không đổi

### BUG C-11 — Import private cross-module
- **Fix:** api/views.py (2 chỗ) import thẳng `from App.cnv.service import parse_cnv_period_filter`.
- **Test guard:** `tests.test_api` green nguyên vẹn (hàm delegate giống hệt hàm gốc).
- **Checklist:** [ ] full API tests green

---

## PHASE 4 — ANALYTICS (theo quyết định user)

### BUG A-01 — total_amount tính trên list bị cap — `[RECLASSIFIED: LATENT, fix KHÔNG đổi số]`
- **File:** `App/analytics/customer_utils.py:474` + docstring stale dòng 411
- **Verify 2026-07-11:** KHÔNG caller nào truyền `max_invoices` (đã grep: api/views.py:963 và customer.py:60 đều dùng default None). Bug chỉ kích hoạt nếu tương lai có ai truyền cap. Docstring dòng 411 nói "API calls with max_invoices=50" — SAI so với code thực.
- **Test TRƯỚC:**
  - `test_total_amount_equals_db_aggregate_when_capped`: gọi TRỰC TIẾP hàm với max_invoices=5, khách 10 hóa đơn → **hiện tại FAIL** (tổng 5 đơn) → sau fix PASS (tổng 10 đơn)
  - GUARD `test_api_customer_detail_amount_unchanged`: API response y hệt baseline (vì API không cap)
  - GUARD `test_web_customer_detail_amount_unchanged`: web y hệt baseline
- **Fix:** `total_amount = qs.aggregate(s=Sum('settlement_amount'))['s'] or Decimal(0)` — tính trên queryset CHƯA cắt. Đồng thời sửa docstring 411 khớp thực tế. total_amount GIỮ settlement_amount (định nghĩa "tổng chi tiêu" — A-04 chỉ đổi coupon_amount).
- **Checklist:** [ ] FAIL→PASS · [ ] 2 guard PASS (số y hệt baseline — không cần approval vì không đổi số) · [ ] docstring sửa

### BUG A-02 — Shop-season vs global-season returning lệch — user: CHỦ ĐÍCH, note kỹ
- **Quyết định:** KHÔNG sửa code. Document đầy đủ.
- **Việc làm:**
  1. Docstring `aggregate_by_shop()` (aggregators.py ~471): giải thích shop-scoped first-date là chủ đích, kèm ví dụ ca lệch (khách mua 2 shop cùng ngày đăng ký)
  2. `docs/project_analytics.md`: mục "Known intentional divergence: shop returning ≠ sum(global returning)"
  3. **Test khóa hành vi:** `test_shop_season_returning_is_shop_scoped_intentional` — dựng đúng ca lệch, assert hành vi HIỆN TẠI (khách không tính returning ở shop B) + comment link tới docs. Để dev tương lai đụng vào là test kêu.
- **Checklist:** [ ] docstring · [ ] docs · [ ] test khóa PASS · [ ] KHÔNG có số nào đổi

### BUG A-04 — coupon_amount 2 nơi 2 field `[SỐ SẼ ĐỔI — CÓ CHỦ ĐÍCH]` — user: dùng sales_amount
- **File:** `App/analytics/customer_utils.py:469` (đổi `inv.settlement_amount` → `inv.sales_amount`)
- ✅ **Verify 2026-07-11:** grep 15 call sites của `calc_coupon_amount` — dòng 469 là chỗ DUY NHẤT dùng `settlement_amount`. Các chỗ khác dùng `sales_amount` trực tiếp hoặc qua biến `inv_amount`/`final_amount`. ⚠️ Khi fix: xác minh nguồn của `final_amount` tại tab_functions.py:716 và coupon_analytics.py:332 (kỳ vọng dẫn xuất từ sales_amount — nếu không thì báo cáo trước khi sửa).
- **Số đổi:** `coupon_amount` trên Customer Detail (web + mobile API). Coupon Dashboard KHÔNG đổi (đã dùng sales_amount).
- **Test TRƯỚC:**
  - `test_coupon_amount_uses_sales_amount`: khách có invoice sales_amount ≠ settlement_amount + coupon → **hiện tại FAIL** → sau fix PASS
  - `test_coupon_amount_matches_coupon_dashboard`: cùng docket → customer detail coupon_amount == số trên coupon analytics (parity) — **hiện tại FAIL** → sau fix PASS
  - GUARD: coupon dashboard tổng không đổi
- **Checklist:** [ ] FAIL→PASS · [ ] parity PASS · [ ] guard dashboard PASS · [ ] before/after 3 khách mẫu có coupon · [ ] approval

### BUG A-05 — defaultdict cache theo reference
- **Fix:** `dict(customer_purchases)` trước khi `_djc.set(...)` (tab_functions.py:103).
- **Test guard:** toàn bộ tab sales/season/shop snapshot y hệt (defaultdict→dict không đổi nội dung); `test_cached_purchases_is_plain_dict`.
- **Checklist:** [ ] guard PASS · [ ] snapshot chỉ `_last_run`

### BUG A-06 — Zalo OA sort sai field (LOW)
- **Quyết định:** sửa sort sang `cnv_created_at` — chỉ đổi THỨ TỰ hiển thị danh sách, không đổi số đếm/tổng.
- **Test:** `test_zalo_oa_list_sorted_by_cnv_created_at`; guard: count/tổng OA không đổi.
- **Checklist:** [ ] test PASS · [ ] KPI Zalo không đổi

### BUG A-07 — Nhãn M11-1 thiếu năm `[NHÃN ĐỔI — text, không phải số]`
- **Fix:** get_session_for_range() trả nhãn kèm năm, format khớp get_session_key().
- **Test:** `test_session_for_range_m11_label_has_year` (Nov 2024–Jan 2025 → "M11-1 2024-2025"); `test_session_for_range_regular_season_label`.
- ⚠️ Snapshot nào chứa nhãn này sẽ đổi TEXT — liệt kê trước, regen có chủ đích.
- **Checklist:** [ ] test PASS · [ ] liệt kê snapshot đổi nhãn (chỉ label, số giữ nguyên)

### BUG A-08 — Coupon period 100% usage — user: TẠM SKIP
- **Quyết định:** DEFER. Ghi nhận vào docs/project_analytics.md mục "Known display semantics" để không ai tưởng là bug mới. Không code.

### BUG A-03 — ĐÃ BÁC BỎ (Django 6.0.2 bỏ Meta.ordering khỏi GROUP BY từ 3.1) — KHÔNG làm gì.

---

## PHASE 5 — UI/TEMPLATE (sau các phase số liệu)

| Bug | Fix | Verify |
|-----|-----|--------|
| UI-03 | register.html: conditional `{% if 'error' in message.tags %}danger{% endif %}` như base.html | Trigger lỗi đăng ký → alert đỏ hiện đúng (screenshot) |
| UI-04 | `color:#000` → `var(--text)` ở analytics + coupon dashboard | Visual snapshot light+dark, 0 token issues |
| UI-05 | Badge Silver khác Member (Member giữ bg-secondary, Silver thêm treatment riêng theo token) | Screenshot customer detail 5 hạng |
| UI-06 | Xóa CSS .badge-level-vip0..3; grep xác nhận không còn chỗ nào xuất class này | grep 0 kết quả |
| UI-07 | Header "Customer Details" thêm `background:var(--primary);color:#fff` | Visual snapshot |
| UI-08 | `#6c757d` → `var(--text-muted)` trong chart.html JS | grep + visual |
| UI-10 | colspan 11→10 season.html | Review |
| UI-11 | Xóa CSS trùng trong _product_partial.html (giữ bản ở shop_detail.html) | Shop detail render không đổi (visual so sánh) |
| UI-09 | DEFER sang refactor (đổi hệ tab đụng chạm lớn) | Ghi nhận |
| UI-12 | Chạy snapshot_render.py + snapshot_visual.py sau TẤT CẢ fix template → PNG + `_index.md` 0 token issues | **Bắt buộc** — evidence chính của phase |

- **Ảnh hưởng số:** KHÔNG. Toàn bộ snapshot JSON phải chỉ khác `_last_run`.
- **Checklist phase:** [ ] tất cả fix xong · [ ] visual snapshot regen, mở PNG review từng trang (QA phase rule) · [ ] 0 token issues · [ ] full suite green

---

## PHASE 6 — TEST COVERAGE BỔ SUNG (từ audit, sau khi các fix xong)

- [ ] `compute_cnv_breakdown(store_filter=...)` — path Shop Detail chưa có test
- [ ] used_points view-level test (đang thiếu trong UploadViewHeaderValidationTests)
- [ ] Customer import: dup (vip_id, phone) trong cùng file
- [ ] CouponCampaign multi-prefix matching
- [ ] `create_empty_bucket()` shape test
- [ ] Snapshot data quality: (a) mở rộng cửa sổ ngày sale detail test data (hiện 23 ngày, 1 mùa — không cover M11-1 cross-year ở product tabs), (b) product_season "2012 9" amount=0 → điều tra data nguồn, note hoặc loại, (c) shop_detail_customer anchor đổi từ warehouse (2 khách) sang retail store đông
- [ ] Chuyển SalesImportTest setUp → setUpTestData
- [ ] test_reimport_adds_rows: thêm comment "intentional business rule" (tránh dev sau tưởng bug)

---

## THỨ TỰ THỰC HIỆN & TRẠNG THÁI

| # | Phase | Phụ thuộc | Trạng thái |
|---|-------|-----------|-----------|
| 0 | Baseline + Guard tests G1–G7 | — | ☐ |
| 1 | Critical: U-01, C-01, C-08, UI-01/02 | Phase 0 | ☐ |
| 2 | Upload validation layer (U-02..U-11) | Phase 0 | ☐ |
| 3 | CNV/API: C-02..C-11 | Phase 0 | ☐ |
| 4 | Analytics: A-01, A-02(doc), A-04, A-05, A-06, A-07 | Phase 0 | ☐ |
| 5 | UI + visual snapshot | Phase 1–4 | ☐ |
| 6 | Coverage bổ sung | Phase 1–5 | ☐ |

**Quy tắc chung:**
- KHÔNG commit khi chưa có approval của user (rule của project).
- Mỗi bug xong → tick checklist + evidence vào `tests/output/bugfix_evidence/<BUG-ID>/` → báo cáo user trước khi sang bug kế.
- 4 bug `[SỐ SẼ ĐỔI]` (A-01, A-04, C-02, A-07-label): trình bảng before/after, chờ approval riêng từng cái.
- Sau mỗi PHASE: chạy "testing for release" checklist trong CLAUDE.md.
