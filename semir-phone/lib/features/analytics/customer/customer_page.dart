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
import '../../../shared/models/analytics_models.dart';
import 'customer_provider.dart';

class CustomerPage extends ConsumerStatefulWidget {
  const CustomerPage({super.key});

  @override
  ConsumerState<CustomerPage> createState() => _CustomerPageState();
}

class _CustomerPageState extends ConsumerState<CustomerPage> {
  int _breakdownTab = 0;
  int _comparisonTab = 0;

  // Order matches API registration_breakdown keys: by_shop, by_season, by_month, by_week, by_grade
  static const _breakdownLabels = ['By Store', 'By Season', 'By Month', 'By Week', 'By Grade'];
  static const _comparisonLabels = ['POS Only', 'CNV Only', 'Both', 'Zalo'];

  @override
  Widget build(BuildContext context) {
    final analyticsAsync = ref.watch(customerAnalyticsProvider);
    final filter = ref.watch(customerFilterProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Customers'),
        actions: [
          IconButton(
            icon: const Icon(Icons.bar_chart),
            tooltip: 'Charts',
            onPressed: () => context.go('/customer/charts'),
          ),
        ],
      ),
      body: Stack(
        children: [
          PullToRefresh(
            onRefresh: () =>
                ref.read(customerAnalyticsProvider.notifier).refresh(),
            child: analyticsAsync.when(
              loading: () => const SizedBox.expand(),
              error: (e, _) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: ErrorBanner(
                    message: e.toString(),
                    onRetry: () =>
                        ref.read(customerAnalyticsProvider.notifier).refresh(),
                  ),
                ),
              ),
              data: (payload) {
                if (payload == null) {
                  return const Center(child: Text('No data'));
                }
                return ListView(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: DateFilterBar(
                        initialFilter: filter,
                        onFilterChanged: (f) =>
                            ref.read(customerFilterProvider.notifier).state = f,
                      ),
                    ),
                    const SectionHeader(title: 'All-Time Overview'),
                    _KpiRow(kpis: payload.allTimeKpis, variant: KpiVariant.allTime),
                    const SectionHeader(title: 'Selected Period'),
                    _KpiRow(kpis: payload.periodKpis, variant: KpiVariant.period),
                    const SectionHeader(title: 'Registration Breakdown'),
                    DarkTabs(
                      tabs: _breakdownLabels,
                      selectedIndex: _breakdownTab,
                      onTabSelected: (i) => setState(() => _breakdownTab = i),
                    ),
                    if (_breakdownTab < payload.registrationBreakdownTabs.length)
                      Padding(
                        padding: const EdgeInsets.all(12),
                        child: SizedBox(
                          height: 300,
                          child: DataTableWidget(
                            headers: payload
                                .registrationBreakdownTabs[_breakdownTab].headers,
                            rows: payload
                                .registrationBreakdownTabs[_breakdownTab].rows,
                          ),
                        ),
                      ),
                    const SectionHeader(title: 'Customer Comparison'),
                    DarkTabs(
                      tabs: _comparisonLabels,
                      selectedIndex: _comparisonTab,
                      onTabSelected: (i) => setState(() => _comparisonTab = i),
                    ),
                    if (_comparisonTab < payload.comparisonTabs.length)
                      Padding(
                        padding: const EdgeInsets.all(12),
                        child: SizedBox(
                          height: 300,
                          child: DataTableWidget(
                            headers: payload.comparisonTabs[_comparisonTab].headers,
                            rows: payload.comparisonTabs[_comparisonTab].rows,
                          ),
                        ),
                      ),
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
