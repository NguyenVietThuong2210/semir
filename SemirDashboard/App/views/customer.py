"""App/views/customer.py — Customer detail view."""
import logging

from django.shortcuts import render
from django.contrib import messages

from App.permissions import requires_perm
from App.models import Customer
from App.analytics.customer_utils import get_customer_detail_data

logger = logging.getLogger(__name__)


@requires_perm("customers.detail")
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
                customer = Customer.objects.filter(phone=search_phone).first()
                logger.warning(
                    "Multiple customers found with phone=%s, using first", search_phone
                )

        if customer:
            detail = get_customer_detail_data(customer)
            cnv_customer    = detail['cnv_customer']
            is_synced_to_cnv = detail['is_synced_to_cnv']
            invoices        = detail['invoices']
            stats           = detail['stats']
            if cnv_customer:
                logger.debug(
                    "cnv_match: phone=%s total_points=%s used_points=%s points=%s",
                    customer.phone, cnv_customer.total_points,
                    cnv_customer.used_points, cnv_customer.points,
                )

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
