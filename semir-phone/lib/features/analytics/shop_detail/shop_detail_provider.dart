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

final shopDetailProvider =
    AsyncNotifierProvider<ShopDetailNotifier, ShopDetailPayload?>(
  ShopDetailNotifier.new,
);

class ShopDetailNotifier extends AsyncNotifier<ShopDetailPayload?> {
  @override
  Future<ShopDetailPayload?> build() async {
    final shop = ref.watch(selectedShopProvider);
    final filter = ref.watch(shopDetailFilterProvider);
    if (shop == null) return null;
    return ref.read(shopDetailServiceProvider).getShopDetail(
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
    state = await AsyncValue.guard(() =>
        ref.read(shopDetailServiceProvider).getShopDetail(
              shop: shop,
              dateFrom: filter.fromParam,
              dateTo: filter.toParam,
            ));
  }
}
