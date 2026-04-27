import 'package:flutter_test/flutter_test.dart';
import 'package:semir_phone/shared/utils/date_utils.dart';

void main() {
  group('computeDateRange', () {
    test('currentYear → Jan 1 to Dec 31 of this year', () {
      final year = DateTime.now().year;
      final range = computeDateRange(DatePreset.currentYear);
      expect(range.dateFrom, DateTime(year, 1, 1));
      expect(range.dateTo, DateTime(year, 12, 31));
    });

    test('previousYear → Jan 1 to Dec 31 of last year', () {
      final year = DateTime.now().year - 1;
      final range = computeDateRange(DatePreset.previousYear);
      expect(range.dateFrom, DateTime(year, 1, 1));
      expect(range.dateTo, DateTime(year, 12, 31));
    });

    test('Last30Days → dateFrom exactly 29 days before today', () {
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);
      final range = computeDateRange(DatePreset.last30Days);
      expect(range.dateTo, today);
      expect(range.dateFrom, today.subtract(const Duration(days: 29)));
    });

    test('Last7Days → dateFrom exactly 6 days before today', () {
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);
      final range = computeDateRange(DatePreset.last7Days);
      expect(range.dateTo, today);
      expect(range.dateFrom, today.subtract(const Duration(days: 6)));
    });

    test('ThisMonth → first day of current month to today', () {
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);
      final range = computeDateRange(DatePreset.thisMonth);
      expect(range.dateFrom, DateTime(now.year, now.month, 1));
      expect(range.dateTo, today);
    });

    test('dateFrom ≤ dateTo for all presets', () {
      for (final preset in DatePreset.values) {
        final range = computeDateRange(preset);
        expect(
          range.dateFrom.isBefore(range.dateTo) ||
              range.dateFrom == range.dateTo,
          isTrue,
          reason: '$preset: dateFrom must be ≤ dateTo',
        );
      }
    });

    test('fromParam formats as YYYY-MM-DD', () {
      final year = DateTime.now().year;
      final range = computeDateRange(DatePreset.currentYear);
      expect(range.fromParam, '$year-01-01');
      expect(range.toParam, '$year-12-31');
    });
  });
}
