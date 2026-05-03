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
    this.registrationStore = '',
    this.registrationDate = '',
    this.email = '',
    this.cnvSyncStatus,
  });

  final String username;
  final String phone; // already masked by API: 09x-xxx-x567
  final String vipId;
  final String grade;
  final String registrationStore;
  final String registrationDate;
  final String email;
  final String? cnvSyncStatus; // 'synced' | 'not_synced' | null
  final List<KpiItem> kpis;
  final List<String> invoiceHeaders;
  final List<List<String>> invoiceRows;

  factory CustomerDetailPayload.fromJson(Map<String, dynamic> json) {
    // API returns flat structure — build KPIs from individual numeric fields
    final kpis = <KpiItem>[
      KpiItem(label: 'Total Invoices', value: '${json['total_invoices'] ?? 0}'),
      KpiItem(label: 'Total Revenue (VND)', value: '${json['total_revenue'] ?? '0'}'),
    ];

    // invoice_history: [{date, shop, invoice_id, amount, coupon_used}]
    final rawHistory = json['invoice_history'];
    final history = rawHistory is List ? rawHistory : <dynamic>[];
    const headers = ['Date', 'Shop', 'Invoice', 'Amount'];
    final rows = history
        .map<List<String>>((h) => [
              h['date'] as String? ?? '',
              h['shop'] as String? ?? '',
              h['invoice_id'] as String? ?? '',
              h['amount'] as String? ?? '',
            ])
        .toList();

    return CustomerDetailPayload(
      username: json['name'] as String? ?? '',
      phone: json['phone'] as String? ?? '',
      vipId: json['vip_id'] as String? ?? '',
      grade: json['grade'] as String? ?? '',
      registrationStore: json['registration_store'] as String? ?? '',
      registrationDate: json['registration_date'] as String? ?? '',
      email: json['email'] as String? ?? '',
      cnvSyncStatus: json['cnv_sync_status'] as String?,
      kpis: kpis,
      invoiceHeaders: headers,
      invoiceRows: rows,
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
