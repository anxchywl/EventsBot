import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';

/// Generic card widget with consistent styling.
/// Use as a container for content sections.
/// 
/// Example:
/// ```dart
/// AppCard(
///   child: Column(
///     children: [
///       Text('Card Title'),
///       Text('Card Content'),
///     ],
///   ),
/// )
/// ```
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding,
    this.margin,
    this.backgroundColor,
    this.borderRadius,
    this.elevation = 0,
    this.border,
    this.onTap,
    this.width,
    this.height,
    this.clipBehavior = Clip.none,
  });

  /// Card content.
  final Widget child;

  /// Card padding (defaults to AppSpacing.cardPadding).
  final EdgeInsets? padding;

  /// Card margin.
  final EdgeInsets? margin;

  /// Background color.
  final Color? backgroundColor;

  /// Border radius.
  final BorderRadius? borderRadius;

  /// Card elevation/shadow.
  final double elevation;

  /// Optional border.
  final BoxBorder? border;

  /// Tap callback.
  final VoidCallback? onTap;

  /// Fixed width.
  final double? width;

  /// Fixed height.
  final double? height;

  /// Clip behavior.
  final Clip clipBehavior;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;

    final effectiveBorderRadius = borderRadius ?? AppSpacing.borderRadiusDf;
    final effectiveBackgroundColor = backgroundColor 
        ?? (isLight ? AppColors.white : AppColors.surfaceDark);

    final cardDecoration = BoxDecoration(
      color: effectiveBackgroundColor,
      borderRadius: effectiveBorderRadius,
      border: border,
    );

    Widget cardContent = Container(
      width: width,
      height: height,
      padding: padding ?? AppSpacing.cardPadding,
      margin: margin,
      decoration: cardDecoration,
      clipBehavior: clipBehavior,
      child: child,
    );

    if (onTap != null) {
      return Material(
        color: AppColors.transparent,
        borderRadius: effectiveBorderRadius,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          borderRadius: effectiveBorderRadius,
          child: cardContent,
        ),
      );
    }

    return cardContent;
  }
}

/// Card with header and content sections.
class AppCardWithHeader extends StatelessWidget {
  const AppCardWithHeader({
    super.key,
    required this.title,
    required this.child,
    this.subtitle,
    this.trailing,
    this.padding,
    this.backgroundColor,
    this.borderRadius,
    this.elevation = 0,
    this.onTap,
    this.onHeaderTap,
  });

  /// Header title.
  final String title;

  /// Optional subtitle.
  final String? subtitle;

  /// Card content below the header.
  final Widget child;

  /// Trailing widget in header (e.g., action button).
  final Widget? trailing;

  /// Card padding.
  final EdgeInsets? padding;

  /// Background color.
  final Color? backgroundColor;

  /// Border radius.
  final BorderRadius? borderRadius;

  /// Card elevation.
  final double elevation;

  /// Tap callback for the entire card.
  final VoidCallback? onTap;

  /// Tap callback for just the header.
  final VoidCallback? onHeaderTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final textColor = isLight ? AppColors.textPrimary : AppColors.textPrimaryDark;

    return AppCard(
      backgroundColor: backgroundColor,
      borderRadius: borderRadius,
      elevation: elevation,
      onTap: onTap,
      padding: AppSpacing.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header
          InkWell(
            onTap: onHeaderTap,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(AppSpacing.radiusDf),
              topRight: Radius.circular(AppSpacing.radiusDf),
            ),
            child: Padding(
              padding: padding ?? AppSpacing.cardPadding,
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: theme.textTheme.titleMedium?.copyWith(
                            color: textColor,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        if (subtitle != null) ...[
                          AppSpacing.verticalXs,
                          Text(
                            subtitle!,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: AppColors.grey,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  ?trailing,
                ],
              ),
            ),
          ),
          // Content
          Padding(
            padding: (padding ?? AppSpacing.cardPadding).copyWith(top: 0),
            child: child,
          ),
        ],
      ),
    );
  }
}
