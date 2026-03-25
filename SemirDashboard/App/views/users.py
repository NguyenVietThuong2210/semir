"""
user_views.py - User & Role Management Views
All endpoints require manage_users permission.
"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User

from App.permissions import requires_perm, PERMISSION_DEFS
from App.models import Role, UserProfile

logger = logging.getLogger(__name__)


@requires_perm('manage_users')
def user_management(request):
    """Main user management page with Users and Roles tabs."""

    if request.method == 'POST':
        action = request.POST.get('action')

        # ── Set a user's role ────────────────────────────────────────────────
        if action == 'set_user_role':
            user_id = request.POST.get('user_id')
            role_id = request.POST.get('role_id')
            try:
                target_user = User.objects.get(pk=user_id)
                profile, _ = UserProfile.objects.get_or_create(user=target_user)
                old_role = profile.role.name if profile.role else None
                if role_id:
                    role = Role.objects.get(pk=role_id)
                    profile.role = role
                    new_role = role.name
                else:
                    profile.role = None
                    new_role = None
                profile.save()
                logger.info(
                    "set_user_role: user=%s old_role=%s new_role=%s by=%s",
                    target_user.username, old_role, new_role, request.user,
                    extra={"step": "user_management"},
                )
                messages.success(request, f"Role updated for {target_user.username}.")
            except (User.DoesNotExist, Role.DoesNotExist):
                logger.warning("set_user_role: user_id=%s role_id=%s not found by=%s", user_id, role_id, request.user)
                messages.error(request, "User or role not found.")
            return redirect('user_management')

        # ── Save role permissions ────────────────────────────────────────────
        elif action == 'save_role_permissions':
            role_id = request.POST.get('role_id')
            try:
                role = Role.objects.get(pk=role_id)
                selected = request.POST.getlist(f'perm_{role_id}')
                role.permissions = selected
                role.save()
                logger.info(
                    "save_role_permissions: role=%s perms=%s by=%s",
                    role.name, selected, request.user,
                    extra={"step": "user_management"},
                )
                messages.success(request, f"Permissions saved for role '{role.name}'.")
            except Role.DoesNotExist:
                logger.warning("save_role_permissions: role_id=%s not found by=%s", role_id, request.user)
                messages.error(request, "Role not found.")
            return redirect('user_management')

        # ── Create new role ──────────────────────────────────────────────────
        elif action == 'create_role':
            role_name = request.POST.get('role_name', '').strip()
            if not role_name:
                messages.error(request, "Role name cannot be empty.")
            elif Role.objects.filter(name=role_name).exists():
                messages.error(request, f"A role named '{role_name}' already exists.")
            else:
                Role.objects.create(name=role_name, permissions=[], is_system=False)
                logger.info("create_role: name=%s by=%s", role_name, request.user, extra={"step": "user_management"})
                messages.success(request, f"Role '{role_name}' created.")
            return redirect('user_management')

        # ── Delete role ──────────────────────────────────────────────────────
        elif action == 'delete_role':
            role_id = request.POST.get('role_id')
            try:
                role = Role.objects.get(pk=role_id)
                if role.is_system:
                    logger.warning("delete_role: blocked — system role=%s by=%s", role.name, request.user)
                    messages.error(request, f"Cannot delete system role '{role.name}'.")
                else:
                    role_name = role.name
                    role.delete()
                    logger.info("delete_role: name=%s by=%s", role_name, request.user, extra={"step": "user_management"})
                    messages.success(request, f"Role '{role_name}' deleted.")
            except Role.DoesNotExist:
                logger.warning("delete_role: role_id=%s not found by=%s", role_id, request.user)
                messages.error(request, "Role not found.")
            return redirect('user_management')

        else:
            messages.error(request, "Unknown action.")
            return redirect('user_management')

    # ── GET ──────────────────────────────────────────────────────────────────
    users = User.objects.select_related('profile__role').order_by('username')
    roles = Role.objects.all()

    # Group permissions by category for the template
    categories = {}
    for codename, display, category in PERMISSION_DEFS:
        categories.setdefault(category, []).append((codename, display))

    return render(request, 'user_management.html', {
        'users': users,
        'roles': roles,
        'all_roles': roles,
        'permission_categories': categories,
    })
