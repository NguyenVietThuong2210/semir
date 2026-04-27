import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

enum KpiVariant { allTime, period }

/// KPI stat card.
/// allTime variant: orange tint background (matches web All-Time stat cards)
/// period variant: blue tint background (matches web Period stat cards)
/// All text uses AppColors.textDark — never white on tinted bg.
class KpiCard extends StatelessWidget {
  const KpiCard({
    super.key,
    required this.label,
    required this.value,
    required this.variant,
  });

  final String label;
  final String value;
  final KpiVariant variant;

  @override
  Widget build(BuildContext context) {
    final bg = variant == KpiVariant.allTime
        ? AppColors.allTimeCardBg
        : AppColors.periodCardBg;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(10),
        boxShadow: const [
          BoxShadow(
            color: Color(0x10000000),
            blurRadius: 6,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label.toUpperCase(),
            style: const TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: AppColors.textMuted,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            value,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: AppColors.textDark,
              height: 1.1,
            ),
          ),
        ],
      ),
    );
  }
}
