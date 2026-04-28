import 'package:dio/dio.dart';

import '../../../core/api/endpoints.dart';
import '../../../shared/models/analytics_models.dart';

class CouponAnalyticsPayload {
  const CouponAnalyticsPayload({
    required this.allTimeKpis,
    required this.periodKpis,
    required this.tabs,
  });

  final List<KpiItem> allTimeKpis;
  final List<KpiItem> periodKpis;
  final List<TableTab> tabs;

  factory CouponAnalyticsPayload.fromJson(Map<String, dynamic> json) {
    try {
      return CouponAnalyticsPayload(
        allTimeKpis: KpiItem.parseMap(json['all_time_kpis'] as Map<String, dynamic>?),
        periodKpis: KpiItem.parseMap(json['period_kpis'] as Map<String, dynamic>?),
        tabs: TableTab.parseMap(json['tabs'] as Map<String, dynamic>?),
      );
    } catch (e) {
      throw ParseException('Failed to parse CouponAnalyticsPayload: $e');
    }
  }
}

class CouponService {
  CouponService({required Dio dio}) : _dio = dio;
  final Dio _dio;

  Future<CouponAnalyticsPayload> getCouponData({
    String? dateFrom,
    String? dateTo,
    String? shopGroup,
    String? prefix,
  }) async {
    try {
      final params = <String, String>{};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;
      if (shopGroup != null && shopGroup != 'All') params['shop_group'] = shopGroup;
      if (prefix != null && prefix.isNotEmpty) params['prefix'] = prefix;

      final response = await _dio.get(
        Endpoints.coupon,
        queryParameters: params.isEmpty ? null : params,
      );
      return CouponAnalyticsPayload.fromJson(
          response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) throw const PermissionException();
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }

  /// Fetch a single coupon tab lazily (detail or duplicates — by_shop is in initial load).
  Future<TableTab?> getCouponTab({
    required String tab,
    String? dateFrom,
    String? dateTo,
    String? shopGroup,
    String? prefix,
  }) async {
    try {
      final params = <String, String>{'tab': tab};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;
      if (shopGroup != null && shopGroup != 'All') params['shop_group'] = shopGroup;
      if (prefix != null && prefix.isNotEmpty) params['prefix'] = prefix;

      final response = await _dio.get(Endpoints.coupon, queryParameters: params);
      final json = response.data as Map<String, dynamic>;
      final tabs = TableTab.parseMap(json['tabs'] as Map<String, dynamic>?);
      return tabs.isNotEmpty ? tabs.first : null;
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }
}
