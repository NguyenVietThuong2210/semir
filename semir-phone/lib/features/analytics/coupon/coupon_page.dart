import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../shared/widgets/dark_tabs.dart';
import '../../../shared/widgets/data_table_widget.dart';
import '../../../shared/widgets/date_filter_bar.dart';
import '../../../shared/widgets/error_banner.dart';
import '../../../shared/widgets/kpi_card.dart';
import '../../../shared/widgets/loading_overlay.dart';
import '../../../shared/widgets/pull_to_refresh.dart';
import '../../../shared/widgets/section_header.dart';
import '../../../shared/widgets/shop_group_filter.dart';
import '../../../shared/models/analytics_models.dart';
import 'coupon_provider.dart';
import 'coupon_service.dart';

// Tab order matches backend available_tabs: ['by_shop', 'detail', 'duplicates']
const _kTabKeys = ['by_shop', 'detail', 'duplicates'];
const _kTabLabels = ['By Store', 'Detail', 'Duplicates'];

class CouponPage extends ConsumerStatefulWidget {
  const CouponPage({super.key});

  @override
  ConsumerState<CouponPage> createState() => _CouponPageState();
}

class _CouponPageState extends ConsumerState<CouponPage> {
  int _selectedTab = 0;
  final _prefixController = TextEditingController();

  @override
  void dispose() {
    _prefixController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final analyticsAsync = ref.watch(couponAnalyticsProvider);
    final filter = ref.watch(couponFilterProvider);
    final shopGroup = ref.watch(couponShopGroupProvider);
    final prefix = ref.watch(couponPrefixProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Coupon'),
        actions: [
          IconButton(
            icon: const Icon(Icons.bar_chart),
            tooltip: 'Charts',
            onPressed: () => context.go('/coupon/charts'),
          ),
        ],
      ),
      body: Stack(
        children: [
          PullToRefresh(
            onRefresh: () =>
                ref.read(couponAnalyticsProvider.notifier).refresh(),
            child: analyticsAsync.when(
              loading: () => const SizedBox.expand(),
              error: (e, _) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: ErrorBanner(
                    message: e.toString(),
                    onRetry: () =>
                        ref.read(couponAnalyticsProvider.notifier).refresh(),
                  ),
                ),
              ),
              data: (payload) {
                return ListView(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        children: [
                          DateFilterBar(
                            initialFilter: filter,
                            onFilterChanged: (f) =>
                                ref.read(couponFilterProvider.notifier).state =
                                    f,
                          ),
                          const SizedBox(height: 8),
                          ShopGroupFilter(
                            value: shopGroup,
                            onChanged: (s) => ref
                                .read(couponShopGroupProvider.notifier)
                                .state = s ?? 'All',
                          ),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _prefixController,
                            decoration: const InputDecoration(
                              labelText: 'Filter by Coupon ID prefix',
                              prefixIcon: Icon(Icons.search),
                            ),
                            onSubmitted: (v) => ref
                                .read(couponPrefixProvider.notifier)
                                .state = v.trim(),
                          ),
                        ],
                      ),
                    ),
                    if (payload == null)
                      const Padding(
                        padding: EdgeInsets.all(32),
                        child: Center(child: Text('No data')),
                      ),
                    if (payload != null) ...[
                      const SectionHeader(title: 'All-Time Overview'),
                      _KpiRow(
                          kpis: payload.allTimeKpis,
                          variant: KpiVariant.allTime),
                      const SectionHeader(title: 'Selected Period'),
                      _KpiRow(
                          kpis: payload.periodKpis,
                          variant: KpiVariant.period),
                      const SectionHeader(title: 'Detailed Analysis'),
                      DarkTabs(
                        tabs: _kTabLabels,
                        selectedIndex: _selectedTab,
                        onTabSelected: (i) => setState(() => _selectedTab = i),
                      ),
                      _LazyTabContent(
                        tabIndex: _selectedTab,
                        payload: payload,
                        filter: filter,
                        shopGroup: shopGroup,
                        prefix: prefix,
                      ),
                    ],
                    const SizedBox(height: 32),
                  ],
                );
              },
            ),
          ),
          if (analyticsAsync.isLoading) const LoadingOverlay(),
        ],
      ),
    );
  }
}

/// Tab 0 (by_shop) uses the data already in the initial payload.
/// Tabs 1 (detail) and 2 (duplicates) are fetched lazily via couponTabProvider.
class _LazyTabContent extends ConsumerWidget {
  const _LazyTabContent({
    required this.tabIndex,
    required this.payload,
    required this.filter,
    required this.shopGroup,
    required this.prefix,
  });

  final int tabIndex;
  final CouponAnalyticsPayload payload;
  final DateRangeFilter filter;
  final String shopGroup;
  final String prefix;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Tab 0 (by_shop) is always in the initial payload — look up by key, not index
    if (tabIndex == 0) {
      final matches = payload.tabs.where((t) => t.tabKey == 'by_shop');
      return _tabContent(matches.isNotEmpty ? matches.first : null);
    }

    if (tabIndex >= _kTabKeys.length) return const SizedBox.shrink();

    final tabKey = _kTabKeys[tabIndex];
    final key = (
      tab: tabKey,
      dateFrom: filter.fromParam ?? '',
      dateTo: filter.toParam ?? '',
      shopGroup: shopGroup,
      prefix: prefix,
    );
    final tabAsync = ref.watch(couponTabProvider(key));

    return tabAsync.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: 48),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.all(16),
        child: Text('Failed to load: $e',
            style: const TextStyle(color: Colors.red)),
      ),
      data: (tab) => _tabContent(tab),
    );
  }

  Widget _tabContent(TableTab? tab) {
    if (tab == null) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: Text('No data for this tab')),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(12),
      child: SizedBox(
        height: 400,
        child: DataTableWidget(headers: tab.headers, rows: tab.rows),
      ),
    );
  }
}

class _KpiRow extends StatelessWidget {
  const _KpiRow({required this.kpis, required this.variant});
  final List<KpiItem> kpis;
  final KpiVariant variant;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: kpis
            .map((k) => SizedBox(
                  width: (MediaQuery.of(context).size.width - 40) / 2,
                  child: KpiCard(label: k.label, value: k.value, variant: variant),
                ))
            .toList(),
      ),
    );
  }
}
