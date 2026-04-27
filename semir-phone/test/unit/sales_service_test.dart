import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/features/analytics/sales/sales_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';

import 'sales_service_test.mocks.dart';

@GenerateMocks([Dio])
void main() {
  late MockDio mockDio;
  late SalesService service;

  setUp(() {
    mockDio = MockDio();
    service = SalesService(dio: mockDio);
  });

  Map<String, dynamic> _successPayload() => {
        'all_time_kpis': {
          'Tổng doanh thu': '1,234,567,890',
          'Tổng đơn hàng': '12,345',
        },
        'period_kpis': {
          'Doanh thu kỳ': '500,000,000',
          'Đơn hàng kỳ': '5,000',
        },
        'tabs': {
          'grade': {
            'label': 'Theo Hạng',
            'headers': ['Hạng', 'Doanh thu', 'Tỷ lệ'],
            'rows': [
              ['Diamond', '200,000,000', '40.00%'],
              ['Gold', '150,000,000', '30.00%'],
            ],
          },
        },
      };

  test('happy path → SalesAnalyticsPayload with correct all_time_kpis', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/sales/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    final payload = await service.getSalesData(
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
    );

    expect(payload.allTimeKpis.length, 2);
    expect(payload.periodKpis.length, 2);
    expect(payload.tabs.length, 1);
    expect(payload.tabs.first.tabKey, 'grade');
    expect(payload.tabs.first.headers, ['Hạng', 'Doanh thu', 'Tỷ lệ']);
  });

  test('date params serialized as YYYY-MM-DD in query string', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/sales/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getSalesData(dateFrom: '2025-01-01', dateTo: '2025-12-31');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>>((p) =>
            p['date_from'] == '2025-01-01' && p['date_to'] == '2025-12-31'),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('500 response → ApiException thrown', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/analytics/sales/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/analytics/sales/'),
            statusCode: 500,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(
      () => service.getSalesData(),
      throwsA(isA<ApiException>()),
    );
  });

  test('shopGroup "All" not sent as query param', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/sales/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getSalesData(shopGroup: 'All');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>?>((p) => p == null || !p.containsKey('shop_group')),
        named: 'queryParameters',
      ),
    )).called(1);
  });
}
