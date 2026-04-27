import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../shared/widgets/error_banner.dart';
import '../../shared/widgets/loading_overlay.dart';
import '../../shared/widgets/section_header.dart';
import 'chart_provider.dart';
import 'chart_service.dart';
import 'donut_card.dart';

class SalesChartPage extends ConsumerWidget {
  const SalesChartPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chartAsync = ref.watch(salesChartProvider);
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
                selectedSlice: selectedSlice,
                onSliceTapped: (label) => ref
                    .read(selectedSliceLabelProvider.notifier)
                    .state = label,
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
    required this.selectedSlice,
    required this.onSliceTapped,
  });

  final ChartPayload payload;
  final String? selectedSlice;
  final ValueChanged<String> onSliceTapped;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
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
        if (payload.trend != null) ...[
          const SectionHeader(title: 'Trend'),
          const SizedBox(height: 120, child: _TrendPlaceholder()),
        ],
        const SizedBox(height: 32),
      ],
    );
  }
}

// Placeholder for trend chart — replaced with fl_chart LineChart when data available
class _TrendPlaceholder extends StatelessWidget {
  const _TrendPlaceholder();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text('Trend chart', style: TextStyle(color: Colors.grey)),
    );
  }
}
