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
import 'sales_provider.dart';
import 'sales_service.dart';

class SalesPage extends ConsumerStatefulWidget {
  const SalesPage({super.key});

  @override
  ConsumerState<SalesPage> createState() => _SalesPageState();
}

class _SalesPageState extends ConsumerState<SalesPage> {
  int _selectedTab = 0;

  static const _tabLabels = [
    'By Grade',
    'By Season',
    'By Month',
    'By Week',
    'By Store',
  ];

  @override
  Widget build(BuildContext context) {
    final analyticsAsync = ref.watch(salesAnalyticsProvider);
    final currentFilter = ref.watch(salesFilterProvider);
    final currentShop = ref.watch(salesShopGroupProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Sales Analytics')),
      body: Stack(
        children: [
          PullToRefresh(
            onRefresh: () => ref.read(salesAnalyticsProvider.notifier).refresh(),
            child: analyticsAsync.when(
              loading: () => const SizedBox.expand(),
              error: (e, _) => _ErrorView(
                message: e.toString(),
                onRetry: () =>
                    ref.read(salesAnalyticsProvider.notifier).refresh(),
              ),
              data: (payload) {
                if (payload == null) {
                  return const Center(child: Text('No data'));
                }
                return _DataView(
                  payload: payload,
                  selectedTab: _selectedTab,
                  onTabSelected: (i) => setState(() => _selectedTab = i),
                  filter: currentFilter,
                  shopGroup: currentShop,
                  onFilterChanged: (f) =>
                      ref.read(salesFilterProvider.notifier).state = f,
                  onShopChanged: (s) =>
                      ref.read(salesShopGroupProvider.notifier).state =
                          s ?? 'All',
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

class _DataView extends StatelessWidget {
  const _DataView({
    required this.payload,
    required this.selectedTab,
    required this.onTabSelected,
    required this.filter,
    required this.shopGroup,
    required this.onFilterChanged,
    required this.onShopChanged,
  });

  final SalesAnalyticsPayload payload;
  final int selectedTab;
  final ValueChanged<int> onTabSelected;
  final DateRangeFilter filter;
  final String shopGroup;
  final ValueChanged<DateRangeFilter> onFilterChanged;
  final ValueChanged<String?> onShopChanged;

  @override
  Widget build(BuildContext context) {
    final tabs = payload.tabs;
    final currentTab = selectedTab < tabs.length ? tabs[selectedTab] : null;

    return ListView(
      children: [
        // Filters
        Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            children: [
              DateFilterBar(
                initialFilter: filter,
                onFilterChanged: onFilterChanged,
              ),
              const SizedBox(height: 8),
              ShopGroupFilter(
                value: shopGroup,
                onChanged: onShopChanged,
              ),
            ],
          ),
        ),

        // All-Time KPIs
        const SectionHeader(title: 'All-Time Overview'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: _KpiGrid(
            kpis: payload.allTimeKpis,
            variant: KpiVariant.allTime,
          ),
        ),

        // Period KPIs
        const SectionHeader(title: 'Selected Period'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: _KpiGrid(
            kpis: payload.periodKpis,
            variant: KpiVariant.period,
          ),
        ),

        // Tab-switched tables
        const SectionHeader(title: 'Detailed Analysis'),
        DarkTabs(
          tabs: _SalesPageState._tabLabels,
          selectedIndex: selectedTab,
          onTabSelected: onTabSelected,
        ),
        if (currentTab != null)
          Padding(
            padding: const EdgeInsets.all(12),
            child: SizedBox(
              height: 400,
              child: DataTableWidget(
                headers: currentTab.headers,
                rows: currentTab.rows,
              ),
            ),
          ),

        const SizedBox(height: 32),
      ],
    );
  }
}

class _KpiGrid extends StatelessWidget {
  const _KpiGrid({required this.kpis, required this.variant});
  final List<KpiItem> kpis;
  final KpiVariant variant;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: kpis
          .map((k) => SizedBox(
                width: (MediaQuery.of(context).size.width - 40) / 2,
                child: KpiCard(
                  label: k.label,
                  value: k.value,
                  variant: variant,
                ),
              ))
          .toList(),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: ErrorBanner(message: message, onRetry: onRetry),
      ),
    );
  }
}
