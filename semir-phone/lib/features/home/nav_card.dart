import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

class NavCard extends StatelessWidget {
  const NavCard({
    super.key,
    required this.title,
    required this.description,
    required this.icon,
    required this.onTap,
    this.hasAccess = true,
    this.accentColor = AppColors.primary,
  });

  final String title;
  final String description;
  final IconData icon;
  final VoidCallback? onTap;
  final bool hasAccess;

  /// Top-border + icon color. Each section gets a distinct accent.
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    final effectiveAccent = hasAccess ? accentColor : Colors.grey;

    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: hasAccess ? onTap : null,
        child: Container(
          constraints: const BoxConstraints(minHeight: 84),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border(
              top: BorderSide(color: effectiveAccent, width: 4),
            ),
          ),
          padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: effectiveAccent.withAlpha(18),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: effectiveAccent, size: 22),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            color:
                                hasAccess ? AppColors.textDark : Colors.grey,
                            fontWeight: FontWeight.w700,
                            fontSize: 14,
                          ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      hasAccess ? description : 'No access',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppColors.textMuted,
                            fontSize: 12,
                          ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              if (hasAccess)
                Icon(Icons.chevron_right,
                    color: effectiveAccent.withAlpha(120), size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
