import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/auth/auth_provider.dart';
import '../../core/auth/auth_service.dart';
import '../../core/theme/app_colors.dart';
import 'nav_card.dart';

class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sessionAsync = ref.watch(authProvider);

    return sessionAsync.when(
      loading: () => const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(body: Center(child: Text('Error: $e'))),
      data: (session) {
        final cards = _buildCards(session);
        return Scaffold(
          appBar: AppBar(
            title: const Text('S&B Dashboard'),
            actions: [
              IconButton(
                icon: const Icon(Icons.logout_outlined),
                tooltip: 'Sign Out',
                onPressed: () async {
                  await ref.read(authProvider.notifier).logout();
                  if (context.mounted) context.go('/login');
                },
              ),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 32),
            children: [
              if (session != null) _GreetingBar(username: session.username),
              const SizedBox(height: 16),
              _CardGrid(cards: cards),
            ],
          ),
        );
      },
    );
  }

  List<_CardSpec> _buildCards(UserSession? session) {
    bool can(String perm) => session?.hasPermission(perm) ?? false;

    return [
      _CardSpec(
        title: 'Sales',
        description: 'Analyse sales by store, season, and customer grade',
        icon: Icons.bar_chart_rounded,
        route: '/sales',
        hasAccess: can('sales.view'),
        accent: AppColors.accentBlue,
      ),
      _CardSpec(
        title: 'Customers',
        description: 'CNV stats, membership grades, return rates',
        icon: Icons.people_outline,
        route: '/customer',
        hasAccess: can('customers.view'),
        accent: AppColors.accentGreen,
      ),
      _CardSpec(
        title: 'Coupon',
        description: 'Track voucher usage and promotion campaigns',
        icon: Icons.local_offer_outlined,
        route: '/coupon',
        hasAccess: can('coupons.view'),
        accent: AppColors.accentOrange,
      ),
      _CardSpec(
        title: 'Store Detail',
        description: 'KPIs per store — sales, customers, coupons',
        icon: Icons.store_outlined,
        route: '/shop-detail',
        hasAccess: can('shop_detail.view'),
        accent: AppColors.accentPurple,
      ),
      _CardSpec(
        title: 'Customer Lookup',
        description: 'Search customers by VIP ID or phone number',
        icon: Icons.person_search_outlined,
        route: '/customer-detail',
        hasAccess: can('customer_detail.view'),
        accent: AppColors.accentTeal,
      ),
      _CardSpec(
        title: 'Sales Charts',
        description: 'Visual charts for sales trends and breakdowns',
        icon: Icons.show_chart_rounded,
        route: '/sales/charts',
        hasAccess: can('sales.view'),
        accent: AppColors.accentBlue,
      ),
      _CardSpec(
        title: 'Customer Charts',
        description: 'Visual charts for customer registration and grades',
        icon: Icons.pie_chart_outline_rounded,
        route: '/customer/charts',
        hasAccess: can('customers.view'),
        accent: AppColors.accentGreen,
      ),
      _CardSpec(
        title: 'Coupon Charts',
        description: 'Visual charts for coupon usage and campaigns',
        icon: Icons.donut_small_outlined,
        route: '/coupon/charts',
        hasAccess: can('coupons.view'),
        accent: AppColors.accentOrange,
      ),
    ];
  }
}

class _CardGrid extends StatelessWidget {
  const _CardGrid({required this.cards});
  final List<_CardSpec> cards;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final useTwoColumn = width >= 768;

    if (useTwoColumn) {
      // 2-column grid — no empty slots (FR-012)
      final rows = <Widget>[];
      for (var i = 0; i < cards.length; i += 2) {
        final left = cards[i];
        final right = i + 1 < cards.length ? cards[i + 1] : null;
        rows.add(
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: _card(context, left)),
              const SizedBox(width: 12),
              Expanded(
                child: right != null
                    ? _card(context, right)
                    : const SizedBox.shrink(),
              ),
            ],
          ),
        );
        if (i + 2 < cards.length) rows.add(const SizedBox(height: 12));
      }
      return Column(children: rows);
    }

    // Single column
    return Column(
      children: cards
          .expand((c) => [_card(context, c), const SizedBox(height: 12)])
          .toList()
        ..removeLast(),
    );
  }

  Widget _card(BuildContext context, _CardSpec spec) {
    return NavCard(
      title: spec.title,
      description: spec.description,
      icon: spec.icon,
      hasAccess: spec.hasAccess,
      accentColor: spec.accent,
      onTap: spec.hasAccess ? () => context.go(spec.route) : null,
    );
  }
}

class _CardSpec {
  const _CardSpec({
    required this.title,
    required this.description,
    required this.icon,
    required this.route,
    required this.hasAccess,
    required this.accent,
  });
  final String title;
  final String description;
  final IconData icon;
  final String route;
  final bool hasAccess;
  final Color accent;
}

class _GreetingBar extends StatelessWidget {
  const _GreetingBar({required this.username});
  final String username;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: AppColors.primary.withAlpha(18),
            borderRadius: BorderRadius.circular(10),
          ),
          child: const Icon(Icons.person_outline,
              color: AppColors.primary, size: 20),
        ),
        const SizedBox(width: 10),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Hello, $username',
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: AppColors.textDark,
              ),
            ),
            const Text(
              'Select a feature below',
              style: TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
          ],
        ),
      ],
    );
  }
}
