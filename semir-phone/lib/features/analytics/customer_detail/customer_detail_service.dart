import 'package:dio/dio.dart';

import '../../../core/api/endpoints.dart';
import '../../../shared/models/analytics_models.dart';

class NotFoundException implements Exception {
  const NotFoundException();
}

class CustomerDetailPayload {
  const CustomerDetailPayload({
    required this.username,
    required this.phone,
    required this.vipId,
    required this.grade,
    required this.kpis,
    required this.invoiceHeaders,
    required this.invoiceRows,
  });

  final String username;
  final String phone; // already masked by API: 09x-xxx-x567
  final String vipId;
  final String grade;
  final List<KpiItem> kpis;
  final List<String> invoiceHeaders;
  final List<List<String>> invoiceRows;

  factory CustomerDetailPayload.fromJson(Map<String, dynamic> json) {
    final customer = json['customer'] as Map<String, dynamic>? ?? json;
    final invoices = json['invoices'] as Map<String, dynamic>? ?? {};

    return CustomerDetailPayload(
      username: customer['username'] as String? ?? '',
      phone: customer['phone'] as String? ?? '',
      vipId: customer['vip_id'] as String? ?? '',
      grade: customer['grade'] as String? ?? '',
      kpis: KpiItem.parseMap(json['kpis'] as Map<String, dynamic>?),
      invoiceHeaders:
          (invoices['headers'] as List?)?.cast<String>() ?? [],
      invoiceRows: (invoices['rows'] as List?)
              ?.map((r) => (r as List).cast<String>())
              .toList() ??
          [],
    );
  }
}

class CustomerDetailService {
  CustomerDetailService({required Dio dio}) : _dio = dio;
  final Dio _dio;

  Future<CustomerDetailPayload> getCustomerDetail({
    String? vipId,
    String? phone,
  }) async {
    assert(vipId != null || phone != null,
        'Either vipId or phone must be provided');
    try {
      final params = <String, String>{};
      if (vipId != null && vipId.isNotEmpty) params['vip_id'] = vipId;
      if (phone != null && phone.isNotEmpty) params['phone'] = phone;

      final response = await _dio.get(
        Endpoints.customerDetail,
        queryParameters: params,
      );
      return CustomerDetailPayload.fromJson(
          response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) throw const NotFoundException();
      if (e.response?.statusCode == 403) throw const PermissionException();
      throw ApiException(e.message ?? 'Network error',
          statusCode: e.response?.statusCode);
    }
  }
}
