import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';
import '../icons/app_icons.dart';
import '../icons/app_icon.dart';

/// List tile widget with consistent styling.
/// Use for settings, menu items, etc.
/// 
/// Example:
/// ```dart
/// AppListTile(
///   title: 'Settings',
///   leading: AppIcon(AppIcons.settings),
///   onTap: () => navigateToSettings(),
/// )
/// ```
class AppListTile extends StatelessWidget {
  const AppListTile({
    super.key,
    required this.title,
    this.subtitle,
    this.leading,
    this.trailing,
    this.onTap,
    this.enabled = true,
    this.showChevron = true,
    this.padding,
    this.backgroundColor,
    this.dense = false,
    this.showDivider = false,
  });

  /// Title text.
  final String title;

  /// Subtitle text.
  final String? subtitle;

  /// Leading widget (icon, avatar, etc.).
  final Widget? leading;

  /// Trailing widget.
  final Widget? trailing;

  /// Tap callback.
  final VoidCallback? onTap;

  /// Whether the tile is enabled.
  final bool enabled;

  /// Whether to show chevron arrow.
  final bool showChevron;

  /// Custom padding.
  final EdgeInsets? padding;

  /// Background color.
  final Color? backgroundColor;

  /// Whether to use dense layout.
  final bool dense;

  /// Whether to show bottom divider.
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final textColor = isLight ? AppColors.textPrimary : AppColors.textPrimaryDark;
    final effectivePadding = padding ?? (dense 
        ? AppSpacing.listItemPaddingCompact 
        : AppSpacing.listItemPadding);

    Widget tile = Opacity(
      opacity: enabled ? 1.0 : 0.5,
      child: Container(
        color: backgroundColor,
        child: Padding(
          padding: effectivePadding,
          child: Row(
            children: [
              if (leading != null) ...[
                IconTheme(
                  data: IconThemeData(
                    size: dense ? AppSpacing.iconMd : AppSpacing.iconDf,
                    color: isLight ? AppColors.iconGrey : AppColors.grey,
                  ),
                  child: leading!,
                ),
                SizedBox(width: dense ? AppSpacing.md : AppSpacing.df),
              ],
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      style: (dense ? AppTextStyles.bodyMedium : AppTextStyles.bodyLarge)
                          .copyWith(color: textColor),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (subtitle != null) ...[
                      AppSpacing.verticalXs,
                      Text(
                        subtitle!,
                        style: AppTextStyles.bodySmall.copyWith(
                          color: AppColors.grey,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
              if (trailing != null) ...[
                AppSpacing.horizontalMd,
                trailing!,
              ] else if (showChevron && onTap != null) ...[
                AppSpacing.horizontalMd,
                AppIcon(
                  AppIcons.chevronRight,
                  size: AppSpacing.iconDf,
                  color: isLight ? AppColors.iconGrey : AppColors.grey,
                ),
              ],
            ],
          ),
        ),
      ),
    );

    if (onTap != null && enabled) {
      tile = InkWell(
        onTap: onTap,
        splashFactory: NoSplash.splashFactory,
        overlayColor: const WidgetStatePropertyAll(Colors.transparent),
        child: tile,
      );
    }

    if (showDivider) {
      tile = Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          tile,
          Divider(
            height: 1,
            thickness: 1,
            color: isLight ? AppColors.divider : AppColors.surfaceDark,
            indent: leading != null ? (effectivePadding.left + AppSpacing.iconDf + AppSpacing.df) : effectivePadding.left,
            endIndent: effectivePadding.right,
          ),
        ],
      );
    }

    return tile;
  }
}
