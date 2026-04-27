"""
DRF permission classes mirroring the existing @requires_perm decorator.

Superusers have all permissions.
Regular users need their profile role to include the required codename.
"""
from rest_framework.permissions import BasePermission

from App.permissions import user_has_perm


class HasPermission(BasePermission):
    """
    Usage on a view:
        permission_classes = [IsAuthenticated, HasPermission]
        required_permission = "sales.view"
    """
    required_permission: str = ""

    def has_permission(self, request, view):
        perm = getattr(view, "required_permission", self.required_permission)
        return user_has_perm(request.user, perm)


def make_perm_class(codename: str):
    """Return a permission class requiring the given codename."""
    return type(
        f"Has_{codename.replace('.', '_')}",
        (HasPermission,),
        {"required_permission": codename},
    )
