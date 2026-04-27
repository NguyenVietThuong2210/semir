import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/features/analytics/coupon/coupon_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';

import 'coupon_service_test.mocks.dart';

@GenerateMocks([Dio])
void main() {
  late MockDio mockDio;
  late CouponService service;

  setUp(() {
    mockDio = MockDio();
    service = CouponService(dio: mockDio);
  });

  Map<String, dynamic> _successPayload() => {
        'all_time_kpis': {
          'Tổng coupon': '10,000',
          'Đã dùng': '6,500',
        },
        'period_kpis': {
          'Coupon kỳ': '2,000',
          'Đã dùng kỳ': '1,200',
        },
        'tabs': {
          'by_shop': {
            'label': 'Theo Cửa hàng',
            'headers': ['Cửa hàng', 'Số coupon'],
            'rows': [
              ['HN01', '500'],
            ],
          },
        },
      };

  test('happy path → CouponAnalyticsPayload with correct kpis and tabs', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    final payload = await service.getCouponData();

    expect(payload.allTimeKpis.length, 2);
    expect(payload.periodKpis.length, 2);
    expect(payload.tabs.length, 1);
    expect(payload.tabs.first.label, 'Theo Cửa hàng');
  });

  test('prefix filter → API called with prefix= query param', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getCouponData(prefix: 'SD2025');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>>((p) => p['prefix'] == 'SD2025'),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('null prefix → no prefix param in query', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getCouponData(prefix: null);

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>?>((p) => p == null || !p.containsKey('prefix')),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('empty string prefix → no prefix param in query', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getCouponData(prefix: '');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>?>((p) => p == null || !p.containsKey('prefix')),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('shopGroup "All" → no shop_group param', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenAnswer((_) async => Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
              statusCode: 200,
              data: _successPayload(),
            ));

    await service.getCouponData(shopGroup: 'All');

    verify(mockDio.get(
      any,
      queryParameters: argThat(
        predicate<Map<String, dynamic>?>((p) => p == null || !p.containsKey('shop_group')),
        named: 'queryParameters',
      ),
    )).called(1);
  });

  test('403 → PermissionException', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
            statusCode: 403,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(() => service.getCouponData(), throwsA(isA<PermissionException>()));
  });

  test('500 → ApiException', () async {
    when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
        .thenThrow(DioException(
          requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/analytics/coupon/'),
            statusCode: 500,
          ),
          type: DioExceptionType.badResponse,
        ));

    expect(() => service.getCouponData(), throwsA(isA<ApiException>()));
  });
}
