---
name: prod-visual
description: Production visual regression — chụp/so sánh screenshot toàn bộ màn hình + tabs của https://analytics-customer-dashboard.com quanh thời điểm deploy. Dùng khi user nói "chụp baseline production", "verify production sau deploy", "prod visual", "so sánh màn hình production". Luôn thực hiện với vai trò QA Senior Leader.
---

# Production Visual Regression (QA Senior Leader)

**Vai trò bắt buộc:** Thực hiện mọi bước dưới tư cách **QA Senior Leader** — không chỉ chạy lệnh, mà phải TỰ MỞ VÀ REVIEW ẢNH bằng mắt (Read từng PNG), đánh giá, và ra verdict có chữ ký. Không bao giờ báo "done" khi chưa nhìn ảnh.

## Công cụ

`SemirDashboard/tests/prod_visual.py` — Playwright, login thật vào production, chụp full-page **mọi trang + mọi tab dữ liệu**.

Credentials: `SemirDashboard/tests/prod_visual.env` (gitignored — KHÔNG đọc ra chat, KHÔNG commit).
Ảnh: `SemirDashboard/tests/prod_snapshots/` (gitignored). `PROD_VIP_ID` (optional) để chụp Customer Detail có data.

## 📋 BASELINE HIỆN TẠI (chụp 2026-07-12, version production pre-2.3.0-deploy)

**64 screenshots** — inventory đầy đủ trong `prod_snapshots/baseline/_manifest.txt`:

| Trang | Ảnh | Phủ những gì |
|-------|-----|--------------|
| 01_home | 1 | Trang chủ + action cards |
| 02_sales_analytics | 9 | Base (By VIP Grade) + 8 lazy tab: by_season, by_month, by_week, by_shop, grade/season/month/week All-Shops |
| 03_sales_chart | 1 | Chart mặc định |
| 04_coupons | 3 | Base (By Shop) + Coupon Detail + Duplicate Invoices |
| 05_coupon_chart | 1 | Chart mặc định |
| 06_shop_detail | 16 | Base + **6 section** (salesShopSel/customerShopSel/couponShopSel/campaignSel/inventoryShopSel/productShopSel — mỗi section: chọn option index 1 + **bấm nút Load**) + **9 sub-tab product** (month/year/week/sales_season/product_season/vip_grade/brand/category/product) |
| 07_customer_detail | 1 | Form search (PROD_VIP_ID chưa cấu hình → chưa có shot data khách) |
| 08_products | ~14 | Base (month) + data-tab: year/week/sales_season/product_season/vip_grade/brand/category/campaign/product/top_by_brand/top_by_campaign + data-stab shop |
| 09_inventory | 1 | Dashboard (collapse sections, không tab) |
| 10_cnv_customer | ~10 | 7 tab Breakdown (bd_season/month/week/shop + 3 AllShops) + ca_points/ca_zalo/ca_pos_cnv |
| 11_cnv_chart | 1 | Chart mặc định |
| 12_cnv_sync_status | 1 | Sync logs |
| 13-16_upload_* | 4 | 4 trang upload (customers+used_points, sales+sale_detail, coupons, inventory) |
| 17_users | 2 | Users + Roles tab |
| 18_formulas | 1 | Trang công thức |

Kết quả review baseline lần đầu: 0 trang lỗi; đã phát hiện & fix trong tool: Shop Detail cần **click nút Load** sau khi chọn dropdown (select không tự load).

## ⚠️ COVERAGE RULE — check code trước mỗi lần baseline

Trước khi chụp baseline mới, PHẢI đối chiếu tool với code hiện tại để không miss màn hình mới:
1. `grep "path(" SemirDashboard/App/urls.py App/cnv/urls.py` — so route với `PAGES` list trong prod_visual.py
2. `grep -rn "data-bs-toggle=.tab.\|data-tab=\|data-stab=" App/templates/ | wc -l` — tab mới tự động được bắt bởi selector generic, nhưng nếu xuất hiện PATTERN tab mới (không phải 3 loại trên) → phải bổ sung vào `_click_all_tabs`
3. Trang có dropdown+Load mới (kiểu Shop Detail) → thêm id vào list `selects` trong `_capture_shop_detail`
4. So `_manifest.txt` với lần trước: số ảnh GIẢM = có màn hình bị mất → điều tra trước khi tiếp tục

## Quy trình quanh deploy

```powershell
cd D:\New-jouney\semir\SemirDashboard
$env:PYTHONIOENCODING="utf-8"
python tests\prod_visual.py baseline    # NGAY TRƯỚC deploy
# (deploy)
python tests\prod_visual.py verify      # NGAY SAU deploy → report.html
python tests\prod_visual.py accept      # chỉ khi mọi diff là chủ đích
```
Chạy nhanh 1 nhóm: `--pages sales,coupon`. Không chạy 2 phiên song song (chung account).

## 📤 OUTPUT VERIFY BẮT BUỘC — checklist chi tiết chứng minh đã check

Sau `verify`, báo cáo cho user PHẢI theo đúng format sau (không được tóm tắt chung chung):

```
## VERIFY REPORT — <version> @ <timestamp>

### 1. Coverage reconciliation
- Baseline: NN ảnh · Current: NN ảnh · MISSING: <liệt kê hoặc "0">

### 2. Bảng kết quả TỪNG ảnh (đủ 64+ dòng, không rút gọn nhóm PASS thành "...")
| # | Screenshot | Diff % | Status | Phân loại | Đã mở xem? | Ghi chú |
|---|-----------|--------|--------|-----------|------------|---------|
| 1 | 01_home | 0.000% | PASS | — | — | |
| 2 | 02_sales_analytics | 0.42% | FAIL | (b) data-trôi | ✅ đã xem diff | vùng đỏ = 3 dòng Customer Details mới |
...

Phân loại FAIL: (a) chủ-đích release / (b) data-trôi / (c) BUG-BLOCKER
Quy tắc "Đã mở xem?": MỌI ảnh FAIL phải được Read và mô tả vùng đỏ nằm ở đâu;
tối thiểu 5 ảnh PASS ngẫu nhiên cũng phải mở xác nhận không trắng trang.

### 3. Blockers (c): <liệt kê + ảnh diff đính kèm, hoặc "KHÔNG CÓ">
### 4. Verdict: ✅ RELEASE VERIFIED / ❌ BLOCKED (lý do)
### 5. Khuyến nghị: accept / rollback / fix-forward
### 6. Chữ ký: QA Senior Leader — <timestamp>
```

## Lưu ý kỹ thuật
- Ngưỡng FAIL 0.10% pixel (`FAIL_THRESHOLD_PCT`); tolerance 16/kênh màu chống anti-aliasing
- FAIL do timestamp/đồng hồ → thêm selector vào `MASK_SELECTORS`, KHÔNG nâng ngưỡng
- Tool chỉ GET — an toàn production; TUYỆT ĐỐI không thêm bước submit form upload/sync
- Console Windows: luôn set `PYTHONIOENCODING=utf-8` trước khi chạy
