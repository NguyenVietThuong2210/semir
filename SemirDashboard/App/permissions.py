from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages

PERMISSION_DEFS = [
    ('page_analytics',       'Analytics Dashboard',           'Pages'),
    ('page_chart',           'Overview Charts',               'Pages'),
    ('page_coupons',         'Coupon Dashboard',              'Pages'),
    ('page_customer_detail', 'Customer Detail',               'Pages'),
    ('page_upload',          'Upload Data',                   'Pages'),
    ('page_formulas',        'Formulas',                      'Pages'),
    ('page_cnv_sync',        'CNV Sync Status',               'Pages'),
    ('page_cnv_comparison',  'Customer Analytics',            'Pages'),
    ('download_analytics',   'Export Analytics (Excel)',      'Downloads'),
    ('download_chart_pdf',   'Download Charts PDF',           'Downloads'),
    ('download_coupons',     'Export Coupons (Excel)',        'Downloads'),
    ('download_cnv',         'Export CNV Comparison (Excel)', 'Downloads'),
    ('manage_users',         'User Management',               'Admin'),
]

ALL_PERMISSIONS   = [p[0] for p in PERMISSION_DEFS]
ADMIN_PERMISSIONS = ALL_PERMISSIONS
VIEWER_PERMISSIONS = [
    'page_analytics', 'page_chart', 'page_coupons',
    'page_customer_detail', 'page_formulas', 'page_cnv_sync', 'page_cnv_comparison',
]


def user_has_perm(user, codename):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        profile = user.profile
        if profile.role:
            return codename in (profile.role.permissions or [])
    except Exception:
        pass
    return False


def requires_perm(codename):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not user_has_perm(request.user, codename):
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
