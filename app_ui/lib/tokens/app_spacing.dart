import 'package:flutter/material.dart';

/// App Spacing - Single source of truth for spacing constants.
/// 
/// Usage:
/// ```dart
/// Padding(padding: AppSpacing.screenPadding)
/// SizedBox(height: AppSpacing.md)
/// Container(decoration: BoxDecoration(borderRadius: AppSpacing.borderRadiusDf))
/// ```
/// 
/// NEVER use raw numbers for EdgeInsets or spacing in feature code.
abstract class AppSpacing {
  // ─────────────────────────────────────────────────────────────────────────────
  // SPACING VALUES
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Extra Small - 4.0
  static const double xs = 4.0;
  
  /// Small - 8.0
  static const double sm = 8.0;
  
  /// Medium - 12.0
  static const double md = 12.0;
  
  /// Default (most common) - 16.0
  static const double df = 16.0;
  
  /// Large - 20.0
  static const double lg = 20.0;
  
  /// Extra Large - 24.0
  static const double xl = 24.0;
  
  /// 2X Large - 32.0
  static const double xxl = 32.0;
  
  /// 3X Large - 48.0
  static const double xxxl = 48.0;
  
  /// 4X Large - 64.0
  static const double xxxxl = 64.0;

  // ─────────────────────────────────────────────────────────────────────────────
  // EDGE INSETS - SCREEN
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Screen padding (all sides) - 16.0
  static const EdgeInsets screenPadding = EdgeInsets.all(df);
  
  /// Screen horizontal padding - 16.0
  static const EdgeInsets screenHorizontal = EdgeInsets.symmetric(horizontal: df);
  
  /// Screen vertical padding - 16.0
  static const EdgeInsets screenVertical = EdgeInsets.symmetric(vertical: df);

  // ─────────────────────────────────────────────────────────────────────────────
  // EDGE INSETS - CARD
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Card padding (default) - 16.0
  static const EdgeInsets cardPadding = EdgeInsets.all(df);
  
  /// Card padding (small) - 12.0
  static const EdgeInsets cardPaddingSm = EdgeInsets.all(md);
  
  /// Card padding (large) - 24.0
  static const EdgeInsets cardPaddingLg = EdgeInsets.all(xl);

  // ─────────────────────────────────────────────────────────────────────────────
  // EDGE INSETS - LIST ITEMS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// List item padding - horizontal: 16, vertical: 12
  static const EdgeInsets listItemPadding = EdgeInsets.symmetric(horizontal: df, vertical: md);
  
  /// List item padding (compact) - horizontal: 16, vertical: 8
  static const EdgeInsets listItemPaddingCompact = EdgeInsets.symmetric(horizontal: df, vertical: sm);
  
  /// List item padding (spacious) - horizontal: 16, vertical: 16
  static const EdgeInsets listItemPaddingSpacious = EdgeInsets.symmetric(horizontal: df, vertical: df);

  // ─────────────────────────────────────────────────────────────────────────────
  // EDGE INSETS - BUTTONS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Button padding - horizontal: 24, vertical: 16
  static const EdgeInsets buttonPadding = EdgeInsets.symmetric(horizontal: xl, vertical: df);
  
  /// Button padding (compact) - horizontal: 16, vertical: 12
  static const EdgeInsets buttonPaddingCompact = EdgeInsets.symmetric(horizontal: df, vertical: md);
  
  /// Icon button padding - all: 12
  static const EdgeInsets iconButtonPadding = EdgeInsets.all(md);

  // ─────────────────────────────────────────────────────────────────────────────
  // EDGE INSETS - DIALOG
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Dialog padding - all: 24
  static const EdgeInsets dialogPadding = EdgeInsets.all(xl);
  
  /// Bottom sheet padding - horizontal: 24, vertical: 16
  static const EdgeInsets bottomSheetPadding = EdgeInsets.symmetric(horizontal: xl, vertical: df);

  // ─────────────────────────────────────────────────────────────────────────────
  // EDGE INSETS - CHIPS / TAGS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Chip padding - horizontal: 12, vertical: 6
  static const EdgeInsets chipPadding = EdgeInsets.symmetric(horizontal: md, vertical: 6);
  
  /// Tag padding (smaller) - horizontal: 8, vertical: 4
  static const EdgeInsets tagPadding = EdgeInsets.symmetric(horizontal: sm, vertical: xs);

  // ─────────────────────────────────────────────────────────────────────────────
  // EDGE INSETS - ZERO
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Zero padding
  static const EdgeInsets zero = EdgeInsets.zero;

  // ─────────────────────────────────────────────────────────────────────────────
  // SIZED BOXES - VERTICAL
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Vertical spacing - 4.0
  static const SizedBox verticalXs = SizedBox(height: xs);
  
  /// Vertical spacing - 8.0
  static const SizedBox verticalSm = SizedBox(height: sm);
  
  /// Vertical spacing - 12.0
  static const SizedBox verticalMd = SizedBox(height: md);
  
  /// Vertical spacing - 16.0
  static const SizedBox verticalDf = SizedBox(height: df);
  
  /// Vertical spacing - 20.0
  static const SizedBox verticalLg = SizedBox(height: lg);
  
  /// Vertical spacing - 24.0
  static const SizedBox verticalXl = SizedBox(height: xl);
  
  /// Vertical spacing - 32.0
  static const SizedBox verticalXxl = SizedBox(height: xxl);
  
  /// Vertical spacing - 48.0
  static const SizedBox verticalXxxl = SizedBox(height: xxxl);

  // ─────────────────────────────────────────────────────────────────────────────
  // SIZED BOXES - HORIZONTAL
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Horizontal spacing - 4.0
  static const SizedBox horizontalXs = SizedBox(width: xs);
  
  /// Horizontal spacing - 8.0
  static const SizedBox horizontalSm = SizedBox(width: sm);
  
  /// Horizontal spacing - 12.0
  static const SizedBox horizontalMd = SizedBox(width: md);
  
  /// Horizontal spacing - 16.0
  static const SizedBox horizontalDf = SizedBox(width: df);
  
  /// Horizontal spacing - 20.0
  static const SizedBox horizontalLg = SizedBox(width: lg);
  
  /// Horizontal spacing - 24.0
  static const SizedBox horizontalXl = SizedBox(width: xl);
  
  /// Horizontal spacing - 32.0
  static const SizedBox horizontalXxl = SizedBox(width: xxl);

  // ─────────────────────────────────────────────────────────────────────────────
  // BORDER RADIUS VALUES
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Border radius - 4.0
  static const double radiusXs = 4.0;
  
  /// Border radius - 8.0
  static const double radiusSm = 8.0;
  
  /// Border radius - 12.0
  static const double radiusMd = 12.0;
  
  /// Border radius (default) - 16.0
  static const double radiusDf = 16.0;
  
  /// Border radius - 20.0
  static const double radiusLg = 20.0;
  
  /// Border radius - 24.0
  static const double radiusXl = 24.0;
  
  /// Border radius (round) - 100.0
  static const double radiusRound = 100.0;

  // ─────────────────────────────────────────────────────────────────────────────
  // BORDER RADIUS GETTERS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// BorderRadius - 4.0
  static BorderRadius get borderRadiusXs => BorderRadius.circular(radiusXs);
  
  /// BorderRadius - 8.0
  static BorderRadius get borderRadiusSm => BorderRadius.circular(radiusSm);
  
  /// BorderRadius - 12.0
  static BorderRadius get borderRadiusMd => BorderRadius.circular(radiusMd);
  
  /// BorderRadius (default) - 16.0
  static BorderRadius get borderRadiusDf => BorderRadius.circular(radiusDf);
  
  /// BorderRadius - 20.0
  static BorderRadius get borderRadiusLg => BorderRadius.circular(radiusLg);
  
  /// BorderRadius - 24.0
  static BorderRadius get borderRadiusXl => BorderRadius.circular(radiusXl);
  
  /// BorderRadius (round) - 100.0
  static BorderRadius get borderRadiusRound => BorderRadius.circular(radiusRound);
  
  /// BorderRadius for top sheet - 24.0 top only
  static BorderRadius get borderRadiusTopSheet => const BorderRadius.vertical(top: Radius.circular(24));
  
  /// BorderRadius for bottom sheet - 24.0 bottom only
  static BorderRadius get borderRadiusBottomSheet => const BorderRadius.vertical(bottom: Radius.circular(24));

  // ─────────────────────────────────────────────────────────────────────────────
  // ICON SIZES
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Icon size - 16.0
  static const double iconSm = 16.0;
  
  /// Icon size - 20.0
  static const double iconMd = 20.0;
  
  /// Icon size (default) - 24.0
  static const double iconDf = 24.0;
  
  /// Icon size - 32.0
  static const double iconLg = 32.0;
  
  /// Icon size - 48.0
  static const double iconXl = 48.0;

  // ─────────────────────────────────────────────────────────────────────────────
  // AVATAR SIZES
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Avatar size - 32.0
  static const double avatarSm = 32.0;
  
  /// Avatar size - 40.0
  static const double avatarMd = 40.0;
  
  /// Avatar size (default) - 48.0
  static const double avatarDf = 48.0;
  
  /// Avatar size - 64.0
  static const double avatarLg = 64.0;
  
  /// Avatar size - 80.0
  static const double avatarXl = 80.0;
  
  /// Avatar size - 100.0
  static const double avatarXxl = 100.0;
  
  /// Avatar size - 120.0
  static const double avatarXxxl = 120.0;

  // ─────────────────────────────────────────────────────────────────────────────
  // BUTTON HEIGHTS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Button height (small) - 40.0
  static const double buttonHeightSm = 40.0;
  
  /// Button height (default) - 48.0
  static const double buttonHeightDf = 48.0;
  
  /// Button height (large) - 56.0
  static const double buttonHeightLg = 56.0;

  // ─────────────────────────────────────────────────────────────────────────────
  // APP BAR HEIGHT
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// AppBar height - 56.0
  static const double appBarHeight = 56.0;

  // ─────────────────────────────────────────────────────────────────────────────
  // DIVIDER THICKNESS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Divider thickness (thin) - 0.5
  static const double dividerThin = 0.5;
  
  /// Divider thickness (default) - 1.0
  static const double dividerDf = 1.0;
  
  /// Divider thickness (thick) - 2.0
  static const double dividerThick = 2.0;
}

// ─────────────────────────────────────────────────────────────────────────────
// HOME SPACING — Revolut-style spacing for the redesigned home screen
// ─────────────────────────────────────────────────────────────────────────────

/// Spacing constants for the Revolut-style home redesign.
/// Extends base AppSpacing with larger, premium-feel values.
abstract class HomeSpacing {
  // ── Screen ────────────────────────────────────────────────────────────────
  static const double screenH = 20.0;
  static const double screenTop = 16.0;
  static const double screenBottom = 24.0;
  static const EdgeInsets screen = EdgeInsets.symmetric(horizontal: screenH);

  // ── Section gaps ──────────────────────────────────────────────────────────
  static const double sectionGap = 28.0;
  static const double rowGap = 20.0;

  // ── Card internals ────────────────────────────────────────────────────────
  static const double cardPadding = 20.0;
  static const EdgeInsets card = EdgeInsets.all(cardPadding);

  // ── Item gaps ─────────────────────────────────────────────────────────────
  static const double storyGap = 14.0;
  static const double itemGap = 12.0;

  // ── AppBar ────────────────────────────────────────────────────────────────
  static const double appBarH = 20.0;
  static const double avatarSize = 36.0;

  // ── Stories ───────────────────────────────────────────────────────────────
  static const double storySize = 64.0;
  static const double storyLabelWidth = 72.0;
  static const double storiesBarHeight = 92.0;

  // ── Navigation bar ────────────────────────────────────────────────────────
  static const double navBarHeight = 60.0;

  // ── SizedBox helpers ──────────────────────────────────────────────────────
  static const SizedBox vSection = SizedBox(height: sectionGap);
  static const SizedBox vRow = SizedBox(height: rowGap);
  static const SizedBox vItem = SizedBox(height: 8.0);
  static const SizedBox hItem = SizedBox(width: itemGap);
}
