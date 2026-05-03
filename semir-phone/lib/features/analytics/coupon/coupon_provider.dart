import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client_provider.dart';
import '../../../shared/models/analytics_models.dart';
import '../../../shared/utils/date_utils.dart';
import '../../../shared/widgets/date_filter_bar.dart';
import 'coupon_service.dart';

final couponServiceProvider = Provider<CouponService>((ref) {
  return CouponService(dio: ref.watch(dioProvider));
});

final couponFilterProvider = StateProvider<DateRangeFilter>((ref) {
  final range = computeDateRange(DatePreset.currentYear);
  return DateRangeFilter(
    preset: DatePreset.currentYear,
    dateFrom: range.dateFrom,
    dateTo: range.dateTo,
  );
});

final couponShopGroupProvider = StateProvider<String>((ref) => 'All');
final couponPrefixProvider = StateProvider<String>((ref) => '');

final couponAnalyticsProvider =
    AsyncNotifierProvider<CouponAnalyticsNotifier, CouponAnalyticsPayload?>(
  CouponAnalyticsNotifier.new,
);

class CouponAnalyticsNotifier extends AsyncNotifier<CouponAnalyticsPayload?> {
  @override
  Future<CouponAnalyticsPayload?> build() async {
    final filter = ref.watch(couponFilterProvider);
    final shopGroup = ref.watch(couponShopGroupProvider);
    final prefix = ref.watch(couponPrefixProvider);
    return _fetch(filter, shopGroup, prefix);
  }

  Future<CouponAnalyticsPayload?> _fetch(
      DateRangeFilter filter, String shopGroup, String prefix) async {
    return ref.read(couponServiceProvider).getCouponData(
          dateFrom: filter.fromParam,
          dateTo: filter.toParam,
          shopGroup: shopGroup,
          prefix: prefix.isEmpty ? null : prefix,
        );
  }

  Future<void> refresh() async {
    final filter = ref.read(couponFilterProvider);
    final shopGroup = ref.read(couponShopGroupProvider);
    final prefix = ref.read(couponPrefixProvider);
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() => _fetch(filter, shopGroup, prefix));
  }
}

// Per-tab lazy loader for detail and duplicates tabs.
typedef _CouponTabKey = ({
  String tab,
  String dateFrom,
  String dateTo,
  String shopGroup,
  String prefix,
});

final couponTabProvider =
    FutureProvider.autoDispose.family<TableTab?, _CouponTabKey>((ref, key) async {
  final service = ref.read(couponServiceProvider);
  return service.getCouponTab(
    tab: key.tab,
    dateFrom: key.dateFrom.isEmpty ? null : key.dateFrom,
    dateTo: key.dateTo.isEmpty ? null : key.dateTo,
    shopGroup: key.shopGroup == 'All' ? null : key.shopGroup,
    prefix: key.prefix.isEmpty ? null : key.prefix,
  );
});
