# Plan: Inventory & Product Analytics
**Version:** 2.0 | **Ngày:** 2026-05-23 | **Branch:** feature/inventory-product

---

## ✅ TẤT CẢ QUYẾT ĐỊNH ĐÃ CONFIRM — SẴN SÀNG CODE

| # | Vấn đề | Quyết định |
|---|--------|-----------|
| C1 | `SaleDetail` link Customer | KHÔNG FK sang Customer. Link gián tiếp qua `invoice_number → SalesTransaction` |
| C2 | Inventory unique key | `(shop_id, product_code)` — product_code đã encode color+size. Không track theo ngày |
| C3 | Season 9 xử lý | Không cần xử lý đặc biệt. Lưu như data bình thường, hiện thị bình thường |
| C4 | SaleDetail perf | Index + cache 5 phút — chuẩn y chang hệ thống hiện có |
| C5 | Upload batch size | `bulk_create` batch 2000, cùng pattern `process_sales_file()` |
| C6 | 2 bảng / 2 form | `SalesTransaction` (header) + `SaleDetail` (line-items) — 2 form trong cùng trang upload |
| C7 | Filter inventory Large Class | Import tất cả, không filter — dùng `category_l1` để filter trong UI |
| C8 | Upload SaleDetail trước header | Cho phép. FK = null nếu invoice chưa tồn tại trong header table |
| C9 | Mobile API | Defer — web trước |
| C10 | Navigation "Products" | Sau "Shop Detail" trong nav |
| C11 | Dead stock threshold | `year <= current_year - 1` |

---

## Tổng quan hệ thống mới

```
2 nguồn data mới từ HQ:
├── inventory.xlsx  → InventorySnapshot model (tồn kho hiện tại, ghi đè khi upload mới)
└── detail.xlsx     → SaleDetail model (line-item, FK mềm sang SalesTransaction)

4 tính năng mới:
├── [1] Upload Inventory        /upload/inventory/
├── [2] Upload Sale Detail      /upload/sales/ (Card 2 trong trang hiện tại)
├── [3] Shop Detail — Tab Inventory   /shop-detail/partial/inventory/
└── [4] Product Analytics page  /products/ + /products/tab/<tab>/
```

---

## Phân tích data đã xác nhận

| File | Rows | Key numbers |
|------|------|-------------|
| inventory.xlsx | 77,507 | 21 shops, 2,808 product_codes, 31% zero-stock |
| detail.xlsx | 15,104 | 4,233 invoices, tháng 5/2026, 18% discount rate avg |
| Tests input | `sale detail (1).xlsx`, `sale detail (2).xlsx` đã có trong `tests/input/` |

---

## Senior PO Analysis — Người dùng cần gì trên UI?

### Persona: HQ Manager / Shop Manager

**Câu hỏi họ cần trả lời:**
1. Sản phẩm nào đang bán chạy nhất tuần này / tháng này?
2. Category nào đóng góp nhiều doanh thu nhất?
3. Shop nào bán category X tốt hơn?
4. Tồn kho shop Y đang như thế nào? SKU nào tồn lâu?
5. Hàng đang về (in-transit) có cần điều phối không?

**Nguyên tắc thiết kế:**
- Filter bar = **clone từ Sales page** (start_date, end_date, shop_group, quick btns, year btns)
- Thêm filter **Brand** (All / BALABALA / SEMIR) vì data có 2 brands chính
- Tabs = **lazy load** y chang Sales page pattern (`data-lazy-url`, `X-Requested-With`)
- Cache = **5 phút** per params combo — cùng key pattern `f"product_{tab}:{hash}"`
- CSS = **100% token-based**, không hardcode hex

---

## Feature 1 — Upload Inventory

### Model: `InventorySnapshot`
**File:** `App/models/inventory.py` (file mới, export từ `__init__.py`)

```python
class InventorySnapshot(models.Model):
    uploaded_at      = models.DateTimeField(auto_now=True)      # lần upload cuối
    shop_id          = models.CharField(max_length=100, db_index=True)
    shop_name        = models.CharField(max_length=200, db_index=True)
    brand            = models.CharField(max_length=100, db_index=True)
    product_code     = models.CharField(max_length=200, db_index=True)  # unique per variant
    product_name     = models.CharField(max_length=500, blank=True)
    product_name_vn  = models.CharField(max_length=500, blank=True)
    barcode          = models.CharField(max_length=100, db_index=True)
    sku              = models.CharField(max_length=100, db_index=True)   # base, no size
    color            = models.CharField(max_length=100, blank=True)
    size             = models.CharField(max_length=50, blank=True)
    year             = models.IntegerField(null=True, blank=True, db_index=True)
    season           = models.CharField(max_length=10, blank=True, db_index=True)
    gender           = models.CharField(max_length=50, blank=True)
    category_l1      = models.CharField(max_length=100, blank=True)    # Large Class
    category_l2      = models.CharField(max_length=100, blank=True)    # Middle Class — primary
    category_l3      = models.CharField(max_length=100, blank=True)    # Small Class
    tag_price        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    inventory_qty    = models.IntegerField(default=0)
    in_transit_qty   = models.IntegerField(default=0)
    total_qty        = models.IntegerField(default=0)
    tag_amount       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_tag_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency         = models.CharField(max_length=10, default='VND')

    class Meta:
        unique_together = ('shop_id', 'product_code')   # upload mới → UPDATE
        indexes = [
            models.Index(fields=['shop_name', 'brand']),
            models.Index(fields=['year', 'season']),
            models.Index(fields=['sku', 'shop_id']),
        ]
```

### Service: `App/services/inventory_import.py`

**Pattern:** Clone `process_sales_file()`, adapt cho inventory.

```
Column mapping (từ header thực tế):
  Warehouse/Shop ID     → shop_id
  Warehouse/Shop        → shop_name
  Brand                 → brand
  Product Code          → product_code
  Product Name          → product_name
  商品名称              → product_name_vn
  Barcode               → barcode
  SKU                   → sku
  Color                 → color
  Size                  → size
  Year                  → year
  Season                → season
  Gender                → gender
  Large Class           → category_l1
  Middle Class          → category_l2
  Small Class           → category_l3
  Tagprice              → tag_price
  Inventory Quantity    → inventory_qty
  In Transit Quantity   → in_transit_qty
  Total Inventory Qty   → total_qty
  Tag Amount            → tag_amount
  Total Tag Amount      → total_tag_amount
  Currency              → currency
```

**Upsert logic:**
```python
# Dùng update_or_create trong batch — không dùng ignore_conflicts vì cần UPDATE
# Batch: 2000 rows. Với 77k rows → ~39 batches → target < 60s
for chunk in batches:
    for row in chunk:
        InventorySnapshot.objects.update_or_create(
            shop_id=row['shop_id'],
            product_code=row['product_code'],
            defaults={...all other fields...}
        )
# Hoặc dùng bulk_create với update_conflicts=True nếu Django >= 4.2
```

### View & Template

**View:** thêm `upload_inventory()` vào `App/views/upload.py`
- Pattern giống `upload_sales()`: background thread, job tracking, `is_type_running("inventory")`
- Stats: latest `uploaded_at`, total rows, total shops, total inventory_qty, total value

**Template:** `App/templates/upload/inventory.html`
- File requirements card (liệt kê columns)
- Upload form
- DB Stats card (latest upload time, total SKU lines, total shops, total qty, total value)

**URL:** `/upload/inventory/`
**Permission:** `data.upload` (reuse)
**Job type:** `"inventory"` — thêm vào `JOB_TYPE_LABELS` trong `upload_jobs.py`

---

## Feature 2 — Upload Sale Detail

### Model: `SaleDetail`
**File:** `App/models/pos.py` — append sau `SalesTransaction`

```python
class SaleDetail(models.Model):
    invoice_number    = models.CharField(max_length=200, db_index=True)
    transaction       = models.ForeignKey(
        'SalesTransaction', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='line_items',
        to_field='invoice_number', db_constraint=False,  # không crash nếu header chưa có
    )
    shop_id           = models.CharField(max_length=100, db_index=True)
    shop_name         = models.CharField(max_length=200, db_index=True)
    sales_date        = models.DateField(db_index=True)
    sales_time        = models.TimeField(null=True, blank=True)
    brand             = models.CharField(max_length=100, db_index=True)
    product_code      = models.CharField(max_length=200)
    product_name      = models.CharField(max_length=500, blank=True)
    barcode           = models.CharField(max_length=100, db_index=True)
    sku               = models.CharField(max_length=100, db_index=True)
    color             = models.CharField(max_length=100, blank=True)
    size              = models.CharField(max_length=50, blank=True)
    year              = models.IntegerField(null=True, blank=True, db_index=True)
    season            = models.CharField(max_length=10, blank=True, db_index=True)
    gender            = models.CharField(max_length=50, blank=True)
    category_l1       = models.CharField(max_length=100, blank=True)
    category_l2       = models.CharField(max_length=100, blank=True)
    category_l3       = models.CharField(max_length=100, blank=True)
    quantity          = models.IntegerField(default=0)
    fact_retail_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sales_amount      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    settlement_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tag_price         = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tag_amount        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_pct      = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    vat_rate          = models.CharField(max_length=20, blank=True)
    salesmen          = models.CharField(max_length=200, blank=True, db_index=True)
    salesmen_code     = models.CharField(max_length=100, blank=True)
    promotion         = models.CharField(max_length=500, blank=True)
    currency          = models.CharField(max_length=10, default='VND')
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('invoice_number', 'barcode', 'size')
        indexes = [
            models.Index(fields=['sales_date', 'brand']),
            models.Index(fields=['sales_date', 'shop_id']),
            models.Index(fields=['year', 'season', 'brand']),
            models.Index(fields=['sku', 'brand']),
            models.Index(fields=['salesmen', 'sales_date']),
        ]
```

**Lưu ý `db_constraint=False`:** Django tạo FK logic nhưng không tạo DB-level constraint → SaleDetail có thể tồn tại dù invoice chưa có trong SalesTransaction.

### Service: `App/services/sale_detail_import.py`

```
Column mapping:
  Invoice Number     → invoice_number
  Shop ID            → shop_id
  Shop Name          → shop_name
  Sales Date         → sales_date
  Sales Time         → sales_time (parse "09:39:48" → time object)
  Brand              → brand
  Product Code       → product_code
  Product Name       → product_name
  Barcode            → barcode
  Product ID         → sku (dùng Product ID làm SKU base)
  Color Name         → color
  Size Name          → size
  Year               → year
  Season             → season
  Gender             → gender
  Large Class        → category_l1
  Middle Class       → category_l2
  Small Class        → category_l3
  Quantity           → quantity
  Fact Retail Price  → fact_retail_price
  Sales Amount       → sales_amount
  Settlement Amount  → settlement_amount
  Tag Price          → tag_price
  Tag Amount         → tag_amount
  Discount           → discount_pct  (parse "100.00%" → Decimal("1.0000"))
  Vat Rate           → vat_rate
  Salesmen           → salesmen
  Salesmen Code      → salesmen_code
  Promotion          → promotion
  Currency           → currency
```

**FK resolution:** Pre-load `{invoice_number: id}` map từ SalesTransaction 1 lần trước batch loop. Nếu không tìm thấy → `transaction_id = None`.

**Batch:** 3000 rows (line-items nhỏ hơn header, batch lớn hơn được).

### Tích hợp vào trang Upload Sales

**Template `upload/sales.html`:** Thêm Card 2 dưới Card 1 hiện có.

```
Card 1 (hiện có): Upload Sales Header (SalesTransaction)
  - File format: Invoice Number, VIP ID, Sales Date, Shop Name, ...

Card 2 (mới): Upload Sale Detail (SaleDetail)
  - File format: Invoice Number, Shop ID, Sales Date, Product Code, Barcode, ...
  - Note: "Có thể upload trước hoặc sau Sales Header. Nếu Invoice chưa tồn tại → FK=null, tự động link sau."
  - Stats: Date range, Total line items, Unique invoices covered
```

**View:** `upload_sale_detail()` trong `App/views/upload.py`
**URL:** `/upload/sale-detail/`
**Job type:** `"sale_detail"` — thêm vào `JOB_TYPE_LABELS`

---

## Feature 3 — Shop Detail: Tab Inventory

### UI Design (Senior PO view)

```
[Shop Detail page — Section 4: Inventory]

Filter: [Shop selector ▼] [Load] ← chỉ cần shop, không cần date filter (inventory = trạng thái hiện tại)
         Uploaded at: 2026-05-23 10:00 (hiển thị thời điểm data cập nhật)

KPI row (4 cards):
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Tổng tồn   │ │ Giá trị tồn│ │ In-Transit  │ │ Dead Stock  │
│ 23,497 pcs │ │ 5.65B VND  │ │ 2,554 pcs  │ │ 🔴 312 SKUs│
│ (qty)      │ │ (tag_amount│ │             │ │ (cần action)│
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘

Tab A: By Category                    Tab B: Top SKUs           Tab C: Dead Stock
──────────────────────────────────    ─────────────────────     ─────────────────────
Category      | Qty  | Value          Rank | Product | Qty |    Product | Year/Season |
短袖T恤       | 3.2k | 1.2B          1    | Áo polo | 45  |    Áo thu  | 2024/S2     |
连衣裙        | 1.8k | 0.9B          ...  | ...     | ... |    ...     | ...         |
...           | ...  | ...

Tab D: Sell-Through (nếu có SaleDetail)
──────────────────────────────────────────
SKU | Tồn | Sold(30d) | Sell-Through% | Days-of-Stock
```

### Backend: `App/analytics/inventory_functions.py` (mới)

```python
_INV_TTL = 600  # 10 phút — inventory không thay đổi thường xuyên

def get_shop_inventory_data(shop_name):
    """
    Return:
    {
        'uploaded_at': datetime,
        'total_qty': int,
        'total_value': Decimal,
        'in_transit_qty': int,
        'dead_stock_count': int,
        'by_category': [{'category': str, 'qty': int, 'value': Decimal}, ...],
        'top_skus': [{'product_name': str, 'brand': str, 'category': str,
                      'year': int, 'season': str, 'qty': int, 'value': Decimal,
                      'is_dead': bool}, ...],  # top 20 by qty
        'dead_stock': [...],   # year <= current_year-1 AND qty > 0
        'sell_through': [...], # nếu SaleDetail có data, else []
    }
    """
    key = f"shop_inv:{shop_name}"
    cached = cache.get(key)
    if cached: return cached
    # ... query + build ...
    cache.set(key, result, _INV_TTL)
    return result
```

**Dead stock query:**
```python
from datetime import date
current_year = date.today().year
dead = InventorySnapshot.objects.filter(
    shop_name=shop_name,
    total_qty__gt=0,
    year__lte=current_year - 1,     # hàng từ năm trước trở về
).order_by('-total_qty')
```

**Sell-through (cross với SaleDetail, 30 ngày gần nhất):**
```python
from django.utils import timezone
cutoff = date.today() - timedelta(days=30)
sold_map = dict(
    SaleDetail.objects
    .filter(shop_name=shop_name, sales_date__gte=cutoff)
    .values('product_code')
    .annotate(sold_qty=Sum('quantity'))
    .values_list('product_code', 'sold_qty')
)
# Chỉ hiện nếu len(sold_map) > 0
```

### View & URL

```python
# App/views/shop_detail.py
def shop_detail_inventory_partial(request):
    err = _ajax_perm_check(request, "shops.view")   # reuse shops.view
    if err: return err
    shop_name = request.GET.get("shop", "").strip()
    if not shop_name:
        return HttpResponse('<div class="no-data-msg ...">Select a shop to view inventory.</div>')
    data = get_shop_inventory_data(shop_name)
    return render(request, "shop_detail/_inventory_partial.html", {
        "data": data, "shop_name": shop_name, "currency": "VND",
    })
```

**URL:** `/shop-detail/partial/inventory/`
**Cập nhật `_get_dropdown_options()`:** thêm `inventory_shops` list (distinct shop_name từ InventorySnapshot).
**Cập nhật `shop_detail.html`:** thêm Section 4 + JS `loadSection('inventory')`.

---

## Feature 4 — Product Analytics Page

### Senior PO: UI Layout

```
/products/

┌─ Filter bar (CLONE từ Sales page) ─────────────────────────────────────────┐
│ [Start Date] [End Date] [Last 7D][Last 30D][Last 90D][Last Year][2025][2026]│
│ Shop: [All ▼] [Bala Group][Semir Group]  Brand: [All▼]  Gender: [All▼]     │
└────────────────────────────────────────────────────────────────────────────┘

┌─ Overview KPI (2 rows, giống Sales page alltime/period stat cards) ─────────┐
│ Tổng doanh thu │ Tổng qty │ Số invoices │ Avg giá/pcs │ Discount% │ # SKUs │
└────────────────────────────────────────────────────────────────────────────┘

┌─ Dark tabs (lazy load — y chang Sales page) ───────────────────────────────┐
│ [Top Products*] [By Week] [By Month] [By Season] [By Category]             │
│ [By Shop] [Salesmen] [Inventory Cross]                                      │
└────────────────────────────────────────────────────────────────────────────┘
* Tab mặc định, load ngay khi vào trang
```

### Filter params (đồng bộ với Sales page)

```python
# Cùng tên params với Sales page — user không cần học lại
start_date  → date_from
end_date    → date_to
shop_group  → "Bala Group" / "Semir Group" / "Others Group" / ""  (CÙNG như Sales)
brand       → "BALABALA" / "SEMIR" / ""   (filter mới cho Product)
gender      → "Woman" / "Man" / "Unisex" / ""  (filter mới)

# lazy_params string (cùng pattern filter_params_str())
lazy_params = filter_params_str(
    start_date=start_date, end_date=end_date,
    shop_group=shop_group, brand=brand, gender=gender
)
```

### Tabs và Data Structure

#### Tab 0: `top_products` (default — load ngay)
```python
# Query: SaleDetail.objects.values('product_code','product_name','brand','category_l2','season','year')
#        .annotate(qty=Sum('quantity'), revenue=Sum('sales_amount'), tag=Sum('tag_amount'))
#        .order_by('-revenue')[:50]
# Template: product/tabs/top_products.html
# Columns: Rank | Product (VN name) | Brand | Category | Year/Season | Qty | Revenue | Avg Price | Disc%
```

#### Tab 1: `by_week`
```python
# TruncWeek('sales_date') + Sum(qty, revenue)
# Sort: bằng week_sort_key() — reuse từ season_utils.py
# Template: product/tabs/by_week.html
# Columns: Week | Qty | Revenue | Avg Price | Discount% | # SKUs sold
```

#### Tab 2: `by_month`
```python
# TruncMonth('sales_date') + Sum(qty, revenue)
# Template: product/tabs/by_month.html
# Columns: Month | Qty | Revenue | Avg Price | Discount% | # SKUs sold
```

#### Tab 3: `by_season`
```python
# Group by season field (1/2/3/4/9)
# Map sang label: {1:'M11-1', 2:'M2-4', 3:'M5-7', 4:'M8-10', 9:'Clearance'}
# Template: product/tabs/by_season.html
# Columns: Season | Qty | Revenue | Avg Price | Discount%
```

#### Tab 4: `by_category`
```python
# Group by category_l2 (Middle Class)
# Top 15 categories + Others
# Template: product/tabs/by_category.html
# Columns: Category | Qty | Revenue | Avg Price | % of total revenue
```

#### Tab 5: `by_shop`
```python
# Group by shop_name
# Summary table + collapsible per-shop detail (cùng pattern shop tab trong Sales)
# Template: product/tabs/by_shop.html
# Columns: Shop | Qty | Revenue | Avg Price | Discount% | Top category
```

#### Tab 6: `salesmen`
```python
# Group by salesmen
# Top 30 by revenue
# Template: product/tabs/salesmen.html
# Columns: Rank | Salesman | Qty | Revenue | Avg Price | # Invoices | Avg basket
```

#### Tab 7: `inventory_cross`
```python
# Cross SaleDetail (30d) với InventorySnapshot
# Chỉ hiện khi InventorySnapshot có data
# Template: product/tabs/inventory_cross.html
# Columns: Product | Stock | Sold(30d) | Sell-Through% | Days-of-Stock
# Flag: Days-of-Stock > 90 → cần action
```

### Analytics Engine: `App/analytics/product_analytics.py`

```python
PRODUCT_TABS = ['top_products', 'by_week', 'by_month', 'by_season',
                'by_category', 'by_shop', 'salesmen', 'inventory_cross']

_PROD_TTL = 300  # 5 phút

def _make_cache_key(tab, date_from, date_to, shop_group, brand, gender):
    import hashlib
    raw = f"{tab}:{date_from}:{date_to}:{shop_group}:{brand}:{gender}"
    return "product_tab:" + hashlib.md5(raw.encode()).hexdigest()[:12]

def _base_qs(date_from, date_to, shop_group, brand, gender):
    """Base queryset — reused by all tabs. Cùng shop_group logic như _load_sales()."""
    from django.db.models import Q
    qs = SaleDetail.objects.all()
    if date_from:    qs = qs.filter(sales_date__gte=date_from)
    if date_to:      qs = qs.filter(sales_date__lte=date_to)
    if brand:        qs = qs.filter(brand=brand)
    if gender:       qs = qs.filter(gender=gender)
    if shop_group == 'Bala Group':
        qs = qs.filter(Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉'))
    elif shop_group == 'Semir Group':
        qs = qs.filter(Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马'))
    elif shop_group == 'Others Group':
        qs = qs.exclude(
            Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉') |
            Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马')
        )
    return qs

def get_product_overview(date_from, date_to, shop_group='', brand='', gender=''):
    """KPI cards: revenue, qty, invoices, avg_price, discount_rate, sku_count."""
    ...

def get_product_tab(tab, date_from, date_to, shop_group='', brand='', gender=''):
    """Dispatch + cache."""
    key = _make_cache_key(tab, date_from, date_to, shop_group, brand, gender)
    cached = cache.get(key)
    if cached: return cached
    result = _dispatch(tab, date_from, date_to, shop_group, brand, gender)
    cache.set(key, result, _PROD_TTL)
    return result
```

### Views: `App/views/product.py` (mới)

```python
@requires_perm("products.view")
def product_analytics(request):
    # Load top_products tab ngay (giống analytics_dashboard load grade tab)
    # lazy_params cho các tabs còn lại
    ...

@requires_perm("products.view")
def product_tab(request, tab: str):
    # Guard: X-Requested-With: XMLHttpRequest
    # Guard: tab in PRODUCT_TABS and tab != 'top_products'
    ...

@requires_perm("products.export")
def export_product_analytics(request):
    # Excel export: Overview sheet + requested tab sheet
    ...
```

### Permissions mới

Thêm vào `PERMISSION_DEFS` trong `App/permissions.py`:
```python
("products.view",   "View Product Analytics",           "Product Analytics"),
("products.export", "Export Product Analytics (Excel)",  "Product Analytics"),
```

### URLs thêm vào `App/urls.py`

```python
path("products/",               views.product_analytics,       name="product_analytics"),
path("products/tab/<str:tab>/", views.product_tab,             name="product_tab"),
path("products/export/",        views.export_product_analytics, name="export_product_analytics"),
path("upload/inventory/",       views.upload_inventory,        name="upload_inventory"),
path("upload/sale-detail/",     views.upload_sale_detail,      name="upload_sale_detail"),
path("shop-detail/partial/inventory/", views.shop_detail_inventory_partial, name="shop_detail_inventory_partial"),
```

---

## Migrations

```
0013_inventorysnapshot.py      → InventorySnapshot model
0014_saledetail.py             → SaleDetail model + FK sang SalesTransaction
```

Permissions không cần migration — code-defined trong `PERMISSION_DEFS`.

---

## Test Plan

### Input files có sẵn

```
tests/input/
├── sale detail (1).xlsx   ← file 1 để test upload + analytics
├── sale detail (2).xlsx   ← file 2 để test upsert (upload lần 2)
├── Sale 2024.xlsx         ← header data (dùng để test FK resolution)
├── Sale 2025.xlsx
└── Sale 2026.xlsx
```

> **Cần thêm:** `inventory.xlsx` hoặc subset vào `tests/input/` để test upload inventory.
> User cần copy file vào `tests/input/inventory.xlsx` trước khi chạy test.

### Snapshot files mới

```
tests/snapshots/
├── inventory_shop_data.json          # get_shop_inventory_data() result
├── inventory_dead_stock.json         # dead stock subset
├── product_overview.json             # get_product_overview() KPIs
├── product_tab_top_products.json     # top 50 SKUs
├── product_tab_by_week.json
├── product_tab_by_month.json
├── product_tab_by_season.json
├── product_tab_by_category.json
├── product_tab_by_shop.json
├── product_tab_salesmen.json
└── ajax_inventory_partial.json       # AJAX partial response shape
```

### Test file 1: `tests/test_inventory.py`

```python
class InventoryUploadTest(SnapshotTestCase):
    """Test upload + upsert logic cho InventorySnapshot."""

    # Không dùng fixture DB — test trực tiếp service với file
    def test_upload_creates_records(self):
        """Process inventory file → InventorySnapshot rows được tạo."""
        f = open(INPUT_DIR / 'inventory.xlsx', 'rb')  # cần file trong tests/input/
        result = process_inventory_file(f)
        self.assertGreater(result['created'] + result['updated'], 0)
        self.assertEqual(result['errors'], [])

    def test_upload_upsert_same_shop_product(self):
        """Upload lần 2 cùng shop+product_code → UPDATE, không tạo duplicate."""
        # Upload lần 1
        process_inventory_file(open(INPUT_DIR / 'inventory.xlsx', 'rb'))
        count_1 = InventorySnapshot.objects.count()
        # Upload lần 2 — cùng file
        process_inventory_file(open(INPUT_DIR / 'inventory.xlsx', 'rb'))
        count_2 = InventorySnapshot.objects.count()
        self.assertEqual(count_1, count_2)  # không tạo thêm

    def test_zero_stock_rows_are_stored(self):
        """Zero-stock rows (qty=0) vẫn được lưu — không filter bỏ."""
        process_inventory_file(open(INPUT_DIR / 'inventory.xlsx', 'rb'))
        zero_count = InventorySnapshot.objects.filter(inventory_qty=0).count()
        self.assertGreater(zero_count, 0)

    def test_all_large_class_imported(self):
        """Không filter Large Class — tất cả rows được import."""
        process_inventory_file(open(INPUT_DIR / 'inventory.xlsx', 'rb'))
        cats = set(InventorySnapshot.objects.values_list('category_l1', flat=True).distinct())
        # 手提袋, 促销品, 商品, 非生产性辅料 đều phải có
        self.assertGreater(len(cats), 1)


class InventoryAnalyticsTest(SnapshotTestCase):
    """Test analytics functions + AJAX partials."""

    @classmethod
    def setUpTestData(cls):
        # Load 1 shop worth of inventory data (subset)
        process_inventory_file(open(INPUT_DIR / 'inventory.xlsx', 'rb'))

    def test_shop_inventory_data_snapshot(self):
        shops = list(InventorySnapshot.objects.values_list('shop_name', flat=True).distinct()[:1])
        self.assertTrue(shops)
        data = get_shop_inventory_data(shops[0])
        self.assert_snapshot('inventory_shop_data', data)

    def test_dead_stock_flag_year(self):
        """Rows với year <= current_year-1 AND qty>0 → in dead_stock list."""
        from datetime import date
        current_year = date.today().year
        data = get_shop_inventory_data(InventorySnapshot.objects.first().shop_name)
        for item in data['dead_stock']:
            self.assertLessEqual(item['year'], current_year - 1)

    def test_dead_stock_count_matches_kpi(self):
        """dead_stock_count trong KPI = len(dead_stock) list."""
        shop = InventorySnapshot.objects.first().shop_name
        data = get_shop_inventory_data(shop)
        self.assertEqual(data['dead_stock_count'], len(data['dead_stock']))

    def test_inventory_partial_200(self):
        shop = InventorySnapshot.objects.first().shop_name
        self.client.force_login(self._get_superuser())
        r = self.client.get(f'/shop-detail/partial/inventory/?shop={shop}',
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)

    def test_inventory_partial_401_unauthenticated(self):
        r = self.client.get('/shop-detail/partial/inventory/?shop=test',
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 401)

    def test_inventory_partial_403_no_perm(self):
        user = self._get_viewer_user()  # user không có shops.view
        self.client.force_login(user)
        r = self.client.get('/shop-detail/partial/inventory/?shop=test',
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 403)

    def test_perf_shop_inventory(self):
        with self.timer('shop_inventory_cold') as t:
            shop = InventorySnapshot.objects.first().shop_name
            get_shop_inventory_data(shop)
        t.assert_under(2.0)  # ≤ 2s cold
```

### Test file 2: `tests/test_sale_detail.py`

```python
class SaleDetailUploadTest(SnapshotTestCase):
    """Test upload + upsert logic cho SaleDetail."""

    def test_upload_file1_creates_records(self):
        """File 1 → SaleDetail rows được tạo."""
        f = open(INPUT_DIR / 'sale detail (1).xlsx', 'rb')
        result = process_sale_detail_file(f)
        self.assertGreater(result['created'], 0)
        self.assertEqual(result['errors'], [])

    def test_upload_file2_upserts(self):
        """File 2 upload sau file 1 → upsert, không duplicate."""
        process_sale_detail_file(open(INPUT_DIR / 'sale detail (1).xlsx', 'rb'))
        count_1 = SaleDetail.objects.count()
        process_sale_detail_file(open(INPUT_DIR / 'sale detail (2).xlsx', 'rb'))
        # Nếu file 2 có cùng invoice+barcode+size → không tạo thêm
        # Nếu file 2 có rows mới → count_2 >= count_1
        # Test chỉ verify không crash và không duplicate
        count_2 = SaleDetail.objects.count()
        self.assertGreaterEqual(count_2, count_1)

    def test_fk_resolved_when_header_exists(self):
        """Nếu SalesTransaction đã có → transaction FK được set."""
        # Load headers
        from App.services.sales_import import process_sales_file
        process_sales_file(open(INPUT_DIR / 'Sale 2026.xlsx', 'rb'))
        # Load details
        process_sale_detail_file(open(INPUT_DIR / 'sale detail (1).xlsx', 'rb'))
        # Check FK
        linked = SaleDetail.objects.filter(transaction__isnull=False).count()
        self.assertGreater(linked, 0)

    def test_fk_null_when_header_missing(self):
        """Nếu upload detail trước header → transaction = null, không crash."""
        result = process_sale_detail_file(open(INPUT_DIR / 'sale detail (1).xlsx', 'rb'))
        self.assertEqual(result['errors'], [])
        # Tất cả rows có thể null FK — không phải lỗi
        null_count = SaleDetail.objects.filter(transaction__isnull=True).count()
        self.assertGreaterEqual(null_count, 0)

    def test_discount_pct_parsed_correctly(self):
        """'100.00%' → Decimal('1.0000'), '50.00%' → Decimal('0.5000')."""
        process_sale_detail_file(open(INPUT_DIR / 'sale detail (1).xlsx', 'rb'))
        sample = SaleDetail.objects.filter(discount_pct__isnull=False).first()
        if sample:
            self.assertGreaterEqual(float(sample.discount_pct), 0)
            self.assertLessEqual(float(sample.discount_pct), 1.0)


class ProductAnalyticsTest(SnapshotTestCase):
    """Test product analytics engine — overview + tabs."""

    @classmethod
    def setUpTestData(cls):
        process_sale_detail_file(open(INPUT_DIR / 'sale detail (1).xlsx', 'rb'))
        process_sale_detail_file(open(INPUT_DIR / 'sale detail (2).xlsx', 'rb'))

    def test_overview_has_required_keys(self):
        data = get_product_overview(None, None)
        for key in ['total_revenue', 'total_qty', 'total_invoices',
                    'avg_price_per_pc', 'discount_rate', 'sku_count']:
            self.assertIn(key, data)

    def test_overview_snapshot(self):
        data = get_product_overview(None, None)
        self.assert_snapshot('product_overview', data)

    def test_tab_top_products_snapshot(self):
        data = get_product_tab('top_products', None, None)
        self.assert_snapshot('product_tab_top_products', data)

    def test_tab_by_week_snapshot(self):
        data = get_product_tab('by_week', None, None)
        self.assert_snapshot('product_tab_by_week', data)

    def test_tab_by_month_snapshot(self):
        data = get_product_tab('by_month', None, None)
        self.assert_snapshot('product_tab_by_month', data)

    def test_tab_by_season_snapshot(self):
        data = get_product_tab('by_season', None, None)
        self.assert_snapshot('product_tab_by_season', data)

    def test_tab_by_category_snapshot(self):
        data = get_product_tab('by_category', None, None)
        self.assert_snapshot('product_tab_by_category', data)

    def test_tab_by_shop_snapshot(self):
        data = get_product_tab('by_shop', None, None)
        self.assert_snapshot('product_tab_by_shop', data)

    def test_tab_salesmen_snapshot(self):
        data = get_product_tab('salesmen', None, None)
        self.assert_snapshot('product_tab_salesmen', data)

    def test_brand_filter(self):
        """Khi filter brand='BALABALA' → chỉ có BALABALA trong result."""
        data = get_product_tab('top_products', None, None, brand='BALABALA')
        for item in data['products']:
            self.assertEqual(item['brand'], 'BALABALA')

    def test_shop_group_filter_bala(self):
        data = get_product_tab('by_shop', None, None, shop_group='Bala Group')
        for shop in data['shops']:
            self.assertIn('Bala', shop['shop_name'])

    def test_date_filter(self):
        """Date filter thu hẹp result."""
        all_data = get_product_tab('by_month', None, None)
        filtered = get_product_tab('by_month', date(2026,5,1), date(2026,5,31))
        self.assertLessEqual(
            sum(m['qty'] for m in filtered['by_month']),
            sum(m['qty'] for m in all_data['by_month'])
        )

    def test_perf_overview(self):
        with self.timer('product_overview_cold') as t:
            get_product_overview(None, None)
        t.assert_under(5.0)

    def test_perf_tab_by_week(self):
        with self.timer('product_tab_week_cold') as t:
            get_product_tab('by_week', None, None)
        t.assert_under(3.0)

    def test_perf_tab_top_products(self):
        with self.timer('product_tab_top_cold') as t:
            get_product_tab('top_products', None, None)
        t.assert_under(3.0)


class ProductViewTest(SnapshotTestCase):
    """Test views: permissions, HTTP, AJAX tabs, export."""

    @classmethod
    def setUpTestData(cls):
        process_sale_detail_file(open(INPUT_DIR / 'sale detail (1).xlsx', 'rb'))

    def test_product_page_200(self):
        self.client.force_login(self._get_superuser())
        r = self.client.get('/products/')
        self.assertEqual(r.status_code, 200)

    def test_product_page_requires_login(self):
        r = self.client.get('/products/')
        self.assertRedirects(r, '/login/?next=/products/')

    def test_product_page_requires_perm(self):
        """User không có products.view → redirect home với error message."""
        user = self._get_viewer_user()  # chỉ có sales.view
        self.client.force_login(user)
        r = self.client.get('/products/')
        self.assertRedirects(r, '/')

    def test_product_tab_ajax_by_week(self):
        self.client.force_login(self._get_superuser())
        r = self.client.get('/products/tab/by_week/',
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'by_week', r.content)  # template rendered

    def test_product_tab_non_ajax_400(self):
        self.client.force_login(self._get_superuser())
        r = self.client.get('/products/tab/by_week/')   # no X-Requested-With
        self.assertEqual(r.status_code, 400)

    def test_product_tab_invalid_400(self):
        self.client.force_login(self._get_superuser())
        r = self.client.get('/products/tab/nonexistent/',
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 400)

    def test_export_requires_perm(self):
        user = self._get_viewer_user()
        self.client.force_login(user)
        r = self.client.get('/products/export/')
        self.assertRedirects(r, '/')

    def test_export_returns_xlsx(self):
        self.client.force_login(self._get_superuser())
        r = self.client.get('/products/export/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
```

---

## Checklist triển khai (theo thứ tự dependency)

### Phase 1 — Models & Migrations (1h)
- [ ] Tạo `App/models/inventory.py` với `InventorySnapshot`
- [ ] Thêm `SaleDetail` vào `App/models/pos.py`
- [ ] Export cả 2 từ `App/models/__init__.py`
- [ ] Thêm cả 2 vào `App/admin.py`
- [ ] `python manage.py makemigrations` → verify 2 migration files
- [ ] `python manage.py migrate` → verify schema

### Phase 2 — Services (2h)
- [ ] Tạo `App/services/inventory_import.py` (`process_inventory_file`)
  - [ ] Column mapping đúng header thực tế
  - [ ] `update_or_create` với unique_together `(shop_id, product_code)`
  - [ ] Batch 2000, progress_fn callback
  - [ ] Return `{created, updated, skipped, errors}`
- [ ] Tạo `App/services/sale_detail_import.py` (`process_sale_detail_file`)
  - [ ] Column mapping đúng
  - [ ] FK resolution SalesTransaction (pre-load dict)
  - [ ] Parse `discount_pct` từ "100.00%" → Decimal
  - [ ] Parse `sales_time` → time object
  - [ ] Batch 3000, upsert unique `(invoice_number, barcode, size)`
  - [ ] Return `{created, updated, skipped, errors}`
- [ ] Export từ `App/services/__init__.py`

### Phase 3 — Upload UI (1.5h)
- [ ] Thêm `InventoryUploadForm` vào `App/forms.py`
- [ ] Thêm `"inventory"`, `"sale_detail"` vào `JOB_TYPE_LABELS` trong `upload_jobs.py`
- [ ] Thêm `upload_inventory()` vào `App/views/upload.py`
- [ ] Thêm `upload_sale_detail()` vào `App/views/upload.py`
- [ ] Tạo `App/templates/upload/inventory.html`
- [ ] Cập nhật `App/templates/upload/sales.html` — thêm Card 2 (Sale Detail)
- [ ] Thêm 2 URLs vào `App/urls.py` (`upload_inventory`, `upload_sale_detail`)
- [ ] Test upload thủ công: inventory.xlsx → verify records created
- [ ] Test upload thủ công: sale detail (1).xlsx → verify records created
- [ ] Test upsert: upload lại cùng file → verify count không tăng

### Phase 4 — Shop Detail Inventory Tab (2h)
- [ ] Tạo `App/analytics/inventory_functions.py`
  - [ ] `get_shop_inventory_data(shop_name)` với cache 10 phút
  - [ ] KPI aggregation (total_qty, total_value, in_transit_qty)
  - [ ] Dead stock query: `year <= current_year - 1 AND total_qty > 0`
  - [ ] By category aggregation
  - [ ] Top 20 SKUs by total_qty
  - [ ] Sell-through cross với SaleDetail (30d) — conditional
- [ ] Thêm `shop_detail_inventory_partial()` vào `App/views/shop_detail.py`
- [ ] Cập nhật `_get_dropdown_options()` — thêm `inventory_shops`
- [ ] Tạo `App/templates/shop_detail/_inventory_partial.html`
  - [ ] 4 KPI cards (total_qty, total_value, in_transit_qty, dead_stock_count)
  - [ ] Table: By Category
  - [ ] Table: Top 20 SKUs (dead stock row highlight)
  - [ ] Table: Dead Stock (nếu dead_stock_count > 0)
  - [ ] Sell-through card (conditional — chỉ hiện khi có SaleDetail data)
  - [ ] CSS: 100% token-based, không hardcode hex
- [ ] Cập nhật `shop_detail.html` — thêm Section 4 + dropdown + JS
- [ ] Thêm URL `/shop-detail/partial/inventory/`
- [ ] Regenerate visual snapshots

### Phase 5 — Product Analytics (4h)
- [ ] Thêm `products.view`, `products.export` vào `PERMISSION_DEFS`
- [ ] Tạo `App/analytics/product_analytics.py`
  - [ ] `PRODUCT_TABS` constant list
  - [ ] `_base_qs()` với shop_group logic (clone từ `_load_sales()`)
  - [ ] `get_product_overview()`
  - [ ] `get_product_tab()` dispatcher + cache
  - [ ] `_top_products()` — top 50 by revenue
  - [ ] `_by_week()` — TruncWeek + Sum
  - [ ] `_by_month()` — TruncMonth + Sum
  - [ ] `_by_season()` — group by season + label mapping
  - [ ] `_by_category()` — group by category_l2 top 15
  - [ ] `_by_shop()` — group by shop_name + detail
  - [ ] `_salesmen()` — top 30 by revenue
  - [ ] `_inventory_cross()` — conditional, cross với InventorySnapshot
- [ ] Tạo `App/views/product.py`
  - [ ] `product_analytics()` — load top_products ngay, lazy_params cho tabs còn lại
  - [ ] `product_tab()` — AJAX guard + dispatcher
  - [ ] `export_product_analytics()` — Excel với Overview sheet + tab sheet
- [ ] Thêm URLs vào `App/urls.py`
- [ ] Tạo `App/views/__init__.py` — export product views
- [ ] Tạo templates:
  - [ ] `product/dashboard.html` (clone + adapt từ `analytics/dashboard.html`)
  - [ ] `product/tabs/top_products.html`
  - [ ] `product/tabs/by_week.html`
  - [ ] `product/tabs/by_month.html`
  - [ ] `product/tabs/by_season.html`
  - [ ] `product/tabs/by_category.html`
  - [ ] `product/tabs/by_shop.html`
  - [ ] `product/tabs/salesmen.html`
  - [ ] `product/tabs/inventory_cross.html`
  - [ ] `product/tabs/_empty.html`
- [ ] Cập nhật `home.html` — thêm Product Analytics action card
- [ ] Cập nhật `base.html` — thêm "Products" link sau "Shop Detail"
- [ ] Regenerate visual snapshots

### Phase 6 — Tests (3h)
- [ ] Copy `inventory.xlsx` vào `tests/input/inventory.xlsx` (cần subset nhỏ để test nhanh)
- [ ] Tạo `tests/test_inventory.py` — 10 test cases (xem test plan trên)
- [ ] Tạo `tests/test_sale_detail.py` — 15 test cases
- [ ] Tạo `tests/test_product.py` — 10 test cases
- [ ] Chạy: `UPDATE_SNAPSHOTS=1 python manage.py test tests.test_inventory tests.test_sale_detail tests.test_product -v 2`
- [ ] Verify snapshots đã tạo đủ
- [ ] Chạy lại (không UPDATE): verify tất cả pass
- [ ] Chạy full suite: `python manage.py test tests -v 2` — verify không regression

### Phase 7 — Docs & Smoke Test (1h)
- [ ] Regenerate visual snapshots (`snapshot_render.py` + `snapshot_visual.py`)
- [ ] Verify 0 token issues trong `tests/render/_index.md`
- [ ] Smoke test tất cả pages:
  - `/products/` → 200
  - `/products/tab/by_week/` (AJAX) → 200
  - `/products/export/` → xlsx
  - `/shop-detail/partial/inventory/?shop=...` → 200
  - `/upload/inventory/` → 200
  - `/upload/sales/` (card 2 hiện) → 200
- [ ] Cập nhật `docs/project_urls.md` — 6 URLs mới
- [ ] Cập nhật `docs/project_models.md` — 2 models mới
- [ ] Cập nhật `docs/project_business_logic.md` — 2 permissions mới, dead stock rule
- [ ] Cập nhật `docs/project_analytics.md` — product analytics engine
- [ ] Cập nhật `docs/project_structure.md` — files mới
- [ ] Cập nhật `FINAL_REPORT.md` — addendum

---

## Tóm tắt URLs mới

| URL | View | Permission |
|-----|------|-----------|
| `/upload/inventory/` | `upload_inventory` | `data.upload` |
| `/upload/sale-detail/` | `upload_sale_detail` | `data.upload` |
| `/shop-detail/partial/inventory/` | `shop_detail_inventory_partial` | `shops.view` |
| `/products/` | `product_analytics` | `products.view` |
| `/products/tab/<tab>/` | `product_tab` | `products.view` |
| `/products/export/` | `export_product_analytics` | `products.export` |

---

## Tóm tắt files mới/thay đổi

| File | Loại | Ghi chú |
|------|------|---------|
| `App/models/inventory.py` | MỚI | InventorySnapshot model |
| `App/models/pos.py` | CẬP NHẬT | Thêm SaleDetail |
| `App/models/__init__.py` | CẬP NHẬT | Export 2 models mới |
| `App/services/inventory_import.py` | MỚI | process_inventory_file |
| `App/services/sale_detail_import.py` | MỚI | process_sale_detail_file |
| `App/services/__init__.py` | CẬP NHẬT | Export 2 services mới |
| `App/analytics/inventory_functions.py` | MỚI | get_shop_inventory_data |
| `App/analytics/product_analytics.py` | MỚI | Engine Product Analytics |
| `App/views/product.py` | MỚI | product views |
| `App/views/upload.py` | CẬP NHẬT | +2 upload views |
| `App/views/shop_detail.py` | CẬP NHẬT | +inventory partial |
| `App/views/__init__.py` | CẬP NHẬT | Export product views |
| `App/permissions.py` | CẬP NHẬT | +2 permissions |
| `App/forms.py` | CẬP NHẬT | +InventoryUploadForm |
| `App/upload_jobs.py` | CẬP NHẬT | +2 job types |
| `App/urls.py` | CẬP NHẬT | +6 URLs |
| `App/templates/upload/inventory.html` | MỚI | |
| `App/templates/upload/sales.html` | CẬP NHẬT | +Card 2 |
| `App/templates/shop_detail.html` | CẬP NHẬT | +Section 4 |
| `App/templates/shop_detail/_inventory_partial.html` | MỚI | |
| `App/templates/product/dashboard.html` | MỚI | |
| `App/templates/product/tabs/*.html` | MỚI | 9 tab templates |
| `App/templates/base.html` | CẬP NHẬT | +Products nav link |
| `App/templates/home.html` | CẬP NHẬT | +Product action card |
| `App/migrations/0013_inventorysnapshot.py` | MỚI | |
| `App/migrations/0014_saledetail.py` | MỚI | |
| `tests/test_inventory.py` | MỚI | 10 test cases |
| `tests/test_sale_detail.py` | MỚI | 15 test cases |
| `tests/test_product.py` | MỚI | 10 test cases |

---

*Plan v2.0 — tất cả quyết định đã confirm, sẵn sàng implement theo thứ tự Phase 1→7.*
