enum DatePreset {
  last7Days,
  last30Days,
  last90Days,
  lastMonth,
  thisMonth,
  thisYear,
  currentYear,  // full calendar year for DateTime.now().year
  previousYear, // full calendar year for DateTime.now().year - 1
}

class DateRange {
  const DateRange({required this.dateFrom, required this.dateTo});
  final DateTime dateFrom;
  final DateTime dateTo;

  String get fromParam =>
      '${dateFrom.year}-${dateFrom.month.toString().padLeft(2, '0')}-${dateFrom.day.toString().padLeft(2, '0')}';
  String get toParam =>
      '${dateTo.year}-${dateTo.month.toString().padLeft(2, '0')}-${dateTo.day.toString().padLeft(2, '0')}';
}

DateRange computeDateRange(DatePreset preset) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);

  switch (preset) {
    case DatePreset.last7Days:
      return DateRange(
        dateFrom: today.subtract(const Duration(days: 6)),
        dateTo: today,
      );
    case DatePreset.last30Days:
      return DateRange(
        dateFrom: today.subtract(const Duration(days: 29)),
        dateTo: today,
      );
    case DatePreset.last90Days:
      return DateRange(
        dateFrom: today.subtract(const Duration(days: 89)),
        dateTo: today,
      );
    case DatePreset.lastMonth:
      final firstOfThisMonth = DateTime(now.year, now.month, 1);
      final lastOfLastMonth =
          firstOfThisMonth.subtract(const Duration(days: 1));
      final firstOfLastMonth =
          DateTime(lastOfLastMonth.year, lastOfLastMonth.month, 1);
      return DateRange(dateFrom: firstOfLastMonth, dateTo: lastOfLastMonth);
    case DatePreset.thisMonth:
      return DateRange(
        dateFrom: DateTime(now.year, now.month, 1),
        dateTo: today,
      );
    case DatePreset.thisYear:
      return DateRange(
        dateFrom: DateTime(now.year, 1, 1),
        dateTo: today,
      );
    case DatePreset.currentYear:
      return DateRange(
        dateFrom: DateTime(now.year, 1, 1),
        dateTo: DateTime(now.year, 12, 31),
      );
    case DatePreset.previousYear:
      return DateRange(
        dateFrom: DateTime(now.year - 1, 1, 1),
        dateTo: DateTime(now.year - 1, 12, 31),
      );
  }
}
