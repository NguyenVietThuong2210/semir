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

  // API returns donuts as a LIST (not a map).
  // Each slice has value as pre-formatted string + percentage as double.
  Map<String, dynamic> successPayload({bool includeTrend = true}) => {
        'donuts': [
          {
            'title': 'Theo Mùa',
            'slices': [
              {
                'label': 'M2-4 2025',
                'value': '500,000,000',
                'color': '#0D6EFD',
                'percentage': 62.5,
              },
              {
                'label': 'M5-7 2025',
                'value': '300,000,000',
                'color': '#6610F2',
                'percentage': 37.5,
              },
            ],
          },
          {
            'title': 'Theo Hạng',
            'slices': [
              {
                'label': 'Diamond',
                'value': '200,000,000',
                'color': '#20C997',
                'percentage': 100.0,
              },
            ],
          },
        ],
        if (includeTrend)
          'trend': [
            {'label': 'T1/2025', 'value': 85.5},
            {'label': 'T2/2025', 'value': 88.2},
          ],
      };

  test('happy path → ChartPayload with donuts deserialized', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: successPayload(),
            ));

    final payload = await service.getSalesChartData();

    expect(payload.donuts.length, 2);
    expect(payload.donuts.first.title, 'Theo Mùa');
    expect(payload.donuts.first.slices.length, 2);
    expect(payload.donuts.first.slices.first.label, 'M2-4 2025');
  });

  test('donut slice values are pre-formatted strings', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: successPayload(),
            ));

    final payload = await service.getSalesChartData();

    expect(payload.donuts.first.slices.first.value, '500,000,000');
  });

  test('donut slice colors preserved as hex strings', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: successPayload(),
            ));

    final payload = await service.getSalesChartData();

    final slice = payload.donuts.first.slices.first;
    expect(slice.color, '#0D6EFD');
    expect(slice.color.startsWith('#'), isTrue);
  });

  test('donut slice percentage is numeric and non-negative', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: successPayload(),
            ));

    final payload = await service.getSalesChartData();

    for (final donut in payload.donuts) {
      for (final slice in donut.slices) {
        expect(slice.percentage, isNonNegative);
        expect(slice.percentage, lessThanOrEqualTo(100.0));
      }
    }
    expect(payload.donuts.first.slices.first.percentage, 62.5);
  });

  test('null trend in response → ChartPayload.trend is null', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: successPayload(includeTrend: false),
            ));

    final payload = await service.getSalesChartData();

    expect(payload.trend, isNull);
  });

  test('trend present → ChartPayload.trend has correct points', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: successPayload(includeTrend: true),
            ));

    final payload = await service.getSalesChartData();

    expect(payload.trend, isNotNull);
    expect(payload.trend!.length, 2);
    expect(payload.trend!.first.label, 'T1/2025');
    expect(payload.trend!.first.value, 85.5);
  });

  test('empty donuts list → payload.donuts is empty', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/sales/'),
              statusCode: 200,
              data: {'donuts': [], 'trend': null},
            ));

    final payload = await service.getSalesChartData();

    expect(payload.donuts, isEmpty);
    expect(payload.trend, isNull);
  });

  test('getCustomerChartData → calls customer chart endpoint', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/customer/'),
              statusCode: 200,
              data: successPayload(),
            ));

    final payload = await service.getCustomerChartData();

    expect(payload.donuts, isNotEmpty);
  });

  test('getCouponChartData → calls coupon chart endpoint', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/charts/coupon/'),
              statusCode: 200,
              data: successPayload(),
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
