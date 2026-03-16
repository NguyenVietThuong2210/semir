from django.conf import settings


def feature_flags(request):
    return {
        "SHOW_CUSTOMER_CHART": getattr(settings, "SHOW_CUSTOMER_CHART", False),
    }
