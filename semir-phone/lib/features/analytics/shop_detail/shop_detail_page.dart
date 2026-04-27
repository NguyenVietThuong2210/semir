import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/widgets/data_table_widget.dart';
import '../../../shared/widgets/date_filter_bar.dart';
import '../../../shared/widgets/error_banner.dart';
import '../../../shared/widgets/kpi_card.dart';
import '../../../shared/widgets/loading_overlay.dart';
import '../../../shared/widgets/pull_to_refresh.dart';
import '../../../shared/widgets/section_header.dart';
import '../../../shared/models/analytics_models.dart';
import 'shop_detail_provider.dart';
import 'shop_detail_service.dart';

class ShopDetailPage extends ConsumerWidget {
  const ShopDetailPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final shopsAsync = ref.watch(shopsListProvider);
    final selectedShop = ref.watch(selectedShopProvider);
    final filter = ref.watch(shopDetailFilterProvider);
    final detailAsync = ref.watch(shopDetailProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Store Detail')),
      body: Stack(
        children: [
          PullToRefresh(
            onRefresh: () =>
                ref.read(shopDetailProvider.notifier).refresh(),
            child: ListView(
              children: [
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      // Shop dropdown
                      shopsAsync.when(
                        loading: () => const LinearProgressIndicator(),
                        error: (e, _) => Text('Error loading stores: $e'),
                        data: (shops) {
                          if (shops.isEmpty) {
                            return const Text('No stores available');
                          }
                          return DropdownButtonFormField<String>(
                            initialValue: selectedShop,
                            hint: const Text('Select a store'),
                            items: shops
                                .map((s) => DropdownMenuItem(
                                    value: s, child: Text(s)))
                                .toList(),
                            onChanged: (v) => ref
                                .read(selectedShopProvider.notifier)
                                .state = v,
                            decoration: const InputDecoration(
                              labelText: 'Store',
                            ),
                          );
                        },
                      ),
                      const SizedBox(height: 8),
                      DateFilterBar(
                        initialFilter: filter,
                        onFilterChanged: (f) =>
                            ref.read(shopDetailFilterProvider.notifier).state =
                                f,
                      ),
                    ],
                  ),
                ),
                if (selectedShop == null)
                  const Center(
                    child: Padding(
                      padding: EdgeInsets.all(32),
                      child: Text('Please select a store to view details'),
                    ),
                  )
                else
                  detailAsync.when(
                    loading: () => const SizedBox.shrink(),
                    error: (e, _) => Padding(
                      padding: const EdgeInsets.all(24),
                      child: ErrorBanner(
                        message: e.toString(),
                        onRetry: () =>
                            ref.read(shopDetailProvider.notifier).refresh(),
                      ),
                    ),
                    data: (payload) {
                      if (payload == null) return const SizedBox.shrink();
                      return _DetailSections(payload: payload);
                    },
                  ),
                const SizedBox(height: 32),
              ],
            ),
          ),
          if (detailAsync.isLoading) const LoadingOverlay(),
        ],
      ),
    );
  }
}

class _DetailSections extends StatelessWidget {
  const _DetailSections({required this.payload});
  final ShopDetailPayload payload;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _Section(
          title: 'Sales',
          allTimeKpis: payload.salesAllTimeKpis,
          periodKpis: payload.salesPeriodKpis,
          tabs: payload.salesTabs,
        ),
        const SizedBox(height: 12),
        _Section(
          title: 'Customers',
          allTimeKpis: payload.customerKpis,
          periodKpis: const [],
          tabs: payload.customerTabs,
        ),
        const SizedBox(height: 12),
        _Section(
          title: 'Coupon',
          allTimeKpis: payload.couponKpis,
          periodKpis: const [],
          tabs: payload.couponTabs,
        ),
      ],
    );
  }
}

class _Section extends StatefulWidget {
  const _Section({
    required this.title,
    required this.allTimeKpis,
    required this.periodKpis,
    required this.tabs,
  });

  final String title;
  final List<KpiItem> allTimeKpis;
  final List<KpiItem> periodKpis;
  final List<TableTab> tabs;

  @override
  State<_Section> createState() => _SectionState();
}

class _SectionState extends State<_Section> {
  int _selectedTab = 0;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: AppColors.primary, width: 4),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHeader(title: widget.title),
          if (widget.allTimeKpis.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: widget.allTimeKpis
                    .map((k) => SizedBox(
                          width:
                              (MediaQuery.of(context).size.width - 40) / 2,
                          child: KpiCard(
                            label: k.label,
                            value: k.value,
                            variant: KpiVariant.allTime,
                          ),
                        ))
                    .toList(),
              ),
            ),
          if (widget.periodKpis.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: widget.periodKpis
                    .map((k) => SizedBox(
                          width:
                              (MediaQuery.of(context).size.width - 40) / 2,
                          child: KpiCard(
                            label: k.label,
                            value: k.value,
                            variant: KpiVariant.period,
                          ),
                        ))
                    .toList(),
              ),
            ),
          if (widget.tabs.isNotEmpty) ...[
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: List.generate(
                  widget.tabs.length,
                  (i) => TextButton(
                    onPressed: () => setState(() => _selectedTab = i),
                    child: Text(
                      widget.tabs[i].label,
                      style: TextStyle(
                        color: _selectedTab == i
                            ? AppColors.primary
                            : AppColors.textMuted,
                        fontWeight: _selectedTab == i
                            ? FontWeight.bold
                            : FontWeight.normal,
                      ),
                    ),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: SizedBox(
                height: 250,
                child: DataTableWidget(
                  headers: widget.tabs[_selectedTab].headers,
                  rows: widget.tabs[_selectedTab].rows,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
