import 'package:dio/dio.dart';

import '../../../core/api/endpoints.dart';
import '../../../features/analytics/customer_detail/customer_detail_service.dart'
    show NotFoundException;
import '../../../shared/models/analytics_models.dart';

// ── Per-section payload models ────────────────────────────────────────────────

class ShopSalesPayload {
  const ShopSalesPayload({
    required this.allTimeKpis,
    required this.periodKpis,
    required this.tabs,
  });

  final List<KpiItem> allTimeKpis;
  final List<KpiItem> periodKpis;
  final List<TableTab> tabs; // by_session, by_month, by_week

  factory ShopSalesPayload.fromJson(Map<String, dynamic> json) {
    final sales = json['sales'] as Map<String, dynamic>? ?? {};
    // Inline table keys (not nested under 'tabs')
    final tabData = <String, dynamic>{};
    for (final key in ['by_session', 'by_month', 'by_week']) {
      if (sales.containsKey(key)) tabData[key] = sales[key];
    }
    return ShopSalesPayload(
      allTimeKpis: KpiItem.parseMap(sales['all_time_kpis'] as Map<String, dynamic>?),
      periodKpis: KpiItem.parseMap(sales['period_kpis'] as Map<String, dynamic>?),
      tabs: TableTab.parseMap(tabData.isNotEmpty ? tabData : null),
    );
  }
}

class ShopCustomerPayload {
  const ShopCustomerPayload({
    required this.allTimeKpis,
    required this.periodKpis,
    required this.tabs,
    this.zaloActiveTable,
  });

  final List<KpiItem> allTimeKpis;
  final List<KpiItem> periodKpis;
  final List<TableTab> tabs; // by_season, by_month, by_week
  final TableTab? zaloActiveTable;

  factory ShopCustomerPayload.fromJson(Map<String, dynamic> json) {
    final customer = json['customer'] as Map<String, dynamic>? ?? {};
    final tabData = <String, dynamic>{};
    for (final key in ['by_season', 'by_month', 'by_week']) {
      if (customer.containsKey(key)) tabData[key] = customer[key];
    }
    TableTab? zaloActive;
    final rawZalo = customer['zalo_active'] as Map<String, dynamic>?;
    if (rawZalo != null) {
      zaloActive = TableTab(
        tabKey: 'zalo_active',
        label: 'Zalo Active',
        headers: (rawZalo['headers'] as List?)?.cast<String>() ?? [],
        rows: (rawZalo['rows'] as List?)
                ?.map((r) => (r as List).cast<String>())
                .toList() ??
            [],
      );
    }
    return ShopCustomerPayload(
      allTimeKpis: KpiItem.parseMap(customer['all_time_kpis'] as Map<String, dynamic>?),
      periodKpis: KpiItem.parseMap(customer['period_kpis'] as Map<String, dynamic>?),
      tabs: TableTab.parseMap(tabData.isNotEmpty ? tabData : null),
      zaloActiveTable: zaloActive,
    );
  }
}

class ShopCouponPayload {
  const ShopCouponPayload({
    required this.allTimeKpis,
    required this.periodKpis,
    this.detailTable,
  });

  final List<KpiItem> allTimeKpis;
  final List<KpiItem> periodKpis;
  final TableTab? detailTable;

  factory ShopCouponPayload.fromJson(Map<String, dynamic> json) {
    final coupon = json['coupon'] as Map<String, dynamic>? ?? {};
    final rawDetail = coupon['detail_table'] as Map<String, dynamic>?;
    TableTab? detail;
    if (rawDetail != null) {
      detail = TableTab(
        tabKey: 'detail_table',
        label: 'Coupon Details',
        headers: (rawDetail['headers'] as List?)?.cast<String>() ?? [],
        rows: (rawDetail['rows'] as List?)
                ?.map((r) => (r as List).cast<String>())
                .toList() ??
            [],
      );
    }
    return ShopCouponPayload(
      allTimeKpis: KpiItem.parseMap(coupon['all_time_kpis'] as Map<String, dynamic>?),
      periodKpis: KpiItem.parseMap(coupon['period_kpis'] as Map<String, dynamic>?),
      detailTable: detail,
    );
  }
}

// ── Service ───────────────────────────────────────────────────────────────────

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

  /// Initial load — returns sales section only (fastest; validates shop exists).
  Future<ShopSalesPayload> getShopSales({
    required String shop,
    String? dateFrom,
    String? dateTo,
  }) async {
    try {
      final params = <String, String>{'shop': shop};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;

      final response = await _dio.get(Endpoints.shopDetail, queryParameters: params);
      return ShopSalesPayload.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) throw const PermissionException();
      if (e.response?.statusCode == 404) throw const NotFoundException();
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }

  /// Lazy-load customer section when the user first selects that tab.
  Future<ShopCustomerPayload> getShopCustomer({
    required String shop,
    String? dateFrom,
    String? dateTo,
  }) async {
    try {
      final params = <String, String>{'shop': shop, 'section': 'customer'};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;

      final response = await _dio.get(Endpoints.shopDetail, queryParameters: params);
      return ShopCustomerPayload.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }

  /// Lazy-load coupon section when the user first selects that tab.
  Future<ShopCouponPayload> getShopCoupon({
    required String shop,
    String? dateFrom,
    String? dateTo,
  }) async {
    try {
      final params = <String, String>{'shop': shop, 'section': 'coupon'};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;

      final response = await _dio.get(Endpoints.shopDetail, queryParameters: params);
      return ShopCouponPayload.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }
}
