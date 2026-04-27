import 'package:flutter_test/flutter_test.dart';
import 'package:semir_phone/shared/utils/vnd_formatter.dart';

void main() {
  group('formatVnd', () {
    test('1234567890 → "1,234,567,890"', () {
      expect(formatVnd(1234567890), '1,234,567,890');
    });

    test('0 → "0"', () {
      expect(formatVnd(0), '0');
    });

    test('1000 → "1,000"', () {
      expect(formatVnd(1000), '1,000');
    });

    test('999 → "999" (no separator below 1000)', () {
      expect(formatVnd(999), '999');
    });

    test('1234567 → "1,234,567"', () {
      expect(formatVnd(1234567), '1,234,567');
    });

    test('double input rounds to nearest integer', () {
      expect(formatVnd(12345.6), '12,346');
    });
  });

  group('formatPercent', () {
    test('45.984 → "45.98%"', () {
      expect(formatPercent(45.984), '45.98%');
    });

    test('100 → "100.00%"', () {
      expect(formatPercent(100), '100.00%');
    });

    test('0 → "0.00%"', () {
      expect(formatPercent(0), '0.00%');
    });

    test('1 decimal place', () {
      expect(formatPercent(33.333, decimals: 1), '33.3%');
    });

    test('50.505 rounds to 50.51%', () {
      expect(formatPercent(50.505), '50.51%');
    });
  });
}
