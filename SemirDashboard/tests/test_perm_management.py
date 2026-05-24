"""Integration tests for perm sync command — permission rename migration."""

from django.test import TestCase
from django.contrib.auth.models import User

from App.models import Role
from App.management.commands.perm import Command
from App.permissions import ADMIN_PERMISSIONS, VIEWER_PERMISSIONS, PERMISSION_DEFS, ALL_PERMISSIONS


class PermSyncMigrationTest(TestCase):
    """Test that perm sync correctly renames old codenames to new ones."""

    def setUp(self):
        self.cmd = Command()
        self.cmd.stdout = type('FakeIO', (), {'write': lambda self, x: None})()
        self.cmd.style = type('FakeStyle', (), {
            'MIGRATE_HEADING': lambda self, x: x,
            'SUCCESS': lambda self, x: x,
            'WARNING': lambda self, x: x,
            'ERROR': lambda self, x: x,
        })()
        Role.objects.filter(name__in=['admin', 'viewer']).delete()

    def _sync(self):
        self.cmd._sync()

    def test_custom_role_old_codenames_are_renamed(self):
        """Custom role with old codenames gets new codenames after sync."""
        role = Role.objects.create(
            name='test_custom',
            permissions=['page_analytics', 'download_coupons'],
            is_system=False,
        )
        self._sync()
        role.refresh_from_db()
        self.assertIn('sales.view', role.permissions)
        self.assertIn('coupons.export', role.permissions)
        self.assertNotIn('page_analytics', role.permissions)
        self.assertNotIn('download_coupons', role.permissions)

    def test_admin_role_gets_all_new_codenames(self):
        """Admin role is overwritten with exactly all current codenames."""
        self._sync()
        admin = Role.objects.get(name='admin')
        self.assertEqual(sorted(admin.permissions), sorted(ADMIN_PERMISSIONS))
        self.assertEqual(len(admin.permissions), len(ALL_PERMISSIONS))

    def test_viewer_role_gets_viewer_permissions(self):
        """Viewer role is overwritten with exactly VIEWER_PERMISSIONS."""
        self._sync()
        viewer = Role.objects.get(name='viewer')
        self.assertEqual(sorted(viewer.permissions), sorted(VIEWER_PERMISSIONS))

    def test_perm_sync_is_idempotent(self):
        """Running perm sync twice produces the same result as running it once."""
        role = Role.objects.create(
            name='test_idempotent',
            permissions=['page_analytics', 'manage_users'],
            is_system=False,
        )
        self._sync()
        role.refresh_from_db()
        after_first = list(role.permissions)

        self._sync()
        role.refresh_from_db()
        after_second = list(role.permissions)

        self.assertEqual(sorted(after_first), sorted(after_second))

    def test_all_renames_are_complete(self):
        """All old codenames are correctly renamed; new perms without old mappings are not added."""
        old_codenames = [
            'page_analytics', 'page_chart', 'download_analytics', 'download_chart_excel',
            'page_coupons', 'page_coupon_chart', 'download_coupons', 'download_coupon_chart_excel',
            'manage_campaigns', 'page_cnv_comparison', 'page_customer_chart', 'page_cnv_sync',
            'download_cnv', 'download_customer_chart_excel', 'page_customer_detail',
            'page_shop_detail', 'download_shop_detail', 'page_upload', 'page_formulas',
            'manage_users',
        ]
        # Only check FINAL codes reachable via renames. PERM_RENAMES has intermediate
        # values (e.g. page_cnv_comparison) — filter to only those in ALL_PERMISSIONS.
        # New perms without any old code (products.view etc.) won't be added by sync.
        mapped_new_codes: set = set()
        for new_codes in Command.PERM_RENAMES.values():
            for nc in new_codes:
                if nc in ALL_PERMISSIONS:
                    mapped_new_codes.add(nc)

        role = Role.objects.create(
            name='test_all_renames',
            permissions=old_codenames,
            is_system=False,
        )
        self._sync()
        role.refresh_from_db()

        for new_code in mapped_new_codes:
            self.assertIn(new_code, role.permissions,
                          f"Expected renamed codename '{new_code}' after sync")
        for old_code in old_codenames:
            self.assertNotIn(old_code, role.permissions,
                             f"Old codename '{old_code}' should be gone after sync")
