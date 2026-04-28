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

// Tab order must match backend available_tabs order
const _kTabKeys = ['by_grade', 'by_season', 'by_month', 'by_week', 'by_shop'];
const _kTabLabels = ['By Grade', 'By Season', 'By Month', 'By Week', 'By Store'];

class SalesPage extends ConsumerStatefulWidget {
  const SalesPage({super.key});

  @override
  ConsumerState<SalesPage> createState() => _SalesPageState();
}

class _SalesPageState extends ConsumerState<SalesPage> {
  int _selectedTab = 0;

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
              error: (e, _) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: ErrorBanner(
                    message: e.toString(),
                    onRetry: () =>
                        ref.read(salesAnalyticsProvider.notifier).refresh(),
                  ),
                ),
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

class _DataView extends ConsumerWidget {
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
  Widget build(BuildContext context, WidgetRef ref) {
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
              ShopGroupFilter(value: shopGroup, onChanged: onShopChanged),
            ],
          ),
        ),

        // All-Time KPIs
        const SectionHeader(title: 'All-Time Overview'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: _KpiGrid(kpis: payload.allTimeKpis, variant: KpiVariant.allTime),
        ),

        // Period KPIs
        const SectionHeader(title: 'Selected Period'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: _KpiGrid(kpis: payload.periodKpis, variant: KpiVariant.period),
        ),

        // Lazy-loaded tab tables
        const SectionHeader(title: 'Detailed Analysis'),
        DarkTabs(
          tabs: _kTabLabels,
          selectedIndex: selectedTab,
          onTabSelected: onTabSelected,
        ),
        _LazyTabContent(
          tabIndex: selectedTab,
          payload: payload,
          filter: filter,
          shopGroup: shopGroup,
        ),

        const SizedBox(height: 32),
      ],
    );
  }
}

/// Renders the active tab's table. Tab 0 (by_grade) uses data already in the
/// initial payload; all other tabs are fetched lazily on first selection.
class _LazyTabContent extends ConsumerWidget {
  const _LazyTabContent({
    required this.tabIndex,
    required this.payload,
    required this.filter,
    required this.shopGroup,
  });

  final int tabIndex;
  final SalesAnalyticsPayload payload;
  final DateRangeFilter filter;
  final String shopGroup;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Tab 0 is always present in the initial payload
    if (tabIndex == 0) {
      final gradeTab = payload.tabs.isNotEmpty ? payload.tabs.first : null;
      return _tabContent(gradeTab);
    }

    if (tabIndex >= _kTabKeys.length) return const SizedBox.shrink();

    final tabKey = _kTabKeys[tabIndex];
    final key = (
      tab: tabKey,
      dateFrom: filter.fromParam ?? '',
      dateTo: filter.toParam ?? '',
      shopGroup: shopGroup,
    );
    final tabAsync = ref.watch(salesTabProvider(key));

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
                child: KpiCard(label: k.label, value: k.value, variant: variant),
              ))
          .toList(),
    );
  }
}
