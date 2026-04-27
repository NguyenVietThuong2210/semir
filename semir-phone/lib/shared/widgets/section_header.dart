import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

/// Section label strip — 4px primary left-accent on light blue tint.
/// Mobile adaptation: avoids full-blue bands that cause visual fatigue
/// when multiple section headers stack on a single screen.
class SectionHeader extends StatelessWidget {
  const SectionHeader({super.key, required this.title});
  final String title;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 10, 16, 10),
      decoration: const BoxDecoration(
        color: AppColors.sectionLightBg,
        border: Border(
          left: BorderSide(color: AppColors.primary, width: 4),
        ),
      ),
      child: Text(
        title,
        style: const TextStyle(
          color: AppColors.primary,
          fontWeight: FontWeight.w700,
          fontSize: 13,
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}
