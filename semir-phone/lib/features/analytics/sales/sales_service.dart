import 'package:dio/dio.dart';

import '../../../core/api/endpoints.dart';
import '../../../shared/models/analytics_models.dart';

class SalesAnalyticsPayload {
  const SalesAnalyticsPayload({
    required this.allTimeKpis,
    required this.periodKpis,
    required this.tabs,
    this.availableTabs = const [],
  });

  final List<KpiItem> allTimeKpis;
  final List<KpiItem> periodKpis;
  final List<TableTab> tabs;
  final List<String> availableTabs;

  factory SalesAnalyticsPayload.fromJson(Map<String, dynamic> json) {
    final rawTabs = (json['available_tabs'] as List<dynamic>?)
        ?.map((e) => e.toString())
        .toList() ?? [];
    return SalesAnalyticsPayload(
      allTimeKpis: KpiItem.parseMap(json['all_time_kpis'] as Map<String, dynamic>?),
      periodKpis: KpiItem.parseMap(json['period_kpis'] as Map<String, dynamic>?),
      tabs: TableTab.parseMap(json['tabs'] as Map<String, dynamic>?),
      availableTabs: rawTabs,
    );
  }
}

class SalesService {
  SalesService({required Dio dio}) : _dio = dio;
  final Dio _dio;

  Future<SalesAnalyticsPayload> getSalesData({
    String? dateFrom,
    String? dateTo,
    String? shopGroup,
  }) async {
    try {
      final params = <String, String>{};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;
      if (shopGroup != null && shopGroup != 'All') params['shop_group'] = shopGroup;

      final response = await _dio.get(
        Endpoints.sales,
        queryParameters: params.isEmpty ? null : params,
      );

      return SalesAnalyticsPayload.fromJson(
        response.data as Map<String, dynamic>,
      );
    } on DioException catch (e) {
      throw ApiException(
        e.message ?? 'Network error',
        statusCode: e.response?.statusCode,
      );
    }
  }

  /// Fetch a single tab lazily — called when the user first selects a tab.
  Future<TableTab?> getSalesTab({
    required String tab,
    String? dateFrom,
    String? dateTo,
    String? shopGroup,
  }) async {
    try {
      final params = <String, String>{'tab': tab};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;
      if (shopGroup != null && shopGroup != 'All') params['shop_group'] = shopGroup;

      final response = await _dio.get(Endpoints.sales, queryParameters: params);
      final json = response.data as Map<String, dynamic>;
      final tabs = TableTab.parseMap(json['tabs'] as Map<String, dynamic>?);
      return tabs.isNotEmpty ? tabs.first : null;
    } on DioException catch (e) {
      throw ApiException(
        e.message ?? 'Network error',
        statusCode: e.response?.statusCode,
      );
    }
  }
}
