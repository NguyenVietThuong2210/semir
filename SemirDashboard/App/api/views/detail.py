"""App/api/views/detail.py — customer detail endpoint (+phone masking)
Split from api/views.py (R4, 2026-07-12).
"""
import logging
from datetime import datetime, timedelta

from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from App.permissions import user_has_perm, PERMISSION_DEFS
from App.api.permissions import make_perm_class

logger = logging.getLogger('App')
from .helpers import _fmt, _fmtd, _parse_date  # noqa: F401

class CustomerDetailView(APIView):
    """GET /api/v1/analytics/customer-detail/?vip_id=<id> OR ?phone=<phone>"""
    permission_classes = [IsAuthenticated, make_perm_class('customers.detail')]

    def get(self, request):
        from App.models import Customer
        from App.analytics.customer_utils import normalize_grade, get_customer_detail_data

        vip_id = request.GET.get('vip_id', '').strip()
        phone = request.GET.get('phone', '').strip()

        if not vip_id and not phone:
            return Response({'detail': 'vip_id or phone is required'}, status=400)

        try:
            if vip_id:
                customer = Customer.objects.get(vip_id=vip_id)
            else:
                # Strip formatting — match on last 9 digits for flexibility
                digits = ''.join(c for c in phone if c.isdigit())
                # C-08: too-short input would endswith-match unrelated customers
                # (empty digits matches the ENTIRE table) — hard 400 below 9 digits.
                if len(digits) < 9:
                    return Response({'detail': 'Phone must contain at least 9 digits'}, status=400)
                customer = Customer.objects.filter(phone__endswith=digits[-9:]).first()
                if customer is None:
                    return Response({'detail': 'Customer not found'}, status=404)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found'}, status=404)
        except Customer.MultipleObjectsReturned:
            customer = Customer.objects.filter(vip_id=vip_id).first()

        # Mask phone (middle digits) — FR-006, PII protection
        masked_phone = _mask_phone(customer.phone or '')

        # Shared data fetch (same function used by web view — no cap, full parity)
        detail = get_customer_detail_data(customer, include_coupons=False)
        cnv_sync = 'synced' if detail['is_synced_to_cnv'] else 'not_synced'
        total_invoices = detail['total_invoice_count']
        invoices = detail['invoices']
        total_revenue = sum(float(inv.get('amount') or 0) for inv in invoices)

        invoice_history = [
            {
                'date': str(inv['sales_day'] or ''),
                'shop': inv['shop_name'] or '',
                'invoice_id': inv['invoice_no'] or '',
                'amount': _fmt(inv.get('amount') or 0),
                'coupon_used': '',
            }
            for inv in invoices
        ]

        return Response({
            'name': customer.name or '',
            'vip_id': str(customer.vip_id or ''),
            'phone': masked_phone,
            'grade': normalize_grade(customer.vip_grade),
            'registration_store': customer.registration_store or '',
            'registration_date': str(customer.registration_date or ''),
            'email': customer.email or '',
            'total_invoices': total_invoices,
            'total_revenue': _fmt(total_revenue),
            'cnv_sync_status': cnv_sync,
            'invoice_history': invoice_history,
        })


def _mask_phone(phone: str) -> str:
    """Mask middle digits of phone number. e.g. 0912345678 → 09x-xxx-x678"""
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 7:
        return phone  # too short to mask meaningfully
    # Keep first 2 + last 3, mask middle
    prefix = digits[:2]
    suffix = digits[-3:]
    mid = 'x' * (len(digits) - 5)
    return f"{prefix}x-xxx-x{suffix}"


# ═══════════════════════════════════════════════════════════════════════════════
# CHART ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

