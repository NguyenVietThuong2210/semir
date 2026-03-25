# 📘 SEMIR DASHBOARD - COMPLETE PROJECT DOCUMENTATION

**Last Updated:** 2026-03-23
**Purpose:** Chi tiết toàn bộ project để dễ dàng handover/recovery trong session khác

---

## 📋 TABLE OF CONTENTS

1. [Project Overview](#project-overview)
2. [Database Models](#database-models)
3. [Features & Functionality](#features--functionality)
4. [Analytics System](#analytics-system)
5. [CNV Integration](#cnv-integration)
6. [File Structure](#file-structure)
7. [URL Routing](#url-routing)
8. [Excel Export System](#excel-export-system)
9. [Recent Updates](#recent-updates)
10. [Deployment Guide](#deployment-guide)

---

## 🎯 PROJECT OVERVIEW

### **Tên Project:** SemirDashboard
### **Framework:** Django 6.0.2
### **Database:** SQLite3
### **Purpose:** Retail analytics dashboard with CNV Loyalty integration

### **Core Functions:**
1. **POS Data Management** - Upload & analyze customer, sales data
2. **Analytics Dashboard** - Sales analysis by VIP grade, season, shop
3. **Coupon Dashboard** - Coupon usage tracking & analytics
4. **CNV Integration** - Sync with CNV Loyalty API
5. **Customer Comparison** - Compare POS vs CNV customer data
6. **Excel Export** - Export analytics to Excel with formatted reports

---

## 🗄️ DATABASE MODELS

### **1. POS Models (App/models/pos.py)**

#### **Customer**
```python
class Customer(models.Model):
    vip_id              # VIP ID (can be 0 for non-VIP)
    id_number           # ID card number
    birthday_month      # Birth month
    vip_grade           # VIP0/VIP1/VIP2/VIP3/DIAMOND
    name                # Full name
    phone               # Phone number (indexed)
    race                # Race/ethnicity
    gender              # Gender
    birthday            # Full birthday
    city_state          # City/State
    postal_code         # Postal code
    country             # Country
    email               # Email
    contact_address     # Address
    registration_store  # Store where registered
    registration_date   # Registration date (indexed)
    points              # Current points
    created_at          # Record created
    updated_at          # Record updated
    
    # Indexes:
    - (vip_id, phone) - unique together
    - registration_date
```

**Business Logic:**
- VIP ID = 0 → Non-VIP customers (excluded from most analytics)
- VIP Grades: VIP0, VIP1, VIP2, VIP3, DIAMOND
- Phone is primary identifier for matching with CNV

#### **SalesTransaction**
```python
class SalesTransaction(models.Model):
    invoice_number          # Unique invoice (indexed)
    shop_id                 # Shop ID
    shop_name               # Shop name
    country                 # Country
    bu                      # Business unit
    sales_date              # Sale date (indexed)
    vip_id                  # Customer VIP ID (indexed)
    vip_name                # Customer name
    quantity                # Items quantity
    settlement_amount       # Settlement amount
    sales_amount            # Sales amount
    tag_amount              # Tag amount
    per_customer_transaction # Per customer transaction
    discount                # Discount amount
    rounding                # Rounding amount
    customer                # FK to Customer (nullable)
    created_at              # Record created
    
    # Indexes:
    - (vip_id, sales_date)
    - sales_date
```

**Business Logic:**
- Links to Customer via vip_id
- Used for sales analytics by grade, shop, season
- Can have customer FK null if customer not found

#### **Coupon**
```python
class Coupon(models.Model):
    department          # Department
    creator             # Creator
    document_number     # Document number
    coupon_id           # Coupon ID (indexed)
    face_value          # Face value amount
    used                # 0=unused, 1=used
    begin_date          # Valid from
    end_date            # Valid until
    using_shop          # Shop where used
    using_date          # Date used (indexed)
    push                # Push status
    member_id           # Member ID
    member_name         # Member name
    member_phone        # Member phone
    docket_number       # Docket number (indexed)
    created_at          # Record created
    updated_at          # Record updated
    
    # Indexes:
    - coupon_id
    - docket_number
    - using_date
    - used
```

**Business Logic:**
- Used = 0 → Unused coupons
- Used = 1 → Used coupons
- Coupon analytics by shop group, season

---

### **2. CNV Models (App/cnv/models.py)** (restructured Feb 27, 2026)

#### **CNVCustomer** ⭐ RECENTLY UPDATED
```python
class CNVCustomer(models.Model):
    # Database IDs
    id                  # AutoField (internal DB primary key: 1, 2, 3...)
    cnv_id              # BigIntegerField (CNV customer ID: 35577245, unique, indexed)
    
    # Basic Info
    last_name           # Last name
    first_name          # First name
    phone               # Phone number (indexed)
    email               # Email
    gender              # Gender (female/male)
    
    # Birthday (split fields)
    birthday_day        # Day (1-31)
    birthday_month      # Month (1-12)
    birthday_year       # Year (YYYY)
    
    # Additional Info
    tags                # Tags (text)
    physical_card_code  # Physical card code
    
    # Points (from customer endpoint)
    points              # Current points balance
    exp_points          # Expiring points
    total_spending      # Total spending amount
    total_points        # Total points earned historically
    
    # Membership (from membership endpoint)
    level_name          # Membership level (Diamond, Gold, etc.) - indexed
    used_points         # Points used/spent
    
    # CNV Timestamps
    cnv_created_at      # Created in CNV (indexed)
    cnv_updated_at      # Updated in CNV (indexed)
    
    # Internal Tracking
    created_at          # Record created in DB
    updated_at          # Record updated in DB
    last_synced_at      # Last sync time (indexed)
    
    # Properties:
    @property
    def full_name(self):
        """Returns: 'last_name first_name'"""
        
    @property
    def registration_date(self):
        """Alias for cnv_created_at"""
    
    # Indexes:
    - cnv_id (unique)
    - phone
    - level_name
    - last_synced_at (desc)
    - cnv_updated_at (desc)
```

**IMPORTANT CHANGES (Feb 27, 2026):**
- Primary key changed: `customer_code` → `id` (AutoField)
- Added: `cnv_id` (BigIntegerField, unique) - stores CNV customer ID
- Split name: `full_name` → `last_name` + `first_name` + property
- Split birthday: `birthday` → `birthday_day/month/year`
- Renamed: `membership_level` → `level_name`
- Renamed: `total_points_earned` → `total_points`
- Renamed: `total_points_spent` → `used_points`
- Renamed dates: `created_at` → `cnv_created_at`, `updated_at` → `cnv_updated_at`

**API Integration:**
- Syncs from 2 CNV API endpoints:
  1. `/loyalty/customers.json` - Base customer data
  2. `/loyalty/customers/{id}/membership.json` - Membership & level data

#### **CNVOrder**
```python
class CNVOrder(models.Model):
    order_code          # Primary key (from CNV)
    order_id            # Order ID (indexed)
    customer_code       # Customer code (indexed)
    customer_name       # Customer name
    customer_phone      # Customer phone
    order_date          # Order date (indexed)
    order_status        # Order status
    payment_status      # Payment status
    payment_method      # Payment method
    store_code          # Store code (indexed)
    store_name          # Store name
    subtotal            # Subtotal amount
    discount_amount     # Discount amount
    tax_amount          # Tax amount
    shipping_fee        # Shipping fee
    total_amount        # Total amount
    points_earned       # Points earned
    points_used         # Points used
    items               # JSON: Line items
    notes               # Notes
    raw_data            # JSON: Raw API response
    created_at          # Record created
    updated_at          # Record updated
    last_synced_at      # Last sync time
    
    # Indexes:
    - order_date (desc)
    - (customer_code, order_date desc)
    - (store_code, order_date desc)
```

#### **CNVSyncLog**
```python
class CNVSyncLog(models.Model):
    sync_type               # 'customers' / 'orders' / 'full'
    status                  # 'running' / 'completed' / 'failed'
    started_at              # Sync start time
    completed_at            # Sync completion time
    checkpoint_updated_at   # Latest updated_at from records (for incremental sync)
    total_records           # Total records processed
    created_count           # New records created
    updated_count           # Records updated
    failed_count            # Failed records
    error_message           # Error message (if failed)
    error_details           # JSON: Error details
    
    # Indexes:
    - (sync_type, status)
    - started_at (desc)
    - (sync_type, checkpoint_updated_at desc)
```

---

## 🎨 FEATURES & FUNCTIONALITY

### **1. Authentication System**
**Files:** `App/views/auth.py`
**URLs:** `/login/`, `/logout/`, `/register/`

**Features:**
- User registration
- Login/logout
- Password validation
- Session management

---

### **2. Home Dashboard**
**File:** `App/views/home.py::home()`
**URL:** `/`
**Template:** `home.html`

**Features:**
- Quick stats overview
- Recent uploads summary
- Navigation to main features

---

### **3. Data Upload System**
**Files:** `App/views/upload.py`
**URLs:** 
- `/upload/customers/` - Upload customer CSV
- `/upload/sales/` - Upload sales CSV
- `/upload/coupons/` - Upload coupon Excel

**Features:**
- CSV/Excel file upload
- Data validation
- Bulk import
- Duplicate detection
- Error reporting

**Upload Formats:**
- Customers: CSV with columns (vip_id, name, phone, etc.)
- Sales: CSV with columns (invoice_number, shop_id, sales_date, etc.)
- Coupons: Excel with specific sheet format

---

### **4. Analytics Dashboard** ⭐
**File:** `App/views/analytics.py::analytics_dashboard()`
**URL:** `/analytics/`
**Template:** `analytics_dashboard.html`

**Features:**
- Sales analytics by date range
- Breakdown by:
  - VIP Grade (VIP0/VIP1/VIP2/VIP3/DIAMOND)
  - Season (SS/AW)
  - Shop Group (by first 2 chars of shop_id)
- Metrics:
  - Total Sales Amount
  - Total Invoices
  - Total Customers
  - Customer Conversion Rate
  - Average per Customer
  - Average per Invoice
- Sub-tables showing detailed breakdowns
- Excel export functionality

**Analytics Module:** `App/analytics/`
- `core.py` - Core analytics engine
- `aggregators.py` - Data aggregation logic (~40KB)
- `calculations.py` - Return visit formula (LOCKED)
- `season_utils.py` - Season detection (M2-4, M5-7, M8-10, M11-1)
- `customer_utils.py` - Customer cache + purchase map
- `coupon_analytics.py` - Coupon analytics (~37KB)
- `excel_export.py` - Excel export formatting (~85KB, 13+ sheets)

---

### **5. Coupon Dashboard**
**File:** `App/views/coupon.py::coupon_dashboard()`
**URL:** `/coupons/`
**Template:** `coupon_dashboard.html`

**Features:**
- Coupon analytics by date range
- Breakdown by:
  - VIP Grade
  - Season
  - Shop Group
- Metrics:
  - Total Issued
  - Total Used
  - Usage Rate
  - Total Face Value
  - Used Value
- Shop group filter
- Excel export

---

### **6. Customer Detail Search**
**File:** `App/views/customer.py::customer_detail()`
**URL:** `/customer-detail/`
**Template:** `customer_detail.html`

**Features:**
- Search by VIP ID or Phone
- Display customer info
- Show transaction history
- Check if synced to CNV
- Points balance

---

### **7. CNV Integration** ⭐

#### **CNV Sync Service**
**File:** `App/cnv/sync_service.py`
**Class:** `CNVSyncService`

**Features:**
- OAuth2 authentication with CNV API
- Incremental sync (checkpoint-based)
- Bulk operations for performance
- Error tracking & logging
- Fetches both customer and membership data

**Methods:**
```python
_transform_customer(data)       # Transform API response to DB format
_fetch_membership(customer_id)  # Fetch membership data from API
_process_customer_batch(batch)  # Bulk create/update customers
sync_customers()                # Main sync method
```

#### **CNV API Client**
**File:** `App/cnv/api_client.py`
**Class:** `CNVAPIClient`

**Features:**
- OAuth2 authorization code flow
- Token caching (30 days)
- Automatic pagination
- Rate limiting handling

**Methods:**
```python
authenticate()                      # Get access token
get_customers(page, page_size)      # Fetch customers page
get_customer_membership(id)         # Fetch membership data ⭐ NEW
get_orders(page, page_size)         # Fetch orders page
fetch_all_customers(updated_since)  # Fetch all with pagination
```

**API Endpoints Used:**
- `https://apis.cnvloyalty.com/loyalty/customers.json`
- `https://apis.cnvloyalty.com/loyalty/customers/{id}/membership.json` ⭐
- `https://apis.cnvloyalty.com/loyalty/orders.json`

#### **CNV Views**
**File:** `App/cnv/views.py`
**URLs:** `/cnv/...`

**Functions:**
- `sync_status()` - Sync dashboard
- `customer_comparison()` - POS vs CNV comparison ⭐
- `export_customer_comparison()` - Export comparison to Excel ⭐

#### **Customer Comparison Page** ⭐ RECENTLY UPDATED
**URL:** `/cnv/customer-comparison/`
**Template:** `cnv/customer_comparison.html`

**Features:**
- Compare POS vs CNV customers by phone number
- 4 data tables:
  1. **POS Only - All Time** (7 columns)
     - VIP ID, Phone, Name, Grade, Email, Reg Date, Points
  2. **CNV Only - All Time** (8 columns) ⭐
     - Customer ID, Phone, Name, **Level**, Email, Reg Date, Points, Used Points
  3. **POS Only - Period** (7 columns)
  4. **CNV Only - Period** (8 columns) ⭐
- Date filtering
- Phone-based matching
- Statistics:
  - Total POS customers
  - Total CNV customers
  - POS-only count
  - CNV-only count
  - New in period
- Excel export

**IMPORTANT:** 
- POS table uses `registration_date`
- CNV table uses `cnv_created_at`
- CNV table includes `level_name` column (membership level)

#### **CNV Scheduler**
**File:** `App/cnv/scheduler.py`

**Features:**
- Scheduled sync tasks
- Configurable intervals
- Background job management

#### **Management Command**
**File:** `App/management/commands/sync_cnv.py`
**Usage:** `python manage.py sync_cnv [--full]`

**Options:**
- `--full` - Full sync (all customers)
- Default - Incremental sync (updated since last checkpoint)

---

## 📊 ANALYTICS SYSTEM

### **Analytics Engine Architecture**

```
App/analytics/
├── core.py              # Main AnalyticsEngine class
├── aggregators.py       # Data aggregation (group by grade/season/shop)
├── calculations.py      # Metric calculations
├── season_utils.py      # Season detection (SS/AW)
├── customer_utils.py    # Customer analytics
└── excel_export.py      # Excel export with formatting
```

### **Core Analytics Flow**

```python
# 1. User selects date range in UI
# 2. View calls AnalyticsEngine
engine = AnalyticsEngine(date_from, date_to)

# 3. Get base data
sales_data = engine.get_sales_data()
customer_data = engine.get_customer_data()

# 4. Aggregate by dimensions
by_grade = aggregate_by_vip_grade(sales_data)
by_season = aggregate_by_season(sales_data)
by_shop = aggregate_by_shop_group(sales_data)

# 5. Calculate metrics
totals = calculate_totals(sales_data)
conversion = calculate_conversion_rate(...)

# 6. Return to template or export
```

### **Season Logic** (App/analytics/season_utils.py)
```
M2-4:  February, March, April
M5-7:  May, June, July
M8-10: August, September, October
M11-1: November, December, January  ← cross-year
```
**NOTE:** Old SS/AW definition is OBSOLETE as of Mar 2026.

### **VIP Grade Hierarchy**
```
VIP0 (lowest)
VIP1
VIP2
VIP3
DIAMOND (highest)
```

### **Shop Grouping**
- Shop ID: "HN01", "HN02", "SG01", "SG02", etc.
- Shop Group: First 2 characters ("HN", "SG", etc.)

---

## 📁 FILE STRUCTURE (Updated 2026-03-23)

```
SemirDashboard/
├── App/
│   ├── models/                # ⭐ Split package (NOT models.py)
│   │   ├── __init__.py        # Exports all models
│   │   ├── pos.py             # Customer, SalesTransaction
│   │   ├── coupon.py          # Coupon, CouponCampaign
│   │   └── user.py            # Role, UserProfile
│   │
│   ├── views/                 # ⭐ Split package (NOT views.py)
│   │   ├── __init__.py        # Re-exports all views
│   │   ├── home.py            # home(), formulas_page()
│   │   ├── auth.py            # login/logout/register
│   │   ├── upload.py          # upload_*, upload_jobs_list/status
│   │   ├── analytics.py       # analytics_dashboard/chart/export
│   │   ├── coupon.py          # coupon_dashboard/chart/export, manage_campaigns
│   │   ├── customer.py        # customer_detail()
│   │   └── users.py           # user_management()
│   │
│   ├── analytics/             # Analytics engine
│   │   ├── __init__.py
│   │   ├── core.py            # calculate_return_rate_analytics()
│   │   ├── aggregators.py     # Data aggregation (~40KB)
│   │   ├── calculations.py    # Return visit formula (LOCKED)
│   │   ├── season_utils.py    # M2-4, M5-7, M8-10, M11-1
│   │   ├── customer_utils.py  # Customer cache + purchase map
│   │   ├── coupon_analytics.py # Coupon analytics (~37KB)
│   │   └── excel_export.py    # Excel export ~85KB, 13+ sheets
│   │
│   ├── cnv/                   # CNV integration
│   │   ├── __init__.py
│   │   ├── models.py          # ⭐ CNVCustomer, CNVOrder, CNVSyncLog
│   │   ├── api_client.py      # CNVAPIClient (OAuth2, pagination)
│   │   ├── sync_service.py    # CNVSyncService (incremental)
│   │   ├── scheduler.py       # APScheduler background tasks
│   │   ├── views.py           # CNV views
│   │   ├── urls.py            # /cnv/... routes
│   │   └── zalo_sync.py       # Zalo integration
│   │
│   ├── services/              # Import/processing services
│   │   ├── file_reader.py     # CSV/Excel parsing
│   │   ├── customer_import.py
│   │   ├── sales_import.py
│   │   └── coupon_import.py
│   │
│   ├── management/
│   │   └── commands/
│   │       ├── sync_cnv.py    # manage.py sync_cnv [--full]
│   │       └── perm.py        # Permission management
│   │
│   ├── migrations/            # 0001 through 0010
│   │
│   ├── templates/
│   │   ├── base.html, home.html, login.html, register.html, formulas.html
│   │   ├── upload_customers.html, upload_sales.html, upload_coupons.html
│   │   ├── analytics_dashboard.html, coupon_dashboard.html, customer_detail.html
│   │   └── cnv/sync_status.html, cnv/customer_comparison.html
│   │
│   ├── templatetags/
│   │   ├── custom_filters.py
│   │   └── perm_tags.py       # Permission checking tags
│   │
│   ├── forms.py               # CustomerUploadForm, SalesUploadForm, UsedPointsUploadForm
│   ├── urls.py                # App URL routing
│   ├── admin.py
│   ├── apps.py
│   ├── permissions.py         # Custom role-based permissions
│   └── upload_jobs.py         # Background job queue
│
├── SemirDashboard/
│   ├── settings.py            # Django settings
│   ├── urls.py                # Root URLs: /admin/, /, /cnv/
│   └── wsgi.py
│
├── db.sqlite3
├── manage.py
└── requirements.txt
```

### ⚠️ OBSOLETE PATHS
| Old (wrong) | New (correct) |
|-------------|---------------|
| `App/models.py` | `App/models/pos.py` + `coupon.py` + `user.py` |
| `App/models_cnv.py` | `App/cnv/models.py` |
| `App/views.py` | `App/views/*.py` |
| `App/auth_views.py` | `App/views/auth.py` |
| `App/utils.py` | `App/services/` |
| `App/analytics.py` | `App/analytics/` package |

---

## 🔗 URL ROUTING

### **Main URLs (SemirDashboard/urls.py)**
```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('App.urls')),
    path('cnv/', include('App.cnv.urls')),
]
```

### **App URLs (App/urls.py)**
```
/                           → home
/formulas/                  → formulas_page
/login/                     → login_view
/logout/                    → logout_view
/register/                  → register_view
/upload/customers/          → upload_customers
/upload/sales/              → upload_sales
/upload/coupons/            → upload_coupons
/upload/used-points/        → upload_used_points
/upload/jobs/               → upload_jobs_list
/upload/jobs/<job_id>/      → upload_job_status (AJAX)
/analytics/                 → analytics_dashboard
/analytics/export/          → export_analytics
/analytics/chart/           → analytics_chart (AJAX)
/coupons/                   → coupon_dashboard
/coupons/export/            → export_coupons
/coupons/chart/             → coupon_chart (AJAX)
/coupons/campaigns/         → manage_campaigns
/customer-detail/           → customer_detail
/users/                     → user_management
```

### **CNV URLs (App/cnv/urls.py)**
```
/cnv/sync-status/                   → sync_status
/cnv/customer-analytics/            → customer_analytics
/cnv/export-customer-analytics/     → export_customer_analytics
/cnv/sync-cnv-points/               → sync_cnv_points (AJAX POST)
/cnv/trigger-sync/                  → trigger_sync (AJAX POST)
/cnv/trigger-zalo-sync/             → trigger_zalo_sync (AJAX POST)
```

---

## 📤 EXCEL EXPORT SYSTEM

**File:** `App/analytics/excel_export.py`

### **Export Functions:**

#### **1. export_analytics_to_excel()** ⭐
**Used by:** Analytics Dashboard
**Sheets:**
- Overview - Summary metrics
- By VIP Grade - Breakdown by grade
- By Season - Breakdown by season
- By Shop Group - Breakdown by shop

**Features:**
- Formatted headers (blue background, white text)
- Number formatting (VND currency)
- Auto-column width
- Filter info display
- Calculation formulas preserved

#### **2. export_coupons_to_excel()** ⭐
**Used by:** Coupon Dashboard
**Sheets:**
- Overview - Summary metrics
- By VIP Grade - Breakdown by grade
- By Season - Breakdown by season
- By Shop Group - Breakdown by shop

**Features:**
- Similar formatting to analytics export
- Coupon-specific metrics (issued, used, usage rate)

#### **3. export_customer_comparison_to_excel()** ⭐ RECENTLY UPDATED
**Used by:** Customer Comparison
**Sheets:**
- Overview - Comparison summary
- POS Only - All Time (7 columns)
- CNV Only - All Time (8 columns) ⭐
- POS Only - Period (7 columns) - if date filtered
- CNV Only - Period (8 columns) ⭐ - if date filtered

**CNV Columns (8 total):**
1. Customer ID (cnv_id)
2. Phone
3. Name (last_name + first_name)
4. **Level** (level_name) ⭐ NEW
5. Email
6. Registration Date (cnv_created_at)
7. Points (total_points)
8. Used Points (used_points)

**Features:**
- Phone-based comparison
- Period filtering support
- Formatted headers
- Number formatting

---

## 🔄 RECENT UPDATES (Feb 27, 2026)

### **1. CNVCustomer Model Restructure** ⭐⭐⭐

**Changes:**
- Primary key: `customer_code` → `id` (AutoField) + `cnv_id` (BigIntegerField, unique)
- Name split: `full_name` → `last_name` + `first_name` + property
- Birthday split: `birthday` → `birthday_day/month/year`
- Field renames:
  - `membership_level` → `level_name`
  - `total_points_earned` → `total_points`
  - `total_points_spent` → `used_points`
  - `created_at` → `cnv_created_at`
  - `updated_at` → `cnv_updated_at`

**Reason:** Match actual CNV API response format

**Migration:** Custom migration `0005_recreate_cnvcustomer.py` (drops & recreates table)

### **2. Membership API Integration** ⭐⭐

**Added:**
- `CNVAPIClient.get_customer_membership()` method
- Fetches membership data from `/loyalty/customers/{id}/membership.json`
- Returns level_name, used_points, etc.

**Sync Flow:**
```python
# For each customer:
1. Fetch from /loyalty/customers.json
2. Fetch from /loyalty/customers/{id}/membership.json
3. Merge data
4. Save to database
```

### **3. Customer Comparison Page** ⭐⭐

**Updates:**
- CNV table: 7 → 8 columns (added Level column)
- POS table: 7 columns (unchanged)
- Column widths optimized
- CSS fixed table layout
- Level badge display
- Excel export updated

**CSS Column Widths:**
```css
/* POS Table (7 columns) */
VIP ID: 10%, Phone: 15%, Name: 15%, Grade: 15%,
Email: 15%, Reg Date: 15%, Points: 15%

/* CNV Table (8 columns) */
Customer ID: 10%, Phone: 15%, Name: 15%, Level: 15%,
Email: 15%, Reg Date: 15%, Points: 7.5%, Used Points: 7.5%
```

### **4. Files Updated:**
- ✅ `models_cnv.py` - New structure
- ✅ `sync_service.py` - Membership integration
- ✅ `api_client.py` - New method
- ✅ `cnv/views.py` - Field updates
- ✅ `customer_comparison.html` - 8 columns
- ✅ `excel_export.py` - CNV export function

---

## 🚀 DEPLOYMENT GUIDE

### **Environment Setup**
```bash
# Python 3.11+
pip install -r requirements.txt

# Database
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run server
python manage.py runserver
```

### **CNV Integration Setup**
1. Configure CNV credentials in settings or environment
2. Run initial sync: `python manage.py sync_cnv --full`
3. Schedule periodic syncs (using scheduler or cron)

### **Data Upload**
1. Navigate to respective upload pages
2. Upload CSV/Excel files
3. Review import summary
4. Check data in analytics dashboard

---

## 🔧 TROUBLESHOOTING

### **Common Issues:**

#### **1. Migration Error: "table has more than one primary key"**
**Solution:** Use custom migration `0005_recreate_cnvcustomer.py`
```bash
rm App/migrations/0005_*.py
cp 0005_recreate_cnvcustomer.py App/migrations/
python manage.py migrate App
```

#### **2. CNV API Error: "object has no attribute 'get'"**
**Solution:** Update `api_client.py` with `get_customer_membership()` method

#### **3. Sync Fails**
**Check:**
- CNV credentials valid
- Network connectivity
- API rate limits
- Check `CNVSyncLog` for error details

#### **4. Excel Export Fails**
**Check:**
- openpyxl installed
- Sufficient memory
- File permissions

---

## 📝 KEY BUSINESS LOGIC

### **VIP Grade Analysis**
- Exclude VIP ID = 0 (non-VIP)
- Calculate metrics per grade
- Compare across grades

### **Season Analysis**
- SS (Jan-Jun)
- AW (Jul-Dec)
- Based on sales_date month

### **Shop Group Analysis**
- Group by first 2 chars of shop_id
- Aggregate sales per group

### **Customer Matching (POS vs CNV)**
- Match by phone number
- Identify POS-only customers
- Identify CNV-only customers
- Track new registrations in period

### **Coupon Analytics**
- Track issued vs used
- Calculate usage rate
- Analyze by grade/season/shop

---

## 🎯 NEXT STEPS / TODO

### **Potential Enhancements:**
1. ⬜ Real-time dashboard updates
2. ⬜ Advanced filtering options
3. ⬜ Custom date range presets
4. ⬜ Export to PDF
5. ⬜ Email reports
6. ⬜ API endpoints for mobile app
7. ⬜ Multi-language support
8. ⬜ Role-based access control
9. ⬜ Advanced customer segmentation
10. ⬜ Predictive analytics

---

## 📞 CONTACT / SUPPORT

For questions about this documentation or the project:
- Review code comments in respective files
- Check Django admin for data inspection
- Review CNVSyncLog for sync issues
- Check Excel exports for data validation

---

## 📚 APPENDIX

### **A. CNV API Response Formats**

#### **Customer Endpoint Response:**
```json
{
  "customer": {
    "id": 35577245,
    "last_name": "Nguyễn Thị Thuỳ Linh",
    "first_name": ".",
    "phone": "0338336011",
    "email": "",
    "gender": "female",
    "birthday_day": 21,
    "birthday_month": 12,
    "birthday_year": 2020,
    "tags": "...",
    "physical_card_code": "",
    "points": 29649.0,
    "exp_points": 25849.0,
    "total_spending": 0.0,
    "total_points": 0.0,
    "created_at": "2025-06-23T08:51:26.859Z",
    "updated_at": "2026-02-05T17:34:44.533Z"
  }
}
```

#### **Membership Endpoint Response:**
```json
{
  "membership": {
    "level_name": "Diamond",
    "total_points": 29649.0,
    "points": 29649.0,
    "used_points": 0.0,
    "barcode_url": "...",
    "color_code": "#F844C7",
    "icon": {...}
  }
}
```

### **B. Database Field Mappings**

#### **POS Customer → CNV Customer Matching:**
```
POS.phone ←→ CNVCustomer.phone (matching field)
POS.vip_id ≠ CNVCustomer.cnv_id (different systems)
```

#### **CNV API → Database:**
```
API id → CNVCustomer.cnv_id
API created_at → CNVCustomer.cnv_created_at
API updated_at → CNVCustomer.cnv_updated_at
API last_name → CNVCustomer.last_name
API first_name → CNVCustomer.first_name
```

### **C. Important Constants**

```python
# Season boundaries (updated Mar 2026)
M2_4_MONTHS = [2, 3, 4]
M5_7_MONTHS = [5, 6, 7]
M8_10_MONTHS = [8, 9, 10]
M11_1_MONTHS = [11, 12, 1]  # cross-year: Nov-Dec (year N), Jan (year N+1)
# OLD (obsolete): SS = [1..6], AW = [7..12]

# VIP Grades (in order)
VIP_GRADES = ['VIP0', 'VIP1', 'VIP2', 'VIP3', 'DIAMOND']

# Coupon status
UNUSED = 0
USED = 1

# Sync types
SYNC_TYPE_CUSTOMERS = 'customers'
SYNC_TYPE_ORDERS = 'orders'
SYNC_TYPE_FULL = 'full'

# Sync status
STATUS_RUNNING = 'running'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
```

---

**END OF DOCUMENTATION**

**Document Version:** 1.1
**Last Updated:** 2026-03-23
**Author:** Claude (Anthropic)
**Status:** ✅ Updated — reflects post-refactor structure (views/, models/, cnv/, services/)