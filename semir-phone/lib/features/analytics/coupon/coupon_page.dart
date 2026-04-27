import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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

class CouponPage extends ConsumerStatefulWidget {
  const CouponPage({super.key});

  @override
  ConsumerState<CouponPage> createState() => _CouponPageState();
}

class _CouponPageState extends ConsumerState<CouponPage> {
  int _selectedTab = 0;
  final _prefixController = TextEditingController();

  static const _tabLabels = ['By Store', 'Detail', 'Duplicates'];

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

    return Scaffold(
      appBar: AppBar(title: const Text('Coupon')),
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
                final tabs = payload?.tabs ?? [];
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
                    if (payload != null) ...[
                      const SectionHeader(title: 'All-Time Overview'),
                      _KpiRow(
                          kpis: payload.allTimeKpis,
                          variant: KpiVariant.allTime),
                      const SectionHeader(title: 'Selected Period'),
                      _KpiRow(
                          kpis: payload.periodKpis, variant: KpiVariant.period),
                      const SectionHeader(title: 'Detailed Analysis'),
                      DarkTabs(
                        tabs: _tabLabels,
                        selectedIndex: _selectedTab,
                        onTabSelected: (i) => setState(() => _selectedTab = i),
                      ),
                      if (_selectedTab < tabs.length)
                        Padding(
                          padding: const EdgeInsets.all(12),
                          child: SizedBox(
                            height: 400,
                            child: DataTableWidget(
                              headers: tabs[_selectedTab].headers,
                              rows: tabs[_selectedTab].rows,
                            ),
                          ),
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
