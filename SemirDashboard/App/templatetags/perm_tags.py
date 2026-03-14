from django import template
from App.permissions import user_has_perm

register = template.Library()


@register.simple_tag(takes_context=True)
def check_perm(context, codename):
    request = context.get('request')
    if not request:
        return False
    return user_has_perm(request.user, codename)
