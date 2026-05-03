import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import 'chart_service.dart';

class DonutCard extends StatefulWidget {
  const DonutCard({
    super.key,
    required this.chart,
    this.onSliceTapped,
    this.highlightedLabel,
  });

  final DonutChart chart;
  final ValueChanged<String>? onSliceTapped;
  final String? highlightedLabel;

  @override
  State<DonutCard> createState() => _DonutCardState();
}

class _DonutCardState extends State<DonutCard> {
  int? _touchedIndex;

  Color _parseHex(String hex) {
    final h = hex.replaceFirst('#', '');
    try {
      return Color(int.parse('FF$h', radix: 16));
    } catch (_) {
      return AppColors.primary;
    }
  }

  @override
  Widget build(BuildContext context) {
    final slices = widget.chart.slices;
    if (slices.isEmpty) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Center(
            child: Text(widget.chart.title,
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ),
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.chart.title,
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 160,
              child: PieChart(
                PieChartData(
                  sections: List.generate(slices.length, (i) {
                    final slice = slices[i];
                    final isHighlighted =
                        widget.highlightedLabel == slice.label;
                    final isTouched = _touchedIndex == i;
                    final radius = (isTouched || isHighlighted) ? 65.0 : 55.0;
                    return PieChartSectionData(
                      value: math.max(slice.percentage, 0.1),
                      color: _parseHex(slice.color),
                      radius: radius,
                      title: '',
                      showTitle: false,
                    );
                  }),
                  pieTouchData: PieTouchData(
                    touchCallback: (event, response) {
                      if (!event.isInterestedForInteractions) {
                        setState(() => _touchedIndex = null);
                        return;
                      }
                      final idx = response?.touchedSection?.touchedSectionIndex;
                      setState(() => _touchedIndex = idx);
                      if (idx != null && idx >= 0 && idx < slices.length) {
                        widget.onSliceTapped?.call(slices[idx].label);
                      }
                    },
                  ),
                  centerSpaceRadius: 35,
                ),
              ),
            ),
            const SizedBox(height: 8),
            // Legend
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: slices.map((s) {
                final isActive = widget.highlightedLabel == s.label;
                return Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        color: _parseHex(s.color),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '${s.label}: ${s.value}',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: isActive
                            ? FontWeight.bold
                            : FontWeight.normal,
                        color: isActive ? AppColors.primary : AppColors.textMuted,
                      ),
                    ),
                  ],
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }
}
