import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client_provider.dart';
import '../../../shared/utils/date_utils.dart';
import '../../../shared/widgets/date_filter_bar.dart';
import 'customer_service.dart';

final customerServiceProvider = Provider<CustomerService>((ref) {
  return CustomerService(dio: ref.watch(dioProvider));
});

final customerFilterProvider = StateProvider<DateRangeFilter>((ref) {
  final range = computeDateRange(DatePreset.currentYear);
  return DateRangeFilter(
    preset: DatePreset.currentYear,
    dateFrom: range.dateFrom,
    dateTo: range.dateTo,
  );
});

final customerAnalyticsProvider =
    AsyncNotifierProvider<CustomerAnalyticsNotifier, CustomerAnalyticsPayload?>(
  CustomerAnalyticsNotifier.new,
);

class CustomerAnalyticsNotifier
    extends AsyncNotifier<CustomerAnalyticsPayload?> {
  @override
  Future<CustomerAnalyticsPayload?> build() async {
    final filter = ref.watch(customerFilterProvider);
    return ref.read(customerServiceProvider).getCustomerData(
          dateFrom: filter.fromParam,
          dateTo: filter.toParam,
        );
  }

  Future<void> refresh() async {
    final filter = ref.read(customerFilterProvider);
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() =>
        ref.read(customerServiceProvider).getCustomerData(
              dateFrom: filter.fromParam,
              dateTo: filter.toParam,
            ));
  }
}
