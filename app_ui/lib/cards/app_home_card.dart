import 'package:flutter/material.dart';

import '../tokens/app_colors.dart';
import '../tokens/app_radius.dart';
import '../tokens/app_shadows.dart';
import '../tokens/app_spacing.dart';

/// Shared card style for the Revolut-style home screen.
abstract class HomeCardStyle {
  /// Standard home card — elevated, no border, radius 20.
  static BoxDecoration surface(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    return BoxDecoration(
      color: isLight ? AppColors.white : AppColors.surfaceDark,
      borderRadius: HomeRadius.cardBR,
      boxShadow: HomeShadows.card,
    );
  }

  /// Large card (student card area) — elevated, radius 24.
  static BoxDecoration surfaceLg(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    return BoxDecoration(
      color: isLight ? AppColors.white : AppColors.surfaceDark,
      borderRadius: HomeRadius.cardLgBR,
      boxShadow: HomeShadows.floating,
    );
  }

  /// Wraps [child] in a standard card container.
  static Widget wrap({
    required BuildContext context,
    required Widget child,
    EdgeInsets? padding,
    VoidCallback? onTap,
  }) {
    final inner = Container(
      padding: padding ?? HomeSpacing.card,
      decoration: surface(context),
      child: child,
    );
    if (onTap == null) return inner;
    return GestureDetector(onTap: onTap, child: inner);
  }
}
