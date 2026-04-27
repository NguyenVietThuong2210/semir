# API Contract: SemirDashboard JSON API (Sprint 0 — Backend Deliverable)

**Status**: Required before mobile development. Backend team must implement this before any mobile data-fetching code is written.  
**Base URL (production)**: `https://analytics-customer-dashboard.com/api/v1`  
**Base URL (debug)**: `http://localhost:8000/api/v1`  
**Auth**: All endpoints except `/auth/token/` require `Authorization: Bearer <access_token>` header.  
**Content-Type**: `application/json` for all requests and responses.  
**Versioning**: URL prefix `/api/v1/`. Breaking changes → `/api/v2/`.

---

## Auth Endpoints

### POST /api/v1/auth/token/

Login. Returns JWT access + refresh tokens and the user's full permission set.

**Request body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response 200:**
```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "access_expires_in": 3600,
  "username": "string",
  "permissions": ["sales.view", "cnv.view", "coupons.view", "shop_detail.view", "customer_detail.view"]
}
```

**Response 401:**
```json
{ "detail": "No active account found with the given credentials" }
```

**Notes:**
- `access_expires_in` is in seconds. Mobile stores `now + access_expires_in` as the expiry timestamp.
- `permissions` contains only the permission strings the user has — omitted strings mean no access.
- Error message MUST be generic (FR-007 — no field-level disclosure).

---

### POST /api/v1/auth/token/refresh/

Silent token refresh. Called by the mobile HTTP interceptor on 401.

**Request body:**
```json
{ "refresh": "eyJ..." }
```

**Response 200:**
```json
{
  "access": "eyJ...",
  "access_expires_in": 3600
}
```

**Response 401:**
```json
{ "detail": "Token is invalid or expired" }
```

**Notes:**
- 401 here means the refresh token is expired/revoked → mobile must route to login.
- Refresh tokens MUST be single-use (rotate on each refresh) to prevent replay attacks.

---

### POST /api/v1/auth/logout/

Revoke the refresh token server-side. Called on Sign Out.

**Request body:**
```json
{ "refresh": "eyJ..." }
```

**Response 205:** (No content — reset content)

**Notes:**
- Even if the refresh token is already expired, return 205 (idempotent).
- The mobile app wipes local tokens regardless of the server response.

---

## Analytics Endpoints

All analytics endpoints accept the following common query parameters (where applicable):

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `date_from` | `YYYY-MM-DD` | No | Omit for all-time |
| `date_to` | `YYYY-MM-DD` | No | Omit for all-time |
| `shop_group` | `string` | No | One of: `"Bala Group"`, `"Semir Group"`, `"Others Group"` |

---

### GET /api/v1/analytics/sales/

**Permissions required**: `sales.view`  
**Query params**: `date_from`, `date_to`, `shop_group`

**Response 200:**
```json
{
  "all_time_kpis": {
    "total_invoices": 123456,
    "total_revenue": "1,234,567,890",
    "avg_invoice": "10,000",
    "total_customers": 45678
  },
  "period_kpis": {
    "total_invoices": 1234,
    "total_revenue": "12,345,678",
    "avg_invoice": "10,000",
    "returning_customers": 567,
    "return_rate": "45.98",
    "new_customers": 123,
    "avg_visits": "1.23",
    "new_no_invoice": 45
  },
  "tabs": {
    "by_season": {
      "headers": ["Season", "Invoices", "Revenue (VND)", "Customers", "Return Rate"],
      "rows": [
        ["M2-4 2025", "1,234", "12,345,678", "567", "45.98%"],
        ["M5-7 2025", "2,345", "23,456,789", "678", "50.12%"]
      ]
    },
    "by_month": { "headers": [...], "rows": [[...]] },
    "by_week":  { "headers": [...], "rows": [[...]] },
    "by_shop":  { "headers": [...], "rows": [[...]] },
    "by_grade": { "headers": [...], "rows": [[...]] }
  }
}
```

**Notes:**
- All numeric values in `all_time_kpis` and `period_kpis` are raw numbers (for comparison logic).
- All values in table `rows` are pre-formatted strings (VND with commas, % with 2 decimal places) — the mobile app renders them as-is without reformatting.
- `return_rate` is a percentage string (e.g. `"45.98"`) without the `%` sign in the KPI object; table cells include `%`.

---

### GET /api/v1/analytics/customer/

**Permissions required**: `cnv.view`  
**Query params**: `date_from`, `date_to`

**Response 200:**
```json
{
  "all_time_kpis": {
    "total_pos_customers": 45678,
    "total_cnv_customers": 34567,
    "pos_only": 11111,
    "cnv_only": 0
  },
  "period_kpis": {
    "new_pos_customers": 123,
    "new_cnv_customers": 89,
    "synced_this_period": 45,
    "active_customers": 234
  },
  "registration_breakdown": {
    "by_shop":  { "headers": [...], "rows": [[...]] },
    "by_month": { "headers": [...], "rows": [[...]] },
    "by_grade": { "headers": [...], "rows": [[...]] }
  },
  "customer_comparison": {
    "pos_only": { "headers": [...], "rows": [[...]] },
    "cnv_only": { "headers": [...], "rows": [[...]] },
    "both":     { "headers": [...], "rows": [[...]] }
  }
}
```

---

### GET /api/v1/analytics/coupon/

**Permissions required**: `coupons.view`  
**Query params**: `date_from`, `date_to`, `shop_group`, `prefix` (optional — coupon ID prefix filter)

**Response 200:**
```json
{
  "all_time_kpis": {
    "used": 12345,
    "unused": 6789,
    "amount_vnd": "123,456,789"
  },
  "period_kpis": {
    "used": 1234,
    "unused": 567,
    "amount_vnd": "12,345,678"
  },
  "tabs": {
    "by_shop":    { "headers": [...], "rows": [[...]] },
    "detail":     { "headers": [...], "rows": [[...]] },
    "duplicates": { "headers": [...], "rows": [[...]] }
  }
}
```

---

### GET /api/v1/analytics/shop-detail/

**Permissions required**: `shop_detail.view`  
**Query params**: `shop` (required — exact shop name), `date_from`, `date_to`

**Response 200:**
```json
{
  "shop_name": "Semir Hà Nội",
  "sales": {
    "all_time_kpis": { ... },
    "period_kpis": { ... },
    "by_session": { "headers": [...], "rows": [[...]] },
    "by_month":   { "headers": [...], "rows": [[...]] },
    "by_week":    { "headers": [...], "rows": [[...]] }
  },
  "customer": {
    "all_time_kpis": { ... },
    "period_kpis": { ... },
    "breakdown": { "headers": [...], "rows": [[...]] }
  },
  "coupon": {
    "all_time_kpis": { ... },
    "period_kpis": { ... },
    "by_shop_table": { "headers": [...], "rows": [[...]] }
  }
}
```

**Additional endpoint for dropdown:**

### GET /api/v1/analytics/shops/

Returns the list of available shop names for the dropdown selector on Shop Detail.

**Response 200:**
```json
{
  "shops": ["Semir Hà Nội", "Semir TP.HCM", "Bala Hà Nội", ...]
}
```

---

### GET /api/v1/analytics/customer-detail/

**Permissions required**: `customer_detail.view`  
**Query params**: `vip_id` OR `phone` (one required)

**Response 200:**
```json
{
  "vip_id": "VIP12345",
  "phone": "09x-xxx-xx89",
  "grade": "Gold",
  "registration_store": "Semir Hà Nội",
  "registration_date": "2023-05-15",
  "total_invoices": 12,
  "total_revenue": "12,345,678",
  "cnv_sync_status": "synced",
  "invoice_history": [
    {
      "date": "2025-03-10",
      "shop": "Semir Hà Nội",
      "invoice_id": "INV-0001234",
      "amount": "1,234,567",
      "coupon_used": "SEMIR001"
    }
  ]
}
```

**Response 404:**
```json
{ "detail": "Customer not found" }
```

**Notes on PII:** The `phone` field returned by the API MUST be masked (middle digits replaced) before being sent to the mobile client. The mobile app must never log or include phone or invoice numbers in crash reports (FR-006, FR-046).

---

## Chart Endpoints

### GET /api/v1/charts/sales/

**Permissions required**: `sales.view`  
**Query params**: `date_from`, `date_to`, `shop_group`

**Response 200:**
```json
{
  "donuts": [
    {
      "title": "By Season",
      "slices": [
        { "label": "M2-4 2025", "value": 1234, "color": "#0d6efd" },
        { "label": "M5-7 2025", "value": 2345, "color": "#6610f2" }
      ]
    }
  ],
  "trend": {
    "metric": "return_rate",
    "series": [
      {
        "shop": "All Shops",
        "data_points": [
          { "date": "2025-01", "value": 45.98 },
          { "date": "2025-02", "value": 47.12 }
        ]
      }
    ]
  }
}
```

### GET /api/v1/charts/customer/
### GET /api/v1/charts/coupon/

Same structure as `/charts/sales/` with domain-appropriate donut and trend data. `trend` may be `null` if the page has no trend chart.

---

## Error Response Format

All error responses follow this envelope:

```json
{
  "detail": "Human-readable error message",
  "code": "optional_error_code"
}
```

| HTTP Status | Meaning | Mobile behavior |
|-------------|---------|-----------------|
| 200 | Success | Render data |
| 400 | Bad request (invalid params) | Show "invalid request" banner |
| 401 | Unauthenticated | Attempt token refresh → retry; if fails, route to login |
| 403 | Permission denied | Show "no access" message |
| 404 | Not found | Show "not found" message |
| 5xx | Server error | Show "server error" banner with retry button |

---

## Backend Implementation Notes (for SemirDashboard Sprint 0)

1. **Library**: `djangorestframework` + `djangorestframework-simplejwt` (already in Python ecosystem, minimal setup)
2. **Reuse existing analytics**: All endpoint handlers call existing functions (`get_sales_tab`, `_load_sales`, `compute_cnv_breakdown`, etc.) — no analytics logic duplication
3. **Permission enforcement**: Use DRF's `IsAuthenticated` + custom `HasPermission` permission class mirroring the existing `@requires_perm` decorator logic
4. **Rotate refresh tokens**: Configure `simplejwt` with `ROTATE_REFRESH_TOKENS = True` and `BLACKLIST_AFTER_ROTATION = True`
5. **CORS**: Add `django-cors-headers` to allow requests from any origin (mobile app origin is not a browser origin — CORS doesn't apply to native apps, but needed if web admin also uses the API)
6. **URL prefix**: Add `path("api/v1/", include("App.api_urls"))` in `SemirDashboard/urls.py`
7. **Response formatting**: Pre-format all VND values and percentages in the serializer (not in the mobile app). Use the existing `|vnd` filter logic as a Python function in the serializer layer.
