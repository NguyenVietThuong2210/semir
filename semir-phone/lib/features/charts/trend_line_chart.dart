import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import 'chart_service.dart';

/// Renders a trend line chart from a list of [TrendPoint]s.
class TrendLineChart extends StatelessWidget {
  const TrendLineChart({super.key, required this.points});

  final List<TrendPoint> points;

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) return const SizedBox.shrink();

    final spots = List.generate(
      points.length,
      (i) => FlSpot(i.toDouble(), points[i].value),
    );

    final minY = points.map((p) => p.value).reduce((a, b) => a < b ? a : b);
    final maxY = points.map((p) => p.value).reduce((a, b) => a > b ? a : b);
    final yPad = ((maxY - minY) * 0.15).clamp(1.0, double.infinity);

    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 16, 16, 8),
        child: SizedBox(
          height: 200,
          child: LineChart(
            LineChartData(
              minY: (minY - yPad).clamp(0, double.infinity),
              maxY: maxY + yPad,
              gridData: FlGridData(
                show: true,
                drawVerticalLine: false,
                horizontalInterval: yPad * 2,
                getDrawingHorizontalLine: (_) => const FlLine(
                  color: Color(0x1A000000),
                  strokeWidth: 1,
                ),
              ),
              borderData: FlBorderData(show: false),
              titlesData: FlTitlesData(
                topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false)),
                rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false)),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 30,
                    interval: (points.length / 4).ceilToDouble().clamp(1, double.infinity),
                    getTitlesWidget: (value, meta) {
                      final idx = value.toInt();
                      if (idx < 0 || idx >= points.length) {
                        return const SizedBox.shrink();
                      }
                      final label = points[idx].label;
                      return Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          label.length > 6 ? label.substring(label.length - 6) : label,
                          style: const TextStyle(fontSize: 10, color: AppColors.textMuted),
                        ),
                      );
                    },
                  ),
                ),
                leftTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 40,
                    getTitlesWidget: (value, meta) => Text(
                      value.toStringAsFixed(1),
                      style: const TextStyle(fontSize: 9, color: AppColors.textMuted),
                    ),
                  ),
                ),
              ),
              lineBarsData: [
                LineChartBarData(
                  spots: spots,
                  isCurved: true,
                  color: AppColors.primary,
                  barWidth: 2.5,
                  dotData: FlDotData(
                    show: true,
                    getDotPainter: (spot, pct, bar, idx) =>
                        FlDotCirclePainter(
                      radius: 3,
                      color: AppColors.primary,
                      strokeWidth: 0,
                      strokeColor: Colors.transparent,
                    ),
                  ),
                  belowBarData: BarAreaData(
                    show: true,
                    color: AppColors.primary.withAlpha(25),
                  ),
                ),
              ],
              lineTouchData: LineTouchData(
                touchTooltipData: LineTouchTooltipData(
                  getTooltipItems: (touchedSpots) => touchedSpots
                      .map((s) => LineTooltipItem(
                            '${points[s.spotIndex].label}\n${s.y.toStringAsFixed(2)}',
                            const TextStyle(
                                color: Colors.white, fontSize: 11),
                          ))
                      .toList(),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
