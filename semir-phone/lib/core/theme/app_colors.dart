import 'package:flutter/material.dart';

/// Design token constants mirroring web CSS variables.
/// All colors reference this file — never hardcode hex in widgets.
abstract final class AppColors {
  /// Primary blue: web --primary / #0d6efd
  static const Color primary = Color(0xFF0D6EFD);

  /// Navigation bar background: web --nav-bg
  static const Color navBg = Color(0xFF0A58CA);

  /// All-Time KPI card background: web rgba(var(--orange-rgb), .08)
  static const Color allTimeCardBg = Color(0x14FD7E14);

  /// Period KPI card background: web rgba(var(--primary-rgb), .09)
  static const Color periodCardBg = Color(0x170D6EFD);

  /// Main text: web --text
  static const Color textDark = Color(0xFF212529);

  /// Muted text
  static const Color textMuted = Color(0xFF6C757D);

  /// Card/surface background
  static const Color surface = Color(0xFFFFFFFF);

  /// Page scaffold background
  static const Color background = Color(0xFFF8F9FA);

  /// Error / danger
  static const Color error = Color(0xFFDC3545);

  /// White — for text on dark backgrounds
  static const Color white = Color(0xFFFFFFFF);

  // ── Mobile-specific tokens ──────────────────────────────────────────────

  /// Section label strip background (left-accent style — replaces full blue band)
  static const Color sectionLightBg = Color(0xFFF0F4FF);

  /// Tab bar tray background (pill-style tabs)
  static const Color tabBarBg = Color(0xFFF0F2F5);

  /// Subtle card / input border
  static const Color cardBorder = Color(0xFFE9ECEF);

  // ── Per-section accent colors (NavCard icons + borders) ─────────────────

  static const Color accentBlue   = primary;
  static const Color accentGreen  = Color(0xFF198754);
  static const Color accentOrange = Color(0xFFFD7E14);
  static const Color accentPurple = Color(0xFF6F42C1);
  static const Color accentTeal   = Color(0xFF20C997);
}
