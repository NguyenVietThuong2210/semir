"""Integration tests for perm sync command — permission rename migration."""

from django.test import TestCase
from django.contrib.auth.models import User

from App.models import Role
from App.management.commands.perm import Command
from App.permissions import ADMIN_PERMISSIONS, VIEWER_PERMISSIONS, PERMISSION_DEFS


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

    def test_admin_role_gets_all_20_new_codenames(self):
        """Admin role is overwritten with exactly all 20 new codenames."""
        self._sync()
        admin = Role.objects.get(name='admin')
        self.assertEqual(sorted(admin.permissions), sorted(ADMIN_PERMISSIONS))
        self.assertEqual(len(admin.permissions), 20)

    def test_viewer_role_gets_sales_view(self):
        """Viewer role is overwritten with exactly ['sales.view']."""
        self._sync()
        viewer = Role.objects.get(name='viewer')
        self.assertEqual(viewer.permissions, ['sales.view'])

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

    def test_all_20_renames_are_complete(self):
        """All 20 old codenames are correctly renamed via a single custom role."""
        old_codenames = [
            'page_analytics', 'page_chart', 'download_analytics', 'download_chart_excel',
            'page_coupons', 'page_coupon_chart', 'download_coupons', 'download_coupon_chart_excel',
            'manage_campaigns', 'page_cnv_comparison', 'page_customer_chart', 'page_cnv_sync',
            'download_cnv', 'download_customer_chart_excel', 'page_customer_detail',
            'page_shop_detail', 'download_shop_detail', 'page_upload', 'page_formulas',
            'manage_users',
        ]
        new_codenames = [p[0] for p in PERMISSION_DEFS]

        role = Role.objects.create(
            name='test_all_renames',
            permissions=old_codenames,
            is_system=False,
        )
        self._sync()
        role.refresh_from_db()

        for new_code in new_codenames:
            self.assertIn(new_code, role.permissions,
                          f"Expected new codename '{new_code}' after sync")
        for old_code in old_codenames:
            self.assertNotIn(old_code, role.permissions,
                             f"Old codename '{old_code}' should be gone after sync")
