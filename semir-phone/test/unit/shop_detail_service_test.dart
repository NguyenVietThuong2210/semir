import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/features/analytics/shop_detail/shop_detail_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';

import 'shop_detail_service_test.mocks.dart';

@GenerateMocks([Dio])
void main() {
  late MockDio mockDio;
  late ShopDetailService service;

  setUp(() {
    mockDio = MockDio();
    service = ShopDetailService(dio: mockDio);
  });

  group('getShops', () {
    test('returns list of shop names from response', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shops/'),
                statusCode: 200,
                data: {
                  'shops': ['HN01', 'HN02', 'HCM01'],
                },
              ));

      final shops = await service.getShops();

      expect(shops, ['HN01', 'HN02', 'HCM01']);
    });

    test('empty shops list → returns empty array (not null)', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shops/'),
                statusCode: 200,
                data: {'shops': []},
              ));

      final shops = await service.getShops();

      expect(shops, isA<List<String>>());
      expect(shops, isEmpty);
    });

    test('missing shops key → returns empty array (not null)', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shops/'),
                statusCode: 200,
                data: <String, dynamic>{},
              ));

      final shops = await service.getShops();

      expect(shops, isA<List<String>>());
      expect(shops, isEmpty);
    });

    test('403 → PermissionException', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenThrow(DioException(
            requestOptions: RequestOptions(path: '/api/v1/analytics/shops/'),
            response: Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/shops/'),
              statusCode: 403,
            ),
            type: DioExceptionType.badResponse,
          ));

      expect(() => service.getShops(), throwsA(isA<PermissionException>()));
    });
  });

  group('getShopDetail', () {
    Map<String, dynamic> _shopDetailPayload() => {
          'sales': {
            'all_time_kpis': {
              'Tổng doanh thu': '5,000,000,000',
            },
            'period_kpis': {
              'Doanh thu kỳ': '1,200,000,000',
            },
            'tabs': {
              'by_session': {
                'label': 'Theo Phiên',
                'headers': ['Phiên', 'Doanh thu'],
                'rows': [['SS25', '500,000,000']],
              },
            },
          },
          'customer': {
            'kpis': {'Tổng KH': '1,234'},
            'tabs': {
              'breakdown': {
                'label': 'Breakdown',
                'headers': ['Hạng', 'Số KH'],
                'rows': [['Diamond', '100']],
              },
            },
          },
          'coupon': {
            'kpis': {'Tổng coupon': '500'},
            'tabs': {
              'detail': {
                'label': 'Chi tiết',
                'headers': ['Coupon', 'Trạng thái'],
                'rows': [['SD001', 'Đã dùng']],
              },
            },
          },
        };

    test('getShopDetail happy path → ShopDetailPayload with all 3 sections', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: _shopDetailPayload(),
              ));

      final payload = await service.getShopDetail(shop: 'HN01');

      expect(payload.salesAllTimeKpis.length, 1);
      expect(payload.salesAllTimeKpis.first.label, 'Tổng doanh thu');
      expect(payload.salesPeriodKpis.length, 1);
      expect(payload.salesTabs.length, 1);
      expect(payload.customerKpis.length, 1);
      expect(payload.couponKpis.length, 1);
    });

    test('shop param included in query string', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: _shopDetailPayload(),
              ));

      await service.getShopDetail(
        shop: 'HN01',
        dateFrom: '2025-01-01',
        dateTo: '2025-12-31',
      );

      verify(mockDio.get(
        any,
        queryParameters: argThat(
          predicate<Map<String, dynamic>>((p) =>
              p['shop'] == 'HN01' &&
              p['date_from'] == '2025-01-01' &&
              p['date_to'] == '2025-12-31'),
          named: 'queryParameters',
        ),
      )).called(1);
    });

    test('403 → PermissionException', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenThrow(DioException(
            requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
            response: Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
              statusCode: 403,
            ),
            type: DioExceptionType.badResponse,
          ));

      expect(
        () => service.getShopDetail(shop: 'HN01'),
        throwsA(isA<PermissionException>()),
      );
    });
  });
}
