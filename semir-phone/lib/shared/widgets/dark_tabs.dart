import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

/// Pill-style tab bar on a light tray background.
/// Active tab: white pill with primary text + subtle shadow.
/// Inactive tab: muted text, no background.
class DarkTabs extends StatelessWidget {
  const DarkTabs({
    super.key,
    required this.tabs,
    required this.selectedIndex,
    required this.onTabSelected,
  });

  final List<String> tabs;
  final int selectedIndex;
  final ValueChanged<int> onTabSelected;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.tabBarBg,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: List.generate(tabs.length, (i) {
            final isActive = i == selectedIndex;
            return Semantics(
              label: tabs[i],
              selected: isActive,
              button: true,
              child: GestureDetector(
                onTap: () => onTabSelected(i),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  margin: const EdgeInsets.symmetric(horizontal: 3),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                  decoration: BoxDecoration(
                    color: isActive ? AppColors.white : Colors.transparent,
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: isActive
                        ? [
                            const BoxShadow(
                              color: Color(0x1A000000),
                              blurRadius: 4,
                              offset: Offset(0, 1),
                            )
                          ]
                        : null,
                  ),
                  child: Text(
                    tabs[i],
                    style: TextStyle(
                      color: isActive ? AppColors.primary : AppColors.textMuted,
                      fontWeight:
                          isActive ? FontWeight.w600 : FontWeight.normal,
                      fontSize: 13,
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
