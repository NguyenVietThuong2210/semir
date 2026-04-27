import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/features/charts/chart_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';

import 'chart_service_test.mocks.dart';

@GenerateMocks([Dio])
void main() {
  late MockDio mockDio;
  late ChartService service;

  setUp(() {
    mockDio = MockDio();
    service = ChartService(dio: mockDio);
  });

  Map<String, dynamic> _successPayload({bool includeTrend = true}) => {
        'donuts': {
          'by_season': {
            'title': 'Theo Mùa',
            'slices': [
              {
                'label': 'M2-4 2025',
                'value': '500,000,000',
                'color': '#0D6EFD',
                'percentage': 40.0,
              },
              {
                'label': 'M5-7 2025',
                'value': '300,000,000',
                'color': '#FF6B6B',
                'percentage': 24.0,
              },
            ],
          },
          'by_grade': {
            'title': 'Theo Hạng',
            'slices': [
              {
                'label': 'Diamond',
                'value': '200,000,000',
                'color': '#20C997',
                'percentage': 16.0,
              },
            ],
          },
        },
        if (includeTrend)
          'trend': [
            {'label': 'T1/2025', 'value': 100000000.0},
            {'label': 'T2/2025', 'value': 120000000.0},
          ],
      };

  test('happy path → ChartPayload with donuts deserialized', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    final payload = await service.getSalesChartData();

    expect(payload.donuts.length, 2);
    expect(payload.donuts.first.title, 'Theo Mùa');
    expect(payload.donuts.first.slices.length, 2);
    expect(payload.donuts.first.slices.first.label, 'M2-4 2025');
  });

  test('donut slice colors preserved as hex strings', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    final payload = await service.getSalesChartData();

    final slice = payload.donuts.first.slices.first;
    expect(slice.color, '#0D6EFD');
    expect(slice.color.startsWith('#'), isTrue);
  });

  test('null trend in response → ChartPayload.trend is null', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: _successPayload(includeTrend: false),
            ));

    final payload = await service.getSalesChartData();

    expect(payload.trend, isNull);
  });

  test('trend present → ChartPayload.trend has correct points', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: _successPayload(includeTrend: true),
            ));

    final payload = await service.getSalesChartData();

    expect(payload.trend, isNotNull);
    expect(payload.trend!.length, 2);
    expect(payload.trend!.first.label, 'T1/2025');
  });

  test('getCustomerChartData → calls customer chart endpoint', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/customer/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    final payload = await service.getCustomerChartData();

    expect(payload.donuts, isNotEmpty);
  });

  test('getCouponChartData → calls coupon chart endpoint', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/coupon/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    final payload = await service.getCouponChartData();

    expect(payload.donuts, isNotEmpty);
  });

  test('403 → PermissionException', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
            statusCode: 403,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(
      () => service.getSalesChartData(),
      throwsA(isA<PermissionException>()),
    );
  });

  test('500 → ApiException', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
            statusCode: 500,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(
      () => service.getSalesChartData(),
      throwsA(isA<ApiException>()),
    );
  });
}
