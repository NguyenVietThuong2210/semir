import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client_provider.dart';
import '../../../shared/utils/date_utils.dart';
import '../../../shared/widgets/date_filter_bar.dart';
import 'shop_detail_service.dart';

final shopDetailServiceProvider = Provider<ShopDetailService>((ref) {
  return ShopDetailService(dio: ref.watch(dioProvider));
});

final shopsListProvider = FutureProvider<List<String>>((ref) async {
  return ref.watch(shopDetailServiceProvider).getShops();
});

final selectedShopProvider = StateProvider<String?>((ref) => null);

final shopDetailFilterProvider = StateProvider<DateRangeFilter>((ref) {
  final range = computeDateRange(DatePreset.currentYear);
  return DateRangeFilter(
    preset: DatePreset.currentYear,
    dateFrom: range.dateFrom,
    dateTo: range.dateTo,
  );
});

// Initial load — sales section only (fast; also validates shop exists).
final shopDetailSalesProvider =
    AsyncNotifierProvider<ShopDetailSalesNotifier, ShopSalesPayload?>(
  ShopDetailSalesNotifier.new,
);

class ShopDetailSalesNotifier extends AsyncNotifier<ShopSalesPayload?> {
  @override
  Future<ShopSalesPayload?> build() async {
    final shop = ref.watch(selectedShopProvider);
    final filter = ref.watch(shopDetailFilterProvider);
    if (shop == null) return null;
    return _fetch(shop, filter);
  }

  Future<ShopSalesPayload?> _fetch(String shop, DateRangeFilter filter) async {
    return ref.read(shopDetailServiceProvider).getShopSales(
          shop: shop,
          dateFrom: filter.fromParam,
          dateTo: filter.toParam,
        );
  }

  Future<void> refresh() async {
    final shop = ref.read(selectedShopProvider);
    final filter = ref.read(shopDetailFilterProvider);
    if (shop == null) return;
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() => _fetch(shop, filter));
  }
}

// Lazy-loaded customer section — triggered when user selects Customer tab.
typedef _ShopSectionKey = ({String shop, String dateFrom, String dateTo});

final shopCustomerProvider =
    FutureProvider.family<ShopCustomerPayload, _ShopSectionKey>((ref, key) async {
  return ref.read(shopDetailServiceProvider).getShopCustomer(
        shop: key.shop,
        dateFrom: key.dateFrom.isEmpty ? null : key.dateFrom,
        dateTo: key.dateTo.isEmpty ? null : key.dateTo,
      );
});

// Lazy-loaded coupon section — triggered when user selects Coupon tab.
final shopCouponProvider =
    FutureProvider.family<ShopCouponPayload, _ShopSectionKey>((ref, key) async {
  return ref.read(shopDetailServiceProvider).getShopCoupon(
        shop: key.shop,
        dateFrom: key.dateFrom.isEmpty ? null : key.dateFrom,
        dateTo: key.dateTo.isEmpty ? null : key.dateTo,
      );
});
