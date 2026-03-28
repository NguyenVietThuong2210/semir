"""
App/views/shop_names.py

CRUD for ShopNameTitle and ShopNameAlias.
Served as a section on the Upload Sales page.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from App.models import ShopNameTitle, ShopNameAlias
from App.permissions import requires_perm
from App.analytics.shop_utils import invalidate_shop_map


def _invalidate_all_caches():
    """Invalidate shop map + all analytics caches whenever shop name mappings change."""
    invalidate_shop_map()
    from App.views.analytics import _invalidate_analytics_cache
    from App.views.coupon import _invalidate_coupon_cache
    from App.cnv.views import _invalidate_cnv_cache
    _invalidate_analytics_cache()
    _invalidate_coupon_cache()
    _invalidate_cnv_cache()


# ── Title CRUD ────────────────────────────────────────────────────────────────

@requires_perm("page_upload")
@require_http_methods(["GET"])
def shop_titles_list(request):
    """Return all titles with their aliases as JSON."""
    titles = []
    for t in ShopNameTitle.objects.prefetch_related("aliases").all():
        titles.append({
            "id": t.id,
            "title": t.title,
            "aliases": [{"id": a.id, "alias": a.alias} for a in t.aliases.all()],
        })
    return JsonResponse({"titles": titles})


@requires_perm("page_upload")
@require_POST
def shop_title_create(request):
    try:
        data = json.loads(request.body)
        title_text = (data.get("title") or "").strip()
        if not title_text:
            return JsonResponse({"error": "Title is required"}, status=400)
        if ShopNameTitle.objects.filter(title=title_text).exists():
            return JsonResponse({"error": "Title already exists"}, status=400)
        t = ShopNameTitle.objects.create(title=title_text)
        _invalidate_all_caches()
        return JsonResponse({"id": t.id, "title": t.title})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@requires_perm("page_upload")
@require_http_methods(["POST"])
def shop_title_update(request, title_id):
    try:
        data = json.loads(request.body)
        title_text = (data.get("title") or "").strip()
        if not title_text:
            return JsonResponse({"error": "Title is required"}, status=400)
        t = ShopNameTitle.objects.get(pk=title_id)
        if ShopNameTitle.objects.filter(title=title_text).exclude(pk=title_id).exists():
            return JsonResponse({"error": "Title already exists"}, status=400)
        t.title = title_text
        t.save()
        _invalidate_all_caches()
        return JsonResponse({"id": t.id, "title": t.title})
    except ShopNameTitle.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@requires_perm("page_upload")
@require_POST
def shop_title_delete(request, title_id):
    try:
        ShopNameTitle.objects.filter(pk=title_id).delete()
        _invalidate_all_caches()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ── Alias CRUD ────────────────────────────────────────────────────────────────

@requires_perm("page_upload")
@require_POST
def shop_alias_create(request):
    try:
        data = json.loads(request.body)
        alias_text = (data.get("alias") or "").strip()
        title_id = data.get("title_id")
        if not alias_text or not title_id:
            return JsonResponse({"error": "alias and title_id are required"}, status=400)
        if ShopNameAlias.objects.filter(alias=alias_text).exists():
            return JsonResponse({"error": "Alias already exists"}, status=400)
        t = ShopNameTitle.objects.get(pk=title_id)
        a = ShopNameAlias.objects.create(title=t, alias=alias_text)
        _invalidate_all_caches()
        return JsonResponse({"id": a.id, "alias": a.alias, "title_id": t.id})
    except ShopNameTitle.DoesNotExist:
        return JsonResponse({"error": "Title not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@requires_perm("page_upload")
@require_POST
def shop_alias_update(request, alias_id):
    try:
        data = json.loads(request.body)
        alias_text = (data.get("alias") or "").strip()
        if not alias_text:
            return JsonResponse({"error": "alias is required"}, status=400)
        a = ShopNameAlias.objects.get(pk=alias_id)
        if ShopNameAlias.objects.filter(alias=alias_text).exclude(pk=alias_id).exists():
            return JsonResponse({"error": "Alias already exists"}, status=400)
        a.alias = alias_text
        a.save()
        _invalidate_all_caches()
        return JsonResponse({"id": a.id, "alias": a.alias})
    except ShopNameAlias.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@requires_perm("page_upload")
@require_POST
def shop_alias_delete(request, alias_id):
    try:
        ShopNameAlias.objects.filter(pk=alias_id).delete()
        _invalidate_all_caches()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@requires_perm("page_upload")
@require_http_methods(["GET"])
def shop_raw_names(request):
    """Return all distinct raw shop names not yet mapped to any alias."""
    from App.models import SalesTransaction, Customer

    mapped = set(ShopNameAlias.objects.values_list("alias", flat=True))

    raw_sales = set(
        SalesTransaction.objects
        .exclude(shop_name="").exclude(shop_name__isnull=True)
        .values_list("shop_name", flat=True).distinct()
    )
    raw_reg = set(
        Customer.objects
        .exclude(registration_store="").exclude(registration_store__isnull=True)
        .values_list("registration_store", flat=True).distinct()
    )
    all_raw = sorted((raw_sales | raw_reg) - mapped)
    return JsonResponse({"unmapped": all_raw})


@requires_perm("page_upload")
@require_POST
def shop_seed_titles(request):
    """
    Auto-create a ShopNameTitle for every distinct raw shop name in the DB
    that is not already covered by an existing title or alias.

    Returns counts: created / skipped.
    """
    from App.models import SalesTransaction, Customer
    try:
        from App.models import Coupon
        raw_coupon = set(
            Coupon.objects
            .exclude(using_shop="").exclude(using_shop__isnull=True)
            .values_list("using_shop", flat=True).distinct()
        )
    except Exception:
        raw_coupon = set()

    from App.models import SalesTransaction, Customer

    raw_sales = set(
        SalesTransaction.objects
        .exclude(shop_name="").exclude(shop_name__isnull=True)
        .values_list("shop_name", flat=True).distinct()
    )
    raw_reg = set(
        Customer.objects
        .exclude(registration_store="").exclude(registration_store__isnull=True)
        .values_list("registration_store", flat=True).distinct()
    )

    all_raw = {s.strip() for s in (raw_sales | raw_reg | raw_coupon) if s and s.strip()}

    # Skip names already covered by a title or an alias
    existing_titles = set(ShopNameTitle.objects.values_list("title", flat=True))
    existing_aliases = set(ShopNameAlias.objects.values_list("alias", flat=True))
    covered = existing_titles | existing_aliases

    to_create = sorted(all_raw - covered)
    created = 0
    for name in to_create:
        ShopNameTitle.objects.get_or_create(title=name)
        created += 1

    _invalidate_all_caches()
    return JsonResponse({"created": created, "skipped": len(all_raw) - created})
