# ═══════════════════════════════════════════════════════════════
#  CUSTOMER ANALYTICS CHARTS
# ═══════════════════════════════════════════════════════════════

_CUST_CHART_VER_KEY = "cust_chart_ver"
_CUST_CHART_TTL = 300


def _cust_chart_cache_key(start_date, end_date):
    v = cache.get(_CUST_CHART_VER_KEY, 0)
    return f"cust_chart:{v}:{start_date}:{end_date}"


def _compute_customer_chart_data(date_from=None, date_to=None):
    """Compute all data needed for Customer Analytics Charts page.

    Uses the same base querysets as _get_cnv_comparison_data so that
    all four metrics are calculated identically between both pages.
    """
    # ── Base querysets (mirrors _get_cnv_comparison_data) ───────
    # POS: exclude vip_id=0 (non-VIP), require phone
    pos_base = (
        POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone="")
    )
    # CNV: require phone (needed for POS↔CNV matching)
    cnv_base = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
    # Zalo: exclude empty-string IDs (as in customer_comparison)
    zalo_app_base = (
        CNVCustomer.objects.filter(zalo_app_id__isnull=False, zalo_app_created_at__isnull=False)
        .exclude(zalo_app_id="")
    )
    zalo_oa_base = (
        CNVCustomer.objects.filter(zalo_oa_id__isnull=False, zalo_app_created_at__isnull=False)
        .exclude(zalo_oa_id="")
    )

    # ── All-time overview (no date filter) ──────────────────────
    total_cnv     = CNVCustomer.objects.count()
    total_pos     = POSCustomer.objects.filter(vip_id__isnull=False).exclude(vip_id=0).count()
    active_zalo_t = CNVCustomer.objects.filter(zalo_app_id__isnull=False).exclude(zalo_app_id="").count()
    follow_oa_t   = CNVCustomer.objects.filter(zalo_oa_id__isnull=False).exclude(zalo_oa_id="").count()

    # POS ↔ CNV overlap — set-difference (mirrors customer_comparison)
    pos_phones = set(pos_base.values_list("phone", flat=True))
    cnv_phones = set(cnv_base.values_list("phone", flat=True))
    cnv_only_count = len(cnv_phones - pos_phones)
    pos_only_count = len(pos_phones - cnv_phones)

    # ── Inner helper: build week / month / season / year series ─
    def _build_series(df=None, dt=None):
        qs_pos  = pos_base
        qs_cnv  = cnv_base
        qs_zalo = zalo_app_base
        qs_oa   = zalo_oa_base
        if df:
            qs_pos  = qs_pos.filter(registration_date__gte=df)
            qs_cnv  = qs_cnv.filter(cnv_created_at__date__gte=df)
            qs_zalo = qs_zalo.filter(zalo_app_created_at__date__gte=df)
            qs_oa   = qs_oa.filter(zalo_app_created_at__date__gte=df)
        if dt:
            qs_pos  = qs_pos.filter(registration_date__lte=dt)
            qs_cnv  = qs_cnv.filter(cnv_created_at__date__lte=dt)
            qs_zalo = qs_zalo.filter(zalo_app_created_at__date__lte=dt)
            qs_oa   = qs_oa.filter(zalo_app_created_at__date__lte=dt)

        def _grp_month(qs, field):
            return {
                f"{d['y']:04d}-{d['m']:02d}": d["cnt"]
                for d in qs.annotate(y=ExtractYear(field), m=ExtractMonth(field))
                           .values("y", "m").annotate(cnt=Count("id")).order_by("y", "m")
                if d["y"] and d["m"]
            }

        def _grp_week(qs, field):
            return {
                f"{d['y']:04d}-W{d['w']:02d}": d["cnt"]
                for d in qs.annotate(y=ExtractYear(field), w=ExtractWeek(field))
                           .values("y", "w").annotate(cnt=Count("id")).order_by("y", "w")
                if d["y"] and d["w"]
            }

        def _grp_year(qs, field):
            return {
                str(d["y"]): d["cnt"]
                for d in qs.annotate(y=ExtractYear(field))
                           .values("y").annotate(cnt=Count("id")).order_by("y")
                if d["y"]
            }

        # Month
        pm = _grp_month(qs_pos,  "registration_date")
        nm = _grp_month(qs_cnv,  "cnv_created_at")
        zm = _grp_month(qs_zalo, "zalo_app_created_at")
        om = _grp_month(qs_oa,   "zalo_app_created_at")
        all_months = sorted(set(pm) | set(nm) | set(zm) | set(om))
        month_stats = [
            {"month": m, "new_pos_users": pm.get(m, 0), "new_cnv_users": nm.get(m, 0),
             "active_zalo": zm.get(m, 0), "follow_oa": om.get(m, 0)}
            for m in all_months
        ]

        # Season: SS = Jan-Jun, AW = Jul-Dec
        season_data = {}
        for ms in month_stats:
            y, mo = ms["month"].split("-")
            s = f"{'SS' if int(mo) <= 6 else 'AW'}{y}"
            if s not in season_data:
                season_data[s] = {"season": s, "new_pos_users": 0, "new_cnv_users": 0,
                                  "active_zalo": 0, "follow_oa": 0}
            for k in ("new_pos_users", "new_cnv_users", "active_zalo", "follow_oa"):
                season_data[s][k] += ms[k]
        season_stats = [season_data[s] for s in sorted(season_data)]

        # Week
        pw = _grp_week(qs_pos,  "registration_date")
        nw = _grp_week(qs_cnv,  "cnv_created_at")
        zw = _grp_week(qs_zalo, "zalo_app_created_at")
        ow = _grp_week(qs_oa,   "zalo_app_created_at")
        all_weeks = sorted(set(pw) | set(nw) | set(zw) | set(ow))
        week_stats = [
            {"week": w, "new_pos_users": pw.get(w, 0), "new_cnv_users": nw.get(w, 0),
             "active_zalo": zw.get(w, 0), "follow_oa": ow.get(w, 0)}
            for w in all_weeks
        ]

        # Year
        py_ = _grp_year(qs_pos,  "registration_date")
        ny_ = _grp_year(qs_cnv,  "cnv_created_at")
        zy_ = _grp_year(qs_zalo, "zalo_app_created_at")
        oy_ = _grp_year(qs_oa,   "zalo_app_created_at")
        all_years = sorted(set(py_) | set(ny_) | set(zy_) | set(oy_))
        year_stats = [
            {"year": y, "new_pos_users": py_.get(y, 0), "new_cnv_users": ny_.get(y, 0),
             "active_zalo": zy_.get(y, 0), "follow_oa": oy_.get(y, 0)}
            for y in all_years
        ]

        return month_stats, season_stats, week_stats, year_stats

    month_stats,     season_stats,     week_stats,     year_stats     = _build_series(date_from, date_to)
    all_month_stats, all_season_stats, all_week_stats, all_year_stats = _build_series()  # all-time for YOY

    return {
        "overview": {
            "total_cnv":   total_cnv,
            "active_zalo": active_zalo_t,
            "follow_oa":   follow_oa_t,
            "cnv_only":    cnv_only_count,
            "pos_only":    pos_only_count,
            "total_pos":   total_pos,
        },
        "month_stats":      month_stats,
        "season_stats":     season_stats,
        "week_stats":       week_stats,
        "year_stats":       year_stats,
        "all_month_stats":  all_month_stats,
        "all_season_stats": all_season_stats,
        "all_week_stats":   all_week_stats,
        "all_year_stats":   all_year_stats,
    }


@requires_perm("page_customer_chart")
def customer_chart(request):
    """Customer Analytics Charts — donut overview + bar chart + YOY comparison."""
    if not getattr(settings, "SHOW_CUSTOMER_CHART", False):
        raise Http404
    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")

    date_from = date_to = None
    try:
        if start_date:
            date_from = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        start_date = ""
    try:
        if end_date:
            date_to = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        end_date = ""

    if date_from and date_to and date_from > date_to:
        date_from = date_to = None
        start_date = end_date = ""

    cache_key = _cust_chart_cache_key(start_date, end_date)
    data = cache.get(cache_key)
    if data is None:
        data = _compute_customer_chart_data(date_from, date_to)
        cache.set(cache_key, data, _CUST_CHART_TTL)

    now_year = datetime.now().year
    return render(
        request,
        "cnv/customer_chart.html",
        {
            "overview":         data["overview"],
            "chart_data_json":  json.dumps(data),
            "start_date":       start_date,
            "end_date":         end_date,
            "quick_btns":       [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90)],
            "year_btns":        [now_year - i for i in range(4)],
        },
    )
