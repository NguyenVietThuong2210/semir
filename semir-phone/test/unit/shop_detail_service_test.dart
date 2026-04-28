import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/features/analytics/customer_detail/customer_detail_service.dart'
    show NotFoundException;
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

  // ── getShops ──────────────────────────────────────────────────────────────

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

  // ── getShopSales ──────────────────────────────────────────────────────────

  group('getShopSales', () {
    Map<String, dynamic> salesPayload() => {
          'shop_name': 'HN01',
          'sales': {
            'all_time_kpis': {
              'Active': '1,234',
              'Returning': '890',
              'Return Rate': '72.12%',
              'INV(RET)': '1,500',
              'AMT(RET)': '5,000,000,000',
              'Total INV': '2,000',
              'Total Amt (VND)': '8,000,000,000',
            },
            'period_kpis': {
              'Active': '400',
              'Returning': '280',
              'Return Rate': '70.00%',
              'INV(RET)': '500',
              'AMT(RET)': '1,200,000,000',
              'Total INV': '700',
              'Total Amt (VND)': '2,000,000,000',
            },
            'by_session': {'headers': ['Season', 'Active'], 'rows': []},
            'by_month': {'headers': ['Month', 'Active'], 'rows': []},
            'by_week': {'headers': ['Week', 'Active'], 'rows': []},
          },
        };

    test('happy path → ShopSalesPayload with KPIs', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: salesPayload(),
              ));

      final payload = await service.getShopSales(shop: 'HN01');

      expect(payload.allTimeKpis, isNotEmpty);
      expect(payload.allTimeKpis.first.label, 'Active');
      expect(payload.allTimeKpis.first.value, '1,234');
      expect(payload.periodKpis, isNotEmpty);
    });

    test('shop + date params sent in query string', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: salesPayload(),
              ));

      await service.getShopSales(
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

    test('null dateFrom/dateTo → not included in params', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: salesPayload(),
              ));

      await service.getShopSales(shop: 'HN01');

      verify(mockDio.get(
        any,
        queryParameters: argThat(
          predicate<Map<String, dynamic>>((p) =>
              !p.containsKey('date_from') && !p.containsKey('date_to')),
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
        () => service.getShopSales(shop: 'HN01'),
        throwsA(isA<PermissionException>()),
      );
    });

    test('404 → NotFoundException', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenThrow(DioException(
            requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
            response: Response(
              requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
              statusCode: 404,
            ),
            type: DioExceptionType.badResponse,
          ));

      expect(
        () => service.getShopSales(shop: '__not_found__'),
        throwsA(isA<NotFoundException>()),
      );
    });
  });

  // ── getShopCustomer ───────────────────────────────────────────────────────

  group('getShopCustomer', () {
    Map<String, dynamic> customerPayload() => {
          'shop_name': 'HN01',
          'customer': {
            'all_time_kpis': {
              'New POS': '1,234',
              'POS (w/ INV)': '900',
              'New CNV': '800',
              'POS Only': '434',
              'CNV Only': '100',
              'Zalo App': '600',
              'Zalo OA': '200',
            },
            'period_kpis': {
              'New POS': '100',
              'POS (w/ INV)': '70',
              'New CNV': '60',
              'POS Only': '40',
              'CNV Only': '15',
              'Zalo App': '50',
              'Zalo OA': '20',
            },
            'by_season': {
              'headers': ['Period', 'POS(INV)', 'POS(NO INV)', 'POS Total',
                          'POS Only', 'New CNV', 'CNV Only', 'Zalo App',
                          '%App', 'Zalo OA', '%OA'],
              'rows': [],
            },
            'by_month': {'headers': ['Period'], 'rows': []},
            'by_week': {'headers': ['Period'], 'rows': []},
          },
        };

    test('happy path → ShopCustomerPayload with 7 KPI cards', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: customerPayload(),
              ));

      final payload = await service.getShopCustomer(shop: 'HN01');

      expect(payload.allTimeKpis.length, 7);
      expect(payload.allTimeKpis.map((k) => k.label),
          containsAll(['New POS', 'POS (w/ INV)', 'New CNV', 'POS Only',
                       'CNV Only', 'Zalo App', 'Zalo OA']));
    });

    test('section=customer param sent in query', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: customerPayload(),
              ));

      await service.getShopCustomer(shop: 'HN01');

      verify(mockDio.get(
        any,
        queryParameters: argThat(
          predicate<Map<String, dynamic>>((p) => p['section'] == 'customer'),
          named: 'queryParameters',
        ),
      )).called(1);
    });
  });

  // ── getShopCoupon ─────────────────────────────────────────────────────────

  group('getShopCoupon', () {
    Map<String, dynamic> couponPayload() => {
          'shop_name': 'HN01',
          'coupon': {
            'all_time_kpis': {
              'Total Coupons': '500',
              'Used': '300',
              'Unused': '200',
              'Total Amount (VND)': '15,000,000',
              'Coupon Amount (VND)': '10,000,000',
              'Unique Invoice Amt (VND)': '12,000,000',
            },
            'period_kpis': {
              'Total Coupons': '100',
              'Used': '60',
              'Unused': '40',
              'Total Amount (VND)': '3,000,000',
              'Coupon Amount (VND)': '2,000,000',
              'Unique Invoice Amt (VND)': '2,500,000',
            },
            'detail_table': null,
          },
        };

    test('happy path → ShopCouponPayload with 6 KPI cards', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: couponPayload(),
              ));

      final payload = await service.getShopCoupon(shop: 'HN01');

      expect(payload.allTimeKpis.length, 6);
      expect(payload.allTimeKpis.map((k) => k.label),
          containsAll(['Total Coupons', 'Used', 'Unused',
                       'Total Amount (VND)', 'Coupon Amount (VND)',
                       'Unique Invoice Amt (VND)']));
    });

    test('Used + Unused == Total Coupons (parity check)', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: couponPayload(),
              ));

      final payload = await service.getShopCoupon(shop: 'HN01');

      int parse(String v) => int.tryParse(v.replaceAll(',', '')) ?? 0;
      final at = {for (final k in payload.allTimeKpis) k.label: k.value};
      final total  = parse(at['Total Coupons'] ?? '0');
      final used   = parse(at['Used'] ?? '0');
      final unused = parse(at['Unused'] ?? '0');
      if (total > 0) expect(used + unused, total);
    });

    test('section=coupon param sent in query', () async {
      when(mockDio.get(any, queryParameters: anyNamed('queryParameters')))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: '/api/v1/analytics/shop-detail/'),
                statusCode: 200,
                data: couponPayload(),
              ));

      await service.getShopCoupon(shop: 'HN01');

      verify(mockDio.get(
        any,
        queryParameters: argThat(
          predicate<Map<String, dynamic>>((p) => p['section'] == 'coupon'),
          named: 'queryParameters',
        ),
      )).called(1);
    });
  });
}
