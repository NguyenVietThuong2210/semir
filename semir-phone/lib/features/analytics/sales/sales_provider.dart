import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client_provider.dart';
import '../../../shared/models/analytics_models.dart';
import '../../../shared/utils/date_utils.dart';
import '../../../shared/widgets/date_filter_bar.dart';
import 'sales_service.dart';

final salesServiceProvider = Provider<SalesService>((ref) {
  final dio = ref.watch(dioProvider);
  return SalesService(dio: dio);
});

// Current filter state
final salesFilterProvider = StateProvider<DateRangeFilter>((ref) {
  final range = computeDateRange(DatePreset.currentYear);
  return DateRangeFilter(
    preset: DatePreset.currentYear,
    dateFrom: range.dateFrom,
    dateTo: range.dateTo,
  );
});

final salesShopGroupProvider = StateProvider<String>((ref) => 'All');

// Initial data — KPIs + first tab (by_grade)
final salesAnalyticsProvider =
    AsyncNotifierProvider<SalesAnalyticsNotifier, SalesAnalyticsPayload?>(
  SalesAnalyticsNotifier.new,
);

class SalesAnalyticsNotifier extends AsyncNotifier<SalesAnalyticsPayload?> {
  @override
  Future<SalesAnalyticsPayload?> build() async {
    final filter = ref.watch(salesFilterProvider);
    final shopGroup = ref.watch(salesShopGroupProvider);
    return _fetch(filter, shopGroup);
  }

  Future<SalesAnalyticsPayload?> _fetch(
    DateRangeFilter filter,
    String shopGroup,
  ) async {
    final service = ref.read(salesServiceProvider);
    return service.getSalesData(
      dateFrom: filter.fromParam,
      dateTo: filter.toParam,
      shopGroup: shopGroup,
    );
  }

  Future<void> refresh() async {
    final filter = ref.read(salesFilterProvider);
    final shopGroup = ref.read(salesShopGroupProvider);
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() => _fetch(filter, shopGroup));
  }
}

// Per-tab lazy loader — family key: (tabKey, dateFrom, dateTo, shopGroup)
// Triggered only when the user first taps a tab that hasn't loaded yet.
typedef _SalesTabKey = ({String tab, String dateFrom, String dateTo, String shopGroup});

final salesTabProvider =
    FutureProvider.family<TableTab?, _SalesTabKey>((ref, key) async {
  final service = ref.read(salesServiceProvider);
  return service.getSalesTab(
    tab: key.tab,
    dateFrom: key.dateFrom.isEmpty ? null : key.dateFrom,
    dateTo: key.dateTo.isEmpty ? null : key.dateTo,
    shopGroup: key.shopGroup == 'All' ? null : key.shopGroup,
  );
});
