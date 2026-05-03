import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../shared/widgets/date_filter_bar.dart';
import '../../shared/widgets/error_banner.dart';
import '../../shared/widgets/loading_overlay.dart';
import '../../shared/widgets/section_header.dart';
import 'chart_provider.dart';
import 'donut_card.dart';
import 'trend_line_chart.dart';

class CustomerChartPage extends ConsumerWidget {
  const CustomerChartPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chartAsync = ref.watch(customerChartProvider);
    final filter = ref.watch(chartFilterProvider);
    final selectedSlice = ref.watch(selectedSliceLabelProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Customer Charts')),
      body: Stack(
        children: [
          chartAsync.when(
            loading: () => const SizedBox.expand(),
            error: (e, _) => Center(child: ErrorBanner(message: e.toString())),
            data: (payload) {
              if (payload == null) {
                return const Center(child: Text('No data'));
              }
              return ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  DateFilterBar(
                    initialFilter: filter,
                    onFilterChanged: (f) =>
                        ref.read(chartFilterProvider.notifier).state = f,
                  ),
                  const SizedBox(height: 8),
                  const SectionHeader(title: 'Analytics Charts'),
                  const SizedBox(height: 8),
                  ...payload.donuts.map((chart) => Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: DonutCard(
                          chart: chart,
                          highlightedLabel: selectedSlice,
                          onSliceTapped: (l) =>
                              ref.read(selectedSliceLabelProvider.notifier).state = l,
                        ),
                      )),
                  if (payload.trend != null && payload.trend!.isNotEmpty) ...[
                    const SectionHeader(title: 'Trend'),
                    TrendLineChart(points: payload.trend!),
                  ],
                  const SizedBox(height: 32),
                ],
              );
            },
          ),
          if (chartAsync.isLoading) const LoadingOverlay(),
        ],
      ),
    );
  }
}
