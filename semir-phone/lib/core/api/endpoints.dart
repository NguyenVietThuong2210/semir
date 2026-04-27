/// All API URL path constants.
/// Prepend BuildConfig.apiBaseUrl before making a request.
abstract final class Endpoints {
  // Auth
  static const String login = '/auth/token/';
  static const String refresh = '/auth/token/refresh/';
  static const String logout = '/auth/logout/';

  // Analytics
  static const String sales = '/analytics/sales/';
  static const String customer = '/analytics/customer/';
  static const String coupon = '/analytics/coupon/';
  static const String shopDetail = '/analytics/shop-detail/';
  static const String customerDetail = '/analytics/customer-detail/';
  static const String shops = '/analytics/shops/';

  // Charts
  static const String salesChart = '/charts/sales/';
  static const String customerChart = '/charts/customer/';
  static const String couponChart = '/charts/coupon/';
}
