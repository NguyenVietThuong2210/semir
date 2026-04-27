import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client_provider.dart';
import 'customer_detail_service.dart';

final customerDetailServiceProvider = Provider<CustomerDetailService>((ref) {
  return CustomerDetailService(dio: ref.watch(dioProvider));
});

// Search query — empty means not searched yet
final customerSearchQueryProvider =
    StateProvider<({String? vipId, String? phone})>((ref) => (vipId: null, phone: null));

final customerDetailProvider =
    AsyncNotifierProvider<CustomerDetailNotifier, CustomerDetailPayload?>(
  CustomerDetailNotifier.new,
);

class CustomerDetailNotifier extends AsyncNotifier<CustomerDetailPayload?> {
  @override
  Future<CustomerDetailPayload?> build() async {
    final query = ref.watch(customerSearchQueryProvider);
    if (query.vipId == null && query.phone == null) return null;
    return ref.read(customerDetailServiceProvider).getCustomerDetail(
          vipId: query.vipId,
          phone: query.phone,
        );
  }

  Future<void> search({String? vipId, String? phone}) async {
    ref.read(customerSearchQueryProvider.notifier).state =
        (vipId: vipId, phone: phone);
  }
}
