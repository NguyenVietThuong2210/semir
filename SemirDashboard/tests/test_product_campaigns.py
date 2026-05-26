"""
tests/test_product_campaigns.py — Unit tests for ProductCampaign analytics.

Tests:
  1. _lookup_campaign — prefix matching, case insensitivity, empty inputs
  2. _derive_campaign_rows — aggregation, pre-computed campaign reuse
  3. _build_campaign_groups — hierarchy correctness
  4. manage_product_campaigns view — GET list, POST create/update/delete

Run:
  cd SemirDashboard && python manage.py test tests.test_product_campaigns -v 2
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from App.models import ProductCampaign
from App.analytics.product_analytics import (
    _lookup_campaign,
    _derive_campaign_rows,
    _build_campaign_groups,
)

from tests.base import SnapshotTestCase


# ── helpers ────────────────────────────────────────────────────────────────────

def _campaigns(*specs):
    """Build campaign list: specs = (name, [prefix, ...]) tuples."""
    return [{'name': name, 'prefixes': [p.upper() for p in prefixes]}
            for name, prefixes in specs]


def _row(code, l1='', l2='', l3='', qty=1, amount=100.0, settlement=80.0,
         tag_amount=100.0, lines=1, campaign=None):
    r = {
        'product_code': code,
        'category_l1': l1,
        'category_l2': l2,
        'category_l3': l3,
        'qty': qty,
        'amount': float(amount),
        'settlement': float(settlement),
        'tag_amount': float(tag_amount),
        'lines': lines,
    }
    if campaign is not None:
        r['campaign'] = campaign
    return r


# ── _lookup_campaign ────────────────────────────────────────────────────────────

class LookupCampaignTest(TestCase):

    def setUp(self):
        self.campaigns = _campaigns(
            ('Summer Sale', ['SS', 'SU']),
            ('Winter Collection', ['WC', 'WIN']),
        )

    def test_exact_prefix_match(self):
        self.assertEqual(_lookup_campaign('SS001', self.campaigns), 'Summer Sale')

    def test_longer_prefix_match(self):
        self.assertEqual(_lookup_campaign('WIN2025-ABC', self.campaigns), 'Winter Collection')

    def test_case_insensitive(self):
        self.assertEqual(_lookup_campaign('ss001', self.campaigns), 'Summer Sale')
        self.assertEqual(_lookup_campaign('Ss001', self.campaigns), 'Summer Sale')

    def test_no_match_returns_empty(self):
        self.assertEqual(_lookup_campaign('XYZ999', self.campaigns), '')

    def test_empty_code_returns_empty(self):
        self.assertEqual(_lookup_campaign('', self.campaigns), '')
        self.assertEqual(_lookup_campaign(None, self.campaigns), '')

    def test_empty_campaigns_returns_empty(self):
        self.assertEqual(_lookup_campaign('SS001', []), '')

    def test_first_campaign_wins_on_ambiguity(self):
        campaigns = _campaigns(('A', ['SS']), ('B', ['SS']))
        self.assertEqual(_lookup_campaign('SS001', campaigns), 'A')

    def test_partial_prefix_no_match(self):
        # 'S' alone should NOT match 'SS001' unless prefix is 'S'
        campaigns = _campaigns(('X', ['SSS']))
        self.assertEqual(_lookup_campaign('SS001', campaigns), '')


# ── _derive_campaign_rows ───────────────────────────────────────────────────────

class DeriveCampaignRowsTest(TestCase):

    def setUp(self):
        self.campaigns = _campaigns(('Alpha', ['AA']), ('Beta', ['BB']))

    def test_aggregates_by_campaign_l1_l2_l3(self):
        rows = [
            _row('AA001', l1='Tops', l2='T-Shirts', l3='Slim', qty=2, amount=200.0),
            _row('AA002', l1='Tops', l2='T-Shirts', l3='Slim', qty=3, amount=300.0),
        ]
        result = _derive_campaign_rows(rows, self.campaigns)
        self.assertEqual(len(result), 1)
        r = result[0]
        self.assertEqual(r['campaign'], 'Alpha')
        self.assertEqual(r['qty'], 5)
        self.assertAlmostEqual(r['amount'], 500.0)

    def test_different_categories_stay_separate(self):
        rows = [
            _row('AA001', l1='Tops', l2='T-Shirts', l3='Slim'),
            _row('AA002', l1='Bottoms', l2='Jeans', l3=''),
        ]
        result = _derive_campaign_rows(rows, self.campaigns)
        self.assertEqual(len(result), 2)

    def test_unmatched_goes_to_empty_campaign(self):
        rows = [_row('ZZ999')]
        result = _derive_campaign_rows(rows, self.campaigns)
        self.assertEqual(result[0]['campaign'], '')

    def test_two_campaigns_kept_separate(self):
        rows = [_row('AA001'), _row('BB001')]
        result = _derive_campaign_rows(rows, self.campaigns)
        camps = {r['campaign'] for r in result}
        self.assertIn('Alpha', camps)
        self.assertIn('Beta', camps)

    def test_precomputed_campaign_is_reused(self):
        """If row already has 'campaign' set, _lookup_campaign must not be called again."""
        rows = [_row('ZZ999', campaign='Pre-Set')]
        result = _derive_campaign_rows(rows, self.campaigns)
        self.assertEqual(result[0]['campaign'], 'Pre-Set')

    def test_empty_rows_returns_empty(self):
        self.assertEqual(_derive_campaign_rows([], self.campaigns), [])


# ── _build_campaign_groups ──────────────────────────────────────────────────────

class BuildCampaignGroupsTest(TestCase):

    def _make_rows(self):
        return [
            {'campaign': 'Alpha', 'category_l1': 'Tops', 'category_l2': 'T-Shirts',
             'category_l3': 'Slim', 'qty': 5, 'amount': 500.0,
             'settlement': 400.0, 'tag_amount': 500.0, 'lines': 3},
            {'campaign': 'Alpha', 'category_l1': 'Tops', 'category_l2': 'Polos',
             'category_l3': '', 'qty': 2, 'amount': 200.0,
             'settlement': 160.0, 'tag_amount': 200.0, 'lines': 1},
            {'campaign': 'Beta', 'category_l1': 'Bottoms', 'category_l2': 'Jeans',
             'category_l3': 'Slim', 'qty': 10, 'amount': 1000.0,
             'settlement': 800.0, 'tag_amount': 1000.0, 'lines': 5},
        ]

    def test_structure_keys(self):
        result = _build_campaign_groups(self._make_rows())
        self.assertGreater(len(result), 0)
        g = result[0]
        self.assertIn('campaign', g)
        self.assertIn('l1_groups', g)
        self.assertIn('subtotal', g)

    def test_sorted_by_amount_desc(self):
        result = _build_campaign_groups(self._make_rows())
        amounts = [g['subtotal']['amount'] for g in result]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    def test_subtotals_correct(self):
        result = _build_campaign_groups(self._make_rows())
        by_camp = {g['campaign']: g for g in result}
        self.assertAlmostEqual(by_camp['Alpha']['subtotal']['amount'], 700.0)
        self.assertAlmostEqual(by_camp['Beta']['subtotal']['amount'], 1000.0)

    def test_empty_campaign_included(self):
        rows = [{'campaign': '', 'category_l1': 'X', 'category_l2': '', 'category_l3': '',
                 'qty': 1, 'amount': 50.0, 'settlement': 40.0, 'tag_amount': 50.0, 'lines': 1}]
        result = _build_campaign_groups(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['campaign'], '')

    def test_empty_input_returns_empty(self):
        self.assertEqual(_build_campaign_groups([]), [])


# ── manage_product_campaigns view ──────────────────────────────────────────────

class ManageProductCampaignsViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='camptest', password='pass', email='camptest@test.com'
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.url = reverse('manage_product_campaigns')

    def _post(self, payload):
        return self.client.post(
            self.url, data=json.dumps(payload),
            content_type='application/json'
        )

    # GET ──────────────────────────────────────────────────────────────────────

    def test_get_returns_200_and_campaigns_list(self):
        ProductCampaign.objects.create(name='TestCamp', prefix='TC,TD')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('campaigns', data)
        names = [c['name'] for c in data['campaigns']]
        self.assertIn('TestCamp', names)

    def test_get_includes_prefix_list(self):
        ProductCampaign.objects.create(name='PrefTest', prefix='AA,BB,CC')
        resp = self.client.get(self.url)
        data = json.loads(resp.content)
        camp = next(c for c in data['campaigns'] if c['name'] == 'PrefTest')
        self.assertEqual(sorted(camp['prefix_list']), ['AA', 'BB', 'CC'])

    # CREATE ───────────────────────────────────────────────────────────────────

    def test_create_success(self):
        resp = self._post({'action': 'create', 'name': 'New Camp', 'prefix': 'NC,ND'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data.get('ok'))
        self.assertTrue(ProductCampaign.objects.filter(name='New Camp').exists())

    def test_create_deduplicates_and_uppercases_prefix(self):
        resp = self._post({'action': 'create', 'name': 'DupPfx', 'prefix': 'aa,AA,bb'})
        self.assertEqual(resp.status_code, 200)
        c = ProductCampaign.objects.get(name='DupPfx')
        self.assertEqual(set(c.prefix.split(',')), {'AA', 'BB'})

    def test_create_missing_name_returns_400(self):
        resp = self._post({'action': 'create', 'name': '', 'prefix': 'AB'})
        self.assertEqual(resp.status_code, 400)

    def test_create_missing_prefix_returns_400(self):
        resp = self._post({'action': 'create', 'name': 'NoPfx', 'prefix': ''})
        self.assertEqual(resp.status_code, 400)

    def test_create_duplicate_name_returns_400(self):
        ProductCampaign.objects.create(name='Dup', prefix='DU')
        resp = self._post({'action': 'create', 'name': 'Dup', 'prefix': 'DX'})
        self.assertEqual(resp.status_code, 400)

    # UPDATE ───────────────────────────────────────────────────────────────────

    def test_update_success(self):
        c = ProductCampaign.objects.create(name='OldName', prefix='ON')
        resp = self._post({'action': 'update', 'id': c.pk, 'name': 'NewName', 'prefix': 'NN'})
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.name, 'NewName')
        self.assertEqual(c.prefix, 'NN')

    def test_update_not_found_returns_404(self):
        resp = self._post({'action': 'update', 'id': 99999, 'name': 'X', 'prefix': 'XX'})
        self.assertEqual(resp.status_code, 404)

    def test_update_duplicate_name_returns_400(self):
        c1 = ProductCampaign.objects.create(name='Camp1', prefix='C1')
        ProductCampaign.objects.create(name='Camp2', prefix='C2')
        resp = self._post({'action': 'update', 'id': c1.pk, 'name': 'Camp2', 'prefix': 'C1'})
        self.assertEqual(resp.status_code, 400)

    # DELETE ───────────────────────────────────────────────────────────────────

    def test_delete_success(self):
        c = ProductCampaign.objects.create(name='ToDelete', prefix='TD')
        resp = self._post({'action': 'delete', 'id': c.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ProductCampaign.objects.filter(pk=c.pk).exists())

    def test_delete_not_found_returns_404(self):
        resp = self._post({'action': 'delete', 'id': 99999})
        self.assertEqual(resp.status_code, 404)

    def test_delete_missing_id_returns_400(self):
        resp = self._post({'action': 'delete'})
        self.assertEqual(resp.status_code, 400)

    # AUTH / permissions ───────────────────────────────────────────────────────

    def test_unauthenticated_redirects(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, [302, 403])

    def test_user_without_perm_redirects(self):
        from django.contrib.auth.models import User
        plain = User.objects.create_user('noperm', password='x')
        self.client.force_login(plain)
        resp = self.client.get(self.url, follow=True)
        self.assertEqual(resp.status_code, 200)
        messages = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('permission' in m.lower() for m in messages))

    # edge cases ───────────────────────────────────────────────────────────────

    def test_unknown_action_returns_400(self):
        resp = self._post({'action': 'explode'})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_json_returns_400(self):
        resp = self.client.post(
            self.url, data='not json', content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
