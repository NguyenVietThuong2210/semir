"""App/views/customer.py — Customer detail view."""
import logging
from django.shortcuts import render
from django.contrib import messages

from App.permissions import requires_perm
from App.models import Customer, SalesTransaction, Coupon
from App.cnv.models import CNVCustomer
from App.analytics.shop_utils import get_shop_map, normalize_shop_display

logger = logging.getLogger(__name__)


@requires_perm("page_customer_detail")
def customer_detail(request):
    """
    Customer Detail Analytics - Search and view individual customer info.
    Searches by VIP ID or Phone Number.
    Shows customer info, CNV sync status, and invoice history.
    """
    search_vip_id = request.GET.get("vip_id", "").strip()
    search_phone = request.GET.get("phone", "").strip()

    customer = None
    invoices = []
    stats = {}
    is_synced_to_cnv = False
    cnv_customer = None
    search_attempted = bool(search_vip_id or search_phone)

    if search_vip_id or search_phone:
        logger.info(
            "customer_detail: vip_id=%s phone=%s user=%s",
            search_vip_id,
            search_phone,
            request.user,
        )

        # Search customer
        if search_vip_id:
            try:
                customer = Customer.objects.get(vip_id=search_vip_id)
            except Customer.DoesNotExist:
                logger.warning("Customer not found: vip_id=%s", search_vip_id)
        elif search_phone:
            try:
                customer = Customer.objects.get(phone=search_phone)
            except Customer.DoesNotExist:
                logger.warning("Customer not found: phone=%s", search_phone)
            except Customer.MultipleObjectsReturned:
                # If multiple customers with same phone, get first one
                customer = Customer.objects.filter(phone=search_phone).first()
                logger.warning(
                    "Multiple customers found with phone=%s, using first", search_phone
                )

        if customer:
            # Check CNV sync status (use 'phone' field not 'phone_no')
            if customer.phone:
                cnv_customer = CNVCustomer.objects.filter(phone=customer.phone).first()
                is_synced_to_cnv = cnv_customer is not None
                if cnv_customer:
                    logger.debug(
                        "cnv_match: phone=%s total_points=%s used_points=%s points=%s",
                        customer.phone, cnv_customer.total_points, cnv_customer.used_points, cnv_customer.points,
                    )

            # Get all invoices for this customer
            invoices = (
                SalesTransaction.objects.filter(vip_id=customer.vip_id)
                .select_related()
                .order_by("-sales_date")
            )

            _shop_map = get_shop_map()

            # Add coupon info to each invoice
            invoices_with_coupons = []
            for inv in invoices:
                invoice_data = {
                    "invoice_no": inv.invoice_number,
                    "sales_day": inv.sales_date,
                    "shop_name": normalize_shop_display(inv.shop_name, _shop_map) or inv.shop_name,
                    "amount": inv.settlement_amount,
                    "season": inv.bu,
                    "coupon_id": None,
                    "face_value_display": None,
                    "coupon_amount": None,
                }

                # Check if this invoice has a coupon
                coupon = Coupon.objects.filter(
                    docket_number=inv.invoice_number, using_date__isnull=False
                ).first()

                if coupon:
                    invoice_data["coupon_id"] = coupon.coupon_id
                    # Display face value
                    from App.analytics.coupon_analytics import (
                        format_face_value,
                        calc_coupon_amount,
                    )

                    invoice_data["face_value_display"] = format_face_value(
                        coupon.face_value
                    )
                    invoice_data["coupon_amount"] = calc_coupon_amount(
                        coupon.face_value, inv.settlement_amount
                    )

                invoices_with_coupons.append(invoice_data)

            invoices = invoices_with_coupons

            # Calculate statistics
            from decimal import Decimal
            from django.db.models import Sum, Max, Count

            invoice_stats = SalesTransaction.objects.filter(
                vip_id=customer.vip_id
            ).aggregate(
                total=Count("id"),
                total_amount=Sum("settlement_amount"),
                last_date=Max("sales_date"),
            )

            stats = {
                "total_purchases": invoice_stats["total"] or 0,
                "total_amount": invoice_stats["total_amount"] or Decimal(0),
                "last_purchase_date": invoice_stats["last_date"],
            }

    return render(
        request,
        "customer/detail.html",
        {
            "customer": customer,
            "invoices": invoices,
            "stats": stats,
            "is_synced_to_cnv": is_synced_to_cnv,
            "cnv_customer": cnv_customer,
            "search_vip_id": search_vip_id,
            "search_phone": search_phone,
            "search_attempted": search_attempted,
        },
    )
