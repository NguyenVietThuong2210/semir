import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/features/analytics/customer_detail/customer_detail_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';

import 'customer_detail_service_test.mocks.dart';

@GenerateMocks([Dio])
void main() {
  late MockDio mockDio;
  late CustomerDetailService service;

  setUp(() {
    mockDio = MockDio();
    service = CustomerDetailService(dio: mockDio);
  });

  Map<String, dynamic> _customerPayload({String phone = '09x-xxx-x567'}) => {
        'customer': {
          'username': 'Nguyen Van A',
          'phone': phone,
          'vip_id': 'VIP001234',
          'grade': 'Gold',
        },
        'kpis': {
          'Tổng đơn': '25',
          'Tổng chi tiêu': '12,500,000',
        },
        'invoices': {
          'headers': ['Ngày', 'Cửa hàng', 'Giá trị'],
          'rows': [
            ['2025-03-01', 'HN01', '500,000'],
          ],
        },
      };

  test('VIP ID search → vip_id query param sent', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
              statusCode: 200,
              data: _customerPayload(),
            ));

    await service.getCustomerDetail(vipId: 'VIP001234');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>>((p) => p['vip_id'] == 'VIP001234'),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('phone search → phone query param sent', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
              statusCode: 200,
              data: _customerPayload(),
            ));

    await service.getCustomerDetail(phone: '0901234567');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>>((p) => p['phone'] == '0901234567'),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('404 → NotFoundException thrown', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
            statusCode: 404,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(
      () => service.getCustomerDetail(vipId: 'UNKNOWN999'),
      throwsA(isA<NotFoundException>()),
    );
  });

  test('403 → PermissionException thrown', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
            statusCode: 403,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(
      () => service.getCustomerDetail(vipId: 'VIP001'),
      throwsA(isA<PermissionException>()),
    );
  });

  test('response phone field is in masked format (09x-xxx-x567)', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
              statusCode: 200,
              data: _customerPayload(phone: '09x-xxx-x567'),
            ));

    final payload = await service.getCustomerDetail(vipId: 'VIP001234');

    // API returns already-masked phone — we verify we store it as-is
    expect(payload.phone, '09x-xxx-x567');
    expect(payload.phone.contains('09x'), isTrue);
  });

  test('happy path → CustomerDetailPayload with all fields', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer-detail/'),
              statusCode: 200,
              data: _customerPayload(),
            ));

    final payload = await service.getCustomerDetail(vipId: 'VIP001234');

    expect(payload.username, 'Nguyen Van A');
    expect(payload.grade, 'Gold');
    expect(payload.vipId, 'VIP001234');
    expect(payload.kpis.length, 2);
    expect(payload.invoiceHeaders, ['Ngày', 'Cửa hàng', 'Giá trị']);
    expect(payload.invoiceRows.length, 1);
  });
}
