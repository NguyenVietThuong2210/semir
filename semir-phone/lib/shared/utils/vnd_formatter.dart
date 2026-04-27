import 'package:intl/intl.dart';

final _vndFormat = NumberFormat('#,###', 'en_US');

/// Formats a number with Vietnamese digit grouping (thousands commas).
/// e.g. formatVnd(1234567890) → "1,234,567,890"
String formatVnd(num value) {
  if (value == 0) return '0';
  return _vndFormat.format(value);
}

/// Formats a decimal as a percentage string with [decimals] decimal places.
/// e.g. formatPercent(45.984) → "45.98%"
String formatPercent(num value, {int decimals = 2}) {
  return '${value.toStringAsFixed(decimals)}%';
}
