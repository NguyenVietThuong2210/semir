import 'package:dio/dio.dart';

import '../../core/api/endpoints.dart';
import '../../shared/models/analytics_models.dart';

class DonutSlice {
  const DonutSlice({
    required this.label,
    required this.value,
    required this.color,
    required this.percentage,
  });
  final String label;
  final String value; // pre-formatted string
  final String color; // hex string e.g. "#0D6EFD"
  final double percentage;

  factory DonutSlice.fromJson(Map<String, dynamic> json) {
    return DonutSlice(
      label: json['label'] as String? ?? '',
      value: json['value'] as String? ?? '',
      color: json['color'] as String? ?? '#0D6EFD',
      percentage: (json['percentage'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class TrendPoint {
  const TrendPoint({required this.label, required this.value});
  final String label;
  final double value;

  factory TrendPoint.fromJson(Map<String, dynamic> json) {
    return TrendPoint(
      label: json['label'] as String? ?? '',
      value: (json['value'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class DonutChart {
  const DonutChart({required this.title, required this.slices});
  final String title;
  final List<DonutSlice> slices;

  factory DonutChart.fromJson(String key, Map<String, dynamic> json) {
    final slices = (json['slices'] as List?)
            ?.map((s) => DonutSlice.fromJson(s as Map<String, dynamic>))
            .toList() ??
        [];
    return DonutChart(title: json['title'] as String? ?? key, slices: slices);
  }
}

class ChartPayload {
  const ChartPayload({required this.donuts, this.trend});
  final List<DonutChart> donuts;
  final List<TrendPoint>? trend;

  factory ChartPayload.fromJson(Map<String, dynamic> json) {
    final donutsMap = json['donuts'] as Map<String, dynamic>? ?? {};
    final donuts = donutsMap.entries
        .map((e) => DonutChart.fromJson(e.key, e.value as Map<String, dynamic>))
        .toList();
    final trendList = json['trend'] as List?;
    final trend = trendList
        ?.map((t) => TrendPoint.fromJson(t as Map<String, dynamic>))
        .toList();
    return ChartPayload(donuts: donuts, trend: trend);
  }
}

class ChartService {
  ChartService({required Dio dio}) : _dio = dio;
  final Dio _dio;

  Future<ChartPayload> _fetch(String endpoint,
      {String? dateFrom, String? dateTo}) async {
    try {
      final params = <String, String>{};
      if (dateFrom != null) params['date_from'] = dateFrom;
      if (dateTo != null) params['date_to'] = dateTo;
      final response = await _dio.get(endpoint,
          queryParameters: params.isEmpty ? null : params);
      return ChartPayload.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) throw const PermissionException();
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }

  Future<ChartPayload> getSalesChartData({String? dateFrom, String? dateTo}) =>
      _fetch(Endpoints.salesChart, dateFrom: dateFrom, dateTo: dateTo);

  Future<ChartPayload> getCustomerChartData(
          {String? dateFrom, String? dateTo}) =>
      _fetch(Endpoints.customerChart, dateFrom: dateFrom, dateTo: dateTo);

  Future<ChartPayload> getCouponChartData({String? dateFrom, String? dateTo}) =>
      _fetch(Endpoints.couponChart, dateFrom: dateFrom, dateTo: dateTo);
}
