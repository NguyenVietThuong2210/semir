import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../shared/widgets/date_filter_bar.dart';
import '../../shared/widgets/error_banner.dart';
import '../../shared/widgets/loading_overlay.dart';
import '../../shared/widgets/section_header.dart';
import 'chart_provider.dart';
import 'chart_service.dart';
import 'donut_card.dart';
import 'trend_line_chart.dart';

class SalesChartPage extends ConsumerWidget {
  const SalesChartPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chartAsync = ref.watch(salesChartProvider);
    final filter = ref.watch(chartFilterProvider);
    final selectedSlice = ref.watch(selectedSliceLabelProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Sales Charts')),
      body: Stack(
        children: [
          chartAsync.when(
            loading: () => const SizedBox.expand(),
            error: (e, _) => Center(
              child: ErrorBanner(message: e.toString()),
            ),
            data: (payload) {
              if (payload == null) {
                return const Center(child: Text('No data'));
              }
              return _ChartContent(
                payload: payload,
                filter: filter,
                selectedSlice: selectedSlice,
                onSliceTapped: (label) =>
                    ref.read(selectedSliceLabelProvider.notifier).state = label,
                onFilterChanged: (f) =>
                    ref.read(chartFilterProvider.notifier).state = f,
              );
            },
          ),
          if (chartAsync.isLoading) const LoadingOverlay(),
        ],
      ),
    );
  }
}

class _ChartContent extends StatelessWidget {
  const _ChartContent({
    required this.payload,
    required this.filter,
    required this.selectedSlice,
    required this.onSliceTapped,
    required this.onFilterChanged,
  });

  final ChartPayload payload;
  final DateRangeFilter filter;
  final String? selectedSlice;
  final ValueChanged<String> onSliceTapped;
  final ValueChanged<DateRangeFilter> onFilterChanged;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        DateFilterBar(initialFilter: filter, onFilterChanged: onFilterChanged),
        const SizedBox(height: 8),
        const SectionHeader(title: 'Analytics Charts'),
        const SizedBox(height: 8),
        ...payload.donuts.map((chart) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: DonutCard(
                chart: chart,
                highlightedLabel: selectedSlice,
                onSliceTapped: onSliceTapped,
              ),
            )),
        if (payload.trend != null && payload.trend!.isNotEmpty) ...[
          const SectionHeader(title: 'Trend'),
          TrendLineChart(points: payload.trend!),
        ],
        const SizedBox(height: 32),
      ],
    );
  }
}
