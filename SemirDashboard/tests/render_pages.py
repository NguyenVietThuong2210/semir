"""
Standalone script: render every discovered GET page and report status + timing.
Run from SemirDashboard/ directory:
  python manage.py shell < tests/render_pages.py
OR:
  python manage.py shell -c "exec(open('tests/render_pages.py').read())"
"""
import time
from django.conf import settings
settings.ALLOWED_HOSTS = list(set(settings.ALLOWED_HOSTS) | {'testserver', 'localhost', '127.0.0.1'})
from django.test import Client
from django.contrib.auth.models import User
from django.urls import reverse

c = Client()
superuser = User.objects.filter(is_superuser=True).first()
if not superuser:
    print("ERROR: no superuser found — create one first")
    raise SystemExit(1)
c.force_login(superuser)

# ── URL list discovered dynamically from App/urls.py + App/cnv/urls.py ────────
# [period-filter] routes tested in two variants: alltime + 2025
# POST-only / AJAX-only routes excluded
pages = [
    # Home & Static
    ("/",                                      "home"),
    ("/formulas/",                             "formulas"),
    # Upload (GET form render)
    ("/upload/customers/",                     "upload_customers"),
    ("/upload/sales/",                         "upload_sales"),
    ("/upload/coupons/",                       "upload_coupons"),
    ("/upload/jobs/",                          "upload_jobs_list"),
    # Analytics dashboard [period-filter]
    ("/analytics/",                            "analytics_dashboard [alltime]"),
    ("/analytics/?start_date=2025-01-01&end_date=2025-12-31",
                                               "analytics_dashboard [2025]"),
    # Analytics chart [period-filter]
    ("/analytics/chart/",                      "analytics_chart [alltime]"),
    ("/analytics/chart/?start_date=2025-01-01&end_date=2025-12-31",
                                               "analytics_chart [2025]"),
    # Analytics tab AJAX (representative tab — season)
    ("/analytics/tab/season/",                 "analytics_tab [season AJAX]"),
    # Coupon dashboard [period-filter]
    ("/coupons/",                              "coupon_dashboard [alltime]"),
    ("/coupons/?start_date=2025-01-01&end_date=2025-12-31",
                                               "coupon_dashboard [2025]"),
    # Coupon chart [period-filter]
    ("/coupons/chart/",                        "coupon_chart [alltime]"),
    ("/coupons/chart/?start_date=2025-01-01&end_date=2025-12-31",
                                               "coupon_chart [2025]"),
    # Coupon campaigns (GET → JSON)
    ("/coupons/campaigns/",                    "manage_campaigns"),
    # Customer detail
    ("/customer-detail/",                      "customer_detail [empty]"),
    ("/customer-detail/?vip_id=XXXXNOTEXIST",  "customer_detail [not found]"),
    # Shop detail
    ("/shop-detail/",                          "shop_detail"),
    # Admin
    ("/users/",                                "user_management"),
    ("/admin-logs/",                           "admin_logs"),
    # CNV
    ("/cnv/sync-status/",                      "cnv:sync_status"),
    ("/cnv/customer-analytics/",               "cnv:customer_analytics [alltime]"),
    ("/cnv/customer-analytics/?start_date=2025-01-01&end_date=2025-12-31",
                                               "cnv:customer_analytics [2025]"),
    ("/cnv/customer-chart/",                   "cnv:customer_chart [alltime]"),
    ("/cnv/customer-chart/?start_date=2025-01-01&end_date=2025-12-31",
                                               "cnv:customer_chart [2025]"),
]

results = []
print(f"\n{'Label':45s} {'URL':50s} {'Status':8s} {'Time':>7s}")
print("─" * 115)
for url, label in pages:
    try:
        t0 = time.time()
        r = c.get(url, follow=False,
                  HTTP_X_REQUESTED_WITH="XMLHttpRequest" if "AJAX" in label else "")
        elapsed = time.time() - t0
        ok = r.status_code == 200
        status = "OK" if ok else f"FAIL({r.status_code})"
        results.append((label, url, r.status_code, status, elapsed))
        print(f"  {label:43s} {url:50s} {status:8s} {elapsed:6.2f}s")
    except Exception as e:
        results.append((label, url, "ERR", str(e)[:60], 0))
        print(f"  {label:43s} {url:50s} ERR      {str(e)[:40]}")

fails = [r for r in results if r[3] != "OK"]
print(f"\n{'─' * 115}")
print(f"  {len(results) - len(fails)}/{len(results)} pages OK")
if fails:
    print("\nFAILED PAGES:")
    for label, url, code, status, *_ in fails:
        print(f"  [{code}] {label} — {url}")
