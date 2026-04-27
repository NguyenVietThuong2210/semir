import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client_provider.dart';
import '../../shared/utils/date_utils.dart';
import '../../shared/widgets/date_filter_bar.dart';
import 'chart_service.dart';

final chartServiceProvider = Provider<ChartService>((ref) {
  return ChartService(dio: ref.watch(dioProvider));
});

final chartFilterProvider = StateProvider<DateRangeFilter>((ref) {
  final range = computeDateRange(DatePreset.currentYear);
  return DateRangeFilter(
    preset: DatePreset.currentYear,
    dateFrom: range.dateFrom,
    dateTo: range.dateTo,
  );
});

// Highlighted slice for cross-widget coordination (donut tap → table row)
final selectedSliceLabelProvider = StateProvider<String?>((ref) => null);

final salesChartProvider = AsyncNotifierProvider<SalesChartNotifier, ChartPayload?>(
  SalesChartNotifier.new,
);

class SalesChartNotifier extends AsyncNotifier<ChartPayload?> {
  @override
  Future<ChartPayload?> build() async {
    final filter = ref.watch(chartFilterProvider);
    return ref.read(chartServiceProvider).getSalesChartData(
          dateFrom: filter.fromParam,
          dateTo: filter.toParam,
        );
  }
}

final customerChartProvider =
    AsyncNotifierProvider<CustomerChartNotifier, ChartPayload?>(
  CustomerChartNotifier.new,
);

class CustomerChartNotifier extends AsyncNotifier<ChartPayload?> {
  @override
  Future<ChartPayload?> build() async {
    final filter = ref.watch(chartFilterProvider);
    return ref.read(chartServiceProvider).getCustomerChartData(
          dateFrom: filter.fromParam,
          dateTo: filter.toParam,
        );
  }
}

final couponChartProvider =
    AsyncNotifierProvider<CouponChartNotifier, ChartPayload?>(
  CouponChartNotifier.new,
);

class CouponChartNotifier extends AsyncNotifier<ChartPayload?> {
  @override
  Future<ChartPayload?> build() async {
    final filter = ref.watch(chartFilterProvider);
    return ref.read(chartServiceProvider).getCouponChartData(
          dateFrom: filter.fromParam,
          dateTo: filter.toParam,
        );
  }
}
