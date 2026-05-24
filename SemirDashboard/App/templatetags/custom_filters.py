"""
================================
FILE 2: App/templatetags/custom_filters.py
================================
Action: CREATE NEW FILE
Location: App/templatetags/custom_filters.py
Description: Custom Django template filters for VND currency formatting
"""

from django import template
from django.conf import settings
from App.analytics.category_translations import translate_category

register = template.Library()


@register.filter(name='vnd')
def vnd_format(value):
    """
    Format number as VND currency with comma separators.
    
    Usage in template:
        {{ amount|vnd }}
    
    Examples:
        1000000 -> 1,000,000
        1234567890 -> 1,234,567,890
        1500.50 -> 1,501 (rounds to nearest integer)
    """
    try:
        # Convert to float first, then to int (rounds to nearest)
        num = int(float(value))
        # Format with comma as thousands separator
        return f"{num:,}"
    except (ValueError, TypeError):
        return value


@register.filter(name='cat_name')
def cat_name(value):
    """
    Translate a Chinese category string using CATEGORY_LANG setting.
    CATEGORY_LANG='VI' → '商品 (Hàng hóa)'
    CATEGORY_LANG='ZH' → '商品'
    """
    lang = getattr(settings, 'CATEGORY_LANG', 'VI')
    return translate_category(str(value) if value else '', lang)


@register.filter(name='vnd_full')
def vnd_full_format(value):
    """
    Format number as VND currency with comma separators and 'VND' suffix.
    
    Usage in template:
        {{ amount|vnd_full }}
    
    Examples:
        1000000 -> 1,000,000 VND
        1234567890 -> 1,234,567,890 VND
    """
    try:
        num = int(float(value))
        return f"{num:,} VND"
    except (ValueError, TypeError):
        return value