"""
Django management command: perm
Manage role permissions for SemirDashboard.

Usage:
  python manage.py perm sync                              # sync admin+viewer with permissions.py
  python manage.py perm show                              # print current state
  python manage.py perm add --codename <X> --role <Y>    # grant a permission to a role
  python manage.py perm remove --codename <X> --role <Y> # revoke a permission from a role
  python manage.py perm reset --role <Y>                 # reset role to default (admin/viewer only)
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Manage role permissions (sync / show / add / remove / reset)'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['sync', 'show', 'add', 'remove', 'reset'],
            help='Action to perform',
        )
        parser.add_argument('--codename', type=str, help='Permission codename')
        parser.add_argument('--role',     type=str, help='Role name')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        action = options['action']

        if action == 'sync':
            self._sync()
        elif action == 'show':
            self._show()
        elif action == 'add':
            self._require('--codename', options['codename'])
            self._require('--role',     options['role'])
            self._add(options['codename'], options['role'])
        elif action == 'remove':
            self._require('--codename', options['codename'])
            self._require('--role',     options['role'])
            self._remove(options['codename'], options['role'])
        elif action == 'reset':
            self._require('--role', options['role'])
            self._reset(options['role'])

    # ------------------------------------------------------------------
    def _require(self, flag, value):
        if not value:
            raise CommandError(f'{flag} is required for this action.')

    # ------------------------------------------------------------------
    def _sync(self):
        """Sync admin + viewer roles with ADMIN_PERMISSIONS / VIEWER_PERMISSIONS in permissions.py.
        Also removes obsolete codenames from custom roles."""
        from App.models import Role, UserProfile
        from App.permissions import ADMIN_PERMISSIONS, VIEWER_PERMISSIONS, PERMISSION_DEFS

        valid = {p[0] for p in PERMISSION_DEFS}

        self.stdout.write(self.style.MIGRATE_HEADING('Syncing roles with permissions.py...'))

        for role_name, ref_perms in [('admin', ADMIN_PERMISSIONS), ('viewer', VIEWER_PERMISSIONS)]:
            role, created = Role.objects.get_or_create(name=role_name)
            old = set(role.permissions or [])
            new = set(ref_perms)
            role.permissions = ref_perms
            role.is_system   = True
            role.save()

            if created:
                self.stdout.write(f'  created  {role_name} ({len(ref_perms)} perms)')
            elif old == new:
                self.stdout.write(f'  OK       {role_name} — already in sync ({len(new)} perms)')
            else:
                added   = sorted(new - old)
                removed = sorted(old - new)
                if added:
                    self.stdout.write(self.style.SUCCESS(f'  updated  {role_name} +{added}'))
                if removed:
                    self.stdout.write(self.style.WARNING(f'  updated  {role_name} -{removed}'))

        # Custom roles: strip codenames that no longer exist in PERMISSION_DEFS
        for role in Role.objects.filter(is_system=False):
            old   = set(role.permissions or [])
            clean = [p for p in (role.permissions or []) if p in valid]
            removed = old - set(clean)
            if removed:
                role.permissions = clean
                role.save()
                self.stdout.write(self.style.WARNING(
                    f'  cleaned  {role.name} — removed obsolete: {sorted(removed)}'
                ))
            else:
                self.stdout.write(f'  OK       {role.name} (custom) — no obsolete perms')

        # Ensure every user has a profile + role
        self.stdout.write(self.style.MIGRATE_HEADING('\nEnsuring all users have a profile...'))
        admin_role = Role.objects.get(name='admin')
        assigned = 0
        for user in User.objects.all():
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.role is None:
                profile.role = admin_role
                profile.save()
                self.stdout.write(f'  assigned admin to {user.username}')
                assigned += 1
        if assigned == 0:
            self.stdout.write('  All users already have roles.')

        self.stdout.write(self.style.SUCCESS('\nSync complete.'))

    # ------------------------------------------------------------------
    def _show(self):
        """Print current permission state."""
        from App.models import Role
        from App.permissions import PERMISSION_DEFS, ADMIN_PERMISSIONS, VIEWER_PERMISSIONS

        valid = {p[0] for p in PERMISSION_DEFS}

        # Permission definitions table
        self.stdout.write(self.style.MIGRATE_HEADING('\nPERMISSION_DEFS (permissions.py):'))
        self.stdout.write(f'  {"Codename":<28} {"Category":<12} Admin  Viewer')
        self.stdout.write('  ' + '-' * 60)
        for codename, display, category in PERMISSION_DEFS:
            a = 'YES' if codename in ADMIN_PERMISSIONS  else 'no'
            v = 'YES' if codename in VIEWER_PERMISSIONS else 'no'
            self.stdout.write(f'  {codename:<28} {category:<12} {a:<6} {v}')

        # Roles in DB
        self.stdout.write(self.style.MIGRATE_HEADING('\nRoles in DB:'))
        for r in Role.objects.all():
            db_perms  = set(r.permissions or [])
            ref_perms = set(ADMIN_PERMISSIONS if r.name == 'admin'
                            else VIEWER_PERMISSIONS if r.name == 'viewer'
                            else [])
            drift   = ref_perms and db_perms != ref_perms
            extra   = db_perms - valid   # codenames not in PERMISSION_DEFS at all
            missing = ref_perms - db_perms
            added_extra = db_perms - ref_perms - extra  # custom additions

            status = self.style.ERROR('DRIFT') if drift else self.style.SUCCESS('OK')
            tag    = 'system' if r.is_system else 'custom'
            self.stdout.write(
                f'  [{tag}] {r.name:<12} {len(db_perms):>2} perms  {r.users.count()} user(s)  [{status}]'
            )
            for p in sorted(db_perms):
                marker = ''
                if p not in valid:     marker = '  <-- OBSOLETE (not in PERMISSION_DEFS)'
                elif p in ref_perms:   marker = ''
                else:                  marker = '  <-- extra (manually added)'
                self.stdout.write(f'      {p}{marker}')
            for p in sorted(missing):
                self.stdout.write(self.style.WARNING(f'      {p}  <-- MISSING'))

        # Users
        self.stdout.write(self.style.MIGRATE_HEADING('\nUsers:'))
        for u in User.objects.select_related('profile__role').order_by('username'):
            role_name = str(getattr(getattr(u, 'profile', None), 'role', 'NO ROLE'))
            superuser = '  [superuser]' if u.is_superuser else ''
            self.stdout.write(f'  {u.username:<22} -> {role_name}{superuser}')

    # ------------------------------------------------------------------
    def _add(self, codename, role_name):
        """Grant a permission to a role."""
        from App.models import Role
        from App.permissions import PERMISSION_DEFS

        valid = {p[0] for p in PERMISSION_DEFS}
        if codename not in valid:
            raise CommandError(
                f'"{codename}" is not a valid codename.\n'
                f'Valid codenames: {sorted(valid)}'
            )

        try:
            role = Role.objects.get(name=role_name)
        except Role.DoesNotExist:
            existing = list(Role.objects.values_list('name', flat=True))
            raise CommandError(f'Role "{role_name}" does not exist. Existing: {existing}')

        perms = list(role.permissions or [])
        if codename in perms:
            self.stdout.write(self.style.WARNING(
                f'"{codename}" is already in role "{role_name}" — no change.'
            ))
        else:
            perms.append(codename)
            role.permissions = perms
            role.save()
            self.stdout.write(self.style.SUCCESS(
                f'Added "{codename}" to role "{role_name}". ({len(perms)} total perms)'
            ))

    # ------------------------------------------------------------------
    def _remove(self, codename, role_name):
        """Revoke a permission from a role."""
        from App.models import Role

        try:
            role = Role.objects.get(name=role_name)
        except Role.DoesNotExist:
            existing = list(Role.objects.values_list('name', flat=True))
            raise CommandError(f'Role "{role_name}" does not exist. Existing: {existing}')

        perms = list(role.permissions or [])
        if codename not in perms:
            self.stdout.write(self.style.WARNING(
                f'"{codename}" is not in role "{role_name}" — no change.'
            ))
        else:
            perms.remove(codename)
            role.permissions = perms
            role.save()
            self.stdout.write(self.style.SUCCESS(
                f'Removed "{codename}" from role "{role_name}". ({len(perms)} total perms)'
            ))

    # ------------------------------------------------------------------
    def _reset(self, role_name):
        """Reset admin or viewer role back to defaults from permissions.py."""
        from App.models import Role
        from App.permissions import ADMIN_PERMISSIONS, VIEWER_PERMISSIONS

        defaults = {'admin': ADMIN_PERMISSIONS, 'viewer': VIEWER_PERMISSIONS}
        if role_name not in defaults:
            raise CommandError(
                f'reset only works for system roles (admin, viewer). Got: "{role_name}"'
            )

        role = Role.objects.get(name=role_name)
        old  = set(role.permissions or [])
        new  = set(defaults[role_name])
        role.permissions = defaults[role_name]
        role.save()

        added   = sorted(new - old)
        removed = sorted(old - new)
        self.stdout.write(self.style.SUCCESS(f'Role "{role_name}" reset to defaults.'))
        if added:   self.stdout.write(f'  added:   {added}')
        if removed: self.stdout.write(f'  removed: {removed}')
        if not added and not removed:
            self.stdout.write('  No changes needed — was already at defaults.')
