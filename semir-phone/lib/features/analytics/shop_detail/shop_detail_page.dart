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

const _kSectionLabels = ['Sales', 'Customers', 'Coupon'];

class ShopDetailPage extends ConsumerStatefulWidget {
  const ShopDetailPage({super.key});

  @override
  ConsumerState<ShopDetailPage> createState() => _ShopDetailPageState();
}

class _ShopDetailPageState extends ConsumerState<ShopDetailPage> {
  int _section = 0;

  @override
  Widget build(BuildContext context) {
    final shopsAsync = ref.watch(shopsListProvider);
    final selectedShop = ref.watch(selectedShopProvider);
    final filter = ref.watch(shopDetailFilterProvider);
    final salesAsync = ref.watch(shopDetailSalesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Store Detail')),
      body: Stack(
        children: [
          PullToRefresh(
            onRefresh: () => ref.read(shopDetailSalesProvider.notifier).refresh(),
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
                            onChanged: (v) {
                              ref.read(selectedShopProvider.notifier).state = v;
                              setState(() => _section = 0);
                            },
                            decoration:
                                const InputDecoration(labelText: 'Store'),
                          );
                        },
                      ),
                      const SizedBox(height: 8),
                      DateFilterBar(
                        initialFilter: filter,
                        onFilterChanged: (f) =>
                            ref.read(shopDetailFilterProvider.notifier).state = f,
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
                else ...[
                  // Section tab bar (Sales / Customers / Coupon)
                  _SectionTabBar(
                    selected: _section,
                    onSelected: (i) => setState(() => _section = i),
                  ),
                  salesAsync.when(
                    loading: () => const SizedBox.shrink(),
                    error: (e, _) => Padding(
                      padding: const EdgeInsets.all(24),
                      child: ErrorBanner(
                        message: e.toString(),
                        onRetry: () =>
                            ref.read(shopDetailSalesProvider.notifier).refresh(),
                      ),
                    ),
                    data: (sales) {
                      if (sales == null) return const SizedBox.shrink();
                      return _SectionContent(
                        section: _section,
                        shop: selectedShop,
                        filter: filter,
                        sales: sales,
                      );
                    },
                  ),
                ],
                const SizedBox(height: 32),
              ],
            ),
          ),
          if (salesAsync.isLoading) const LoadingOverlay(),
        ],
      ),
    );
  }
}

class _SectionTabBar extends StatelessWidget {
  const _SectionTabBar({required this.selected, required this.onSelected});
  final int selected;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: List.generate(_kSectionLabels.length, (i) {
          final active = i == selected;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            child: TextButton(
              onPressed: () => onSelected(i),
              style: TextButton.styleFrom(
                backgroundColor:
                    active ? AppColors.primary : Colors.transparent,
                foregroundColor: active ? Colors.white : AppColors.primary,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                  side: const BorderSide(color: AppColors.primary),
                ),
              ),
              child: Text(_kSectionLabels[i]),
            ),
          );
        }),
      ),
    );
  }
}

/// Renders the active section. Sales is always loaded; customer/coupon are lazy.
class _SectionContent extends ConsumerWidget {
  const _SectionContent({
    required this.section,
    required this.shop,
    required this.filter,
    required this.sales,
  });

  final int section;
  final String shop;
  final DateRangeFilter filter;
  final ShopSalesPayload sales;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    switch (section) {
      case 0:
        return _KpiSection(
          title: 'Sales',
          allTimeKpis: sales.allTimeKpis,
          periodKpis: sales.periodKpis,
          tabs: sales.tabs,
        );

      case 1:
        final key = (
          shop: shop,
          dateFrom: filter.fromParam ?? '',
          dateTo: filter.toParam ?? '',
        );
        final customerAsync = ref.watch(shopCustomerProvider(key));
        return customerAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 48),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.all(16),
            child: Text('Failed to load customers: $e',
                style: const TextStyle(color: Colors.red)),
          ),
          data: (c) => _CustomerSection(customer: c),
        );

      case 2:
        final key = (
          shop: shop,
          dateFrom: filter.fromParam ?? '',
          dateTo: filter.toParam ?? '',
        );
        final couponAsync = ref.watch(shopCouponProvider(key));
        return couponAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 48),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.all(16),
            child: Text('Failed to load coupons: $e',
                style: const TextStyle(color: Colors.red)),
          ),
          data: (c) => _KpiSection(
            title: 'Coupon',
            allTimeKpis: c.allTimeKpis,
            periodKpis: c.periodKpis,
            tabs: c.detailTable != null ? [c.detailTable!] : [],
          ),
        );

      default:
        return const SizedBox.shrink();
    }
  }
}

class _KpiSection extends StatefulWidget {
  const _KpiSection({
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
  State<_KpiSection> createState() => _KpiSectionState();
}

class _KpiSectionState extends State<_KpiSection> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.primary, width: 4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHeader(title: widget.title),
          if (widget.allTimeKpis.isNotEmpty)
            _kpiGrid(context, widget.allTimeKpis, KpiVariant.allTime),
          if (widget.periodKpis.isNotEmpty)
            _kpiGrid(context, widget.periodKpis, KpiVariant.period),
          if (widget.tabs.isNotEmpty) ...[
            if (widget.tabs.length > 1)
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: List.generate(
                    widget.tabs.length,
                    (i) => TextButton(
                      onPressed: () => setState(() => _tab = i),
                      child: Text(
                        widget.tabs[i].label,
                        style: TextStyle(
                          color: _tab == i
                              ? AppColors.primary
                              : AppColors.textMuted,
                          fontWeight: _tab == i
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
                  headers: widget.tabs[_tab].headers,
                  rows: widget.tabs[_tab].rows,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _kpiGrid(BuildContext context, List<KpiItem> kpis, KpiVariant variant) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Wrap(
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
      ),
    );
  }
}

/// Customer section: KPI + period tabs + Zalo Active list
class _CustomerSection extends StatefulWidget {
  const _CustomerSection({required this.customer});
  final ShopCustomerPayload customer;

  @override
  State<_CustomerSection> createState() => _CustomerSectionState();
}

class _CustomerSectionState extends State<_CustomerSection> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    final c = widget.customer;
    return Container(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.primary, width: 4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SectionHeader(title: 'Customers'),
          if (c.allTimeKpis.isNotEmpty)
            _kpiGrid(context, c.allTimeKpis, KpiVariant.allTime),
          if (c.periodKpis.isNotEmpty)
            _kpiGrid(context, c.periodKpis, KpiVariant.period),
          if (c.tabs.isNotEmpty) ...[
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: List.generate(
                  c.tabs.length,
                  (i) => TextButton(
                    onPressed: () => setState(() => _tab = i),
                    child: Text(
                      c.tabs[i].label,
                      style: TextStyle(
                        color: _tab == i ? AppColors.primary : AppColors.textMuted,
                        fontWeight: _tab == i ? FontWeight.bold : FontWeight.normal,
                      ),
                    ),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: SizedBox(
                height: 300,
                child: DataTableWidget(
                  headers: c.tabs[_tab].headers,
                  rows: c.tabs[_tab].rows,
                ),
              ),
            ),
          ],
          // Zalo Active list
          if (c.zaloActiveTable != null && c.zaloActiveTable!.rows.isNotEmpty) ...[
            const SectionHeader(title: 'Zalo Active Customers'),
            Padding(
              padding: const EdgeInsets.all(12),
              child: SizedBox(
                height: 300,
                child: DataTableWidget(
                  headers: c.zaloActiveTable!.headers,
                  rows: c.zaloActiveTable!.rows,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _kpiGrid(BuildContext context, List<KpiItem> kpis, KpiVariant variant) {
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
