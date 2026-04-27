import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../utils/date_utils.dart';

class DateRangeFilter {
  const DateRangeFilter({this.dateFrom, this.dateTo, this.preset});
  final DateTime? dateFrom;
  final DateTime? dateTo;
  final DatePreset? preset;

  DateRangeFilter copyWith({
    DateTime? dateFrom,
    DateTime? dateTo,
    DatePreset? preset,
  }) =>
      DateRangeFilter(
        dateFrom: dateFrom ?? this.dateFrom,
        dateTo: dateTo ?? this.dateTo,
        preset: preset ?? this.preset,
      );

  String? get fromParam {
    if (dateFrom == null) return null;
    return '${dateFrom!.year}-${dateFrom!.month.toString().padLeft(2, '0')}-${dateFrom!.day.toString().padLeft(2, '0')}';
  }

  String? get toParam {
    if (dateTo == null) return null;
    return '${dateTo!.year}-${dateTo!.month.toString().padLeft(2, '0')}-${dateTo!.day.toString().padLeft(2, '0')}';
  }
}

class DateFilterBar extends StatefulWidget {
  const DateFilterBar({
    super.key,
    required this.onFilterChanged,
    this.initialFilter = const DateRangeFilter(),
  });

  final ValueChanged<DateRangeFilter> onFilterChanged;
  final DateRangeFilter initialFilter;

  @override
  State<DateFilterBar> createState() => _DateFilterBarState();
}

class _DateFilterBarState extends State<DateFilterBar> {
  late DateRangeFilter _filter;

  static List<(DatePreset, String)> get _presets {
    final year = DateTime.now().year;
    return [
      (DatePreset.last7Days, 'Last 7 Days'),
      (DatePreset.last30Days, 'Last 30 Days'),
      (DatePreset.thisMonth, 'This Month'),
      (DatePreset.lastMonth, 'Last Month'),
      (DatePreset.thisYear, 'This Year'),
      (DatePreset.currentYear, 'Year $year'),
      (DatePreset.previousYear, 'Year ${year - 1}'),
    ];
  }

  @override
  void initState() {
    super.initState();
    _filter = widget.initialFilter;
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: DropdownButtonFormField<DatePreset>(
              initialValue: _filter.preset,
              decoration: const InputDecoration(
                labelText: 'Time Filter',
                isDense: true,
                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              ),
              items: [
                const DropdownMenuItem<DatePreset>(
                  value: null,
                  child: Text('All Time'),
                ),
                ..._presets.map(
                  (p) => DropdownMenuItem(value: p.$1, child: Text(p.$2)),
                ),
              ],
              onChanged: (preset) {
                final range =
                    preset != null ? computeDateRange(preset) : null;
                final updated = DateRangeFilter(
                  dateFrom: range?.dateFrom,
                  dateTo: range?.dateTo,
                  preset: preset,
                );
                setState(() => _filter = updated);
                widget.onFilterChanged(updated);
              },
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.primary,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            ),
            onPressed: () => widget.onFilterChanged(_filter),
            child: const Text('Apply', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }
}
