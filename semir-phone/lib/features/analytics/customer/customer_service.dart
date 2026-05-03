import 'package:dio/dio.dart';

import '../../../core/api/endpoints.dart';
import '../../../shared/models/analytics_models.dart';

class CustomerAnalyticsPayload {
  const CustomerAnalyticsPayload({
    required this.allTimeKpis,
    required this.periodKpis,
    required this.registrationBreakdownTabs,
    required this.comparisonTabs,
  });

  final List<KpiItem> allTimeKpis;
  final List<KpiItem> periodKpis;
  final List<TableTab> registrationBreakdownTabs;
  final List<TableTab> comparisonTabs;

  factory CustomerAnalyticsPayload.fromJson(Map<String, dynamic> json) {
    try {
      return CustomerAnalyticsPayload(
        allTimeKpis: KpiItem.parseMap(json['all_time_kpis'] as Map<String, dynamic>?),
        periodKpis: KpiItem.parseMap(json['period_kpis'] as Map<String, dynamic>?),
        registrationBreakdownTabs:
            TableTab.parseMap(json['registration_breakdown'] as Map<String, dynamic>?),
        comparisonTabs: TableTab.parseMap(json['customer_comparison'] as Map<String, dynamic>?),
      );
    } catch (e) {
      throw ParseException('Failed to parse CustomerAnalyticsPayload: $e');
    }
  }
}

class CustomerService {
  CustomerService({required Dio dio}) : _dio = dio;
  final Dio _dio;

  Future<CustomerAnalyticsPayload> getCustomerData({
    String? dateFrom,
    String? dateTo,
  }) async {
    try {
      final params = <String, String>{};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;

      final response = await _dio.get(
        Endpoints.customer,
        queryParameters: params.isEmpty ? null : params,
      );
      return CustomerAnalyticsPayload.fromJson(
          response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) throw const PermissionException();
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }
}
