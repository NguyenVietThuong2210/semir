import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/features/analytics/customer/customer_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';

import 'customer_service_test.mocks.dart';

@GenerateMocks([Dio])
void main() {
  late MockDio mockDio;
  late CustomerService service;

  setUp(() {
    mockDio = MockDio();
    service = CustomerService(dio: mockDio);
  });

  Map<String, dynamic> _successPayload() => {
        'all_time_kpis': {
          'Tổng KH CNV': '5,678',
          'Tỷ lệ quay lại': '62.5%',
        },
        'period_kpis': {
          'KH mới kỳ': '1,234',
          'KH active': '3,456',
        },
        'registration_breakdown': {
          'by_shop': {
            'label': 'Theo Cửa hàng',
            'headers': ['Cửa hàng', 'Số KH'],
            'rows': [
              ['HN01', '500'],
              ['HN02', '300'],
            ],
          },
        },
        'comparison': {
          'pos_only': {
            'label': 'POS Only',
            'headers': ['Tháng', 'Số KH'],
            'rows': [
              ['01/2025', '200'],
            ],
          },
        },
      };

  test('happy path → CustomerAnalyticsPayload with correct kpis', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    final payload = await service.getCustomerData(
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
    );

    expect(payload.allTimeKpis.length, 2);
    expect(payload.periodKpis.length, 2);
    expect(payload.registrationBreakdownTabs.length, 1);
    expect(payload.comparisonTabs.length, 1);
    expect(payload.registrationBreakdownTabs.first.tabKey, 'by_shop');
  });

  test('403 response → PermissionException thrown', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
            statusCode: 403,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(
      () => service.getCustomerData(),
      throwsA(isA<PermissionException>()),
    );
  });

  test('malformed response → ParseException thrown', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
              statusCode: 200,
              data: {
                'registration_breakdown': 'not_a_map', // invalid type
              },
            ));

    expect(
      () => service.getCustomerData(),
      throwsA(isA<ParseException>()),
    );
  });

  test('date params passed correctly in query string', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getCustomerData(dateFrom: '2025-01-01', dateTo: '2025-12-31');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>>((p) =>
            p['date_from'] == '2025-01-01' && p['date_to'] == '2025-12-31'),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('no date params → queryParameters is null or empty', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getCustomerData();

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>?>((p) => p == null || p.isEmpty),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('500 response → ApiException thrown', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/analytics/customer/'),
            statusCode: 500,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(
      () => service.getCustomerData(),
      throwsA(isA<ApiException>()),
    );
  });
}
