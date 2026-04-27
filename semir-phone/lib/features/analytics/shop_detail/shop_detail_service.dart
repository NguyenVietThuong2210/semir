import 'package:dio/dio.dart';

import '../../../core/api/endpoints.dart';
import '../../../shared/models/analytics_models.dart';

class ShopDetailPayload {
  const ShopDetailPayload({
    required this.salesAllTimeKpis,
    required this.salesPeriodKpis,
    required this.salesTabs,
    required this.customerKpis,
    required this.customerTabs,
    required this.couponKpis,
    required this.couponTabs,
  });

  final List<KpiItem> salesAllTimeKpis;
  final List<KpiItem> salesPeriodKpis;
  final List<TableTab> salesTabs;
  final List<KpiItem> customerKpis;
  final List<TableTab> customerTabs;
  final List<KpiItem> couponKpis;
  final List<TableTab> couponTabs;

  factory ShopDetailPayload.fromJson(Map<String, dynamic> json) {
    final sales = json['sales'] as Map<String, dynamic>? ?? {};
    final customer = json['customer'] as Map<String, dynamic>? ?? {};
    final coupon = json['coupon'] as Map<String, dynamic>? ?? {};

    return ShopDetailPayload(
      salesAllTimeKpis: KpiItem.parseMap(sales['all_time_kpis'] as Map<String, dynamic>?),
      salesPeriodKpis: KpiItem.parseMap(sales['period_kpis'] as Map<String, dynamic>?),
      salesTabs: TableTab.parseMap(sales['tabs'] as Map<String, dynamic>?),
      customerKpis: KpiItem.parseMap(customer['kpis'] as Map<String, dynamic>?),
      customerTabs: TableTab.parseMap(customer['tabs'] as Map<String, dynamic>?),
      couponKpis: KpiItem.parseMap(coupon['kpis'] as Map<String, dynamic>?),
      couponTabs: TableTab.parseMap(coupon['tabs'] as Map<String, dynamic>?),
    );
  }
}

class ShopDetailService {
  ShopDetailService({required Dio dio}) : _dio = dio;
  final Dio _dio;

  Future<List<String>> getShops() async {
    try {
      final response = await _dio.get(Endpoints.shops);
      final data = response.data as Map<String, dynamic>;
      return (data['shops'] as List?)?.cast<String>() ?? [];
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) throw const PermissionException();
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }

  Future<ShopDetailPayload> getShopDetail({
    required String shop,
    String? dateFrom,
    String? dateTo,
  }) async {
    try {
      final params = <String, String>{'shop': shop};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;

      final response = await _dio.get(
        Endpoints.shopDetail,
        queryParameters: params,
      );
      return ShopDetailPayload.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) throw const PermissionException();
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }
}
