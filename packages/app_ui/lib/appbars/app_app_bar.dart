import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';
import '../icons/app_icons.dart';
import '../icons/app_icon.dart';

/// Global AppBar widget with consistent height and behavior.
/// Features: 56px height, centered title, optional divider.
/// 
/// Example:
/// ```dart
/// AppAppBar(
///   title: 'Profile',
///   showBackButton: true,
/// )
/// ```
class AppAppBar extends StatelessWidget implements PreferredSizeWidget {
  const AppAppBar({
    super.key,
    this.title,
    this.titleWidget,
    this.leading,
    this.leadingWidth,
    this.actions,
    this.showBackButton = false,
    this.onBackPressed,
    this.centerTitle = true,
    this.backgroundColor,
    this.elevation = 0,
    this.bottom,
    this.showDivider = false,
  });

  /// The title text to display.
  final String? title;

  /// Custom title widget (takes precedence over [title]).
  final Widget? titleWidget;

  /// Custom leading widget (takes precedence over back button).
  final Widget? leading;

  /// Width of the leading widget slot. Defaults to Flutter's kToolbarHeight (56).
  /// Set to a smaller value (e.g. 52) when using a compact avatar or icon.
  final double? leadingWidth;

  /// List of action widgets to display on the right.
  final List<Widget>? actions;

  /// Whether to show the default back button.
  final bool showBackButton;

  /// Callback when back button is pressed.
  final VoidCallback? onBackPressed;

  /// Whether to center the title.
  final bool centerTitle;

  /// Custom background color.
  final Color? backgroundColor;

  /// AppBar elevation.
  final double elevation;

  /// Bottom widget (e.g., TabBar).
  final PreferredSizeWidget? bottom;

  /// Whether to show bottom divider.
  final bool showDivider;

  @override
  Size get preferredSize => Size.fromHeight(
        AppSpacing.appBarHeight + 
        (bottom?.preferredSize.height ?? 0) + 
        (showDivider ? 1 : 0),
      );

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final effectiveBackgroundColor = backgroundColor
        ?? (isLight ? AppColors.background : const Color(0xFF171717));
    final textColor = isLight ? AppColors.textPrimary : AppColors.textPrimaryDark;

    Widget? leadingWidget = leading;
    if (leadingWidget == null && showBackButton) {
      leadingWidget = _buildBackButton(context, isLight);
    }

    Widget? titleWidgetFinal = titleWidget;
    if (titleWidgetFinal == null && title != null) {
      titleWidgetFinal = Text(
        title!,
        style: AppTextStyles.appBarTitle.copyWith(color: textColor),
        overflow: TextOverflow.ellipsis,
      );
    }

    // Build the bottom widget with optional divider
    PreferredSizeWidget? effectiveBottom = bottom;
    if (showDivider || bottom != null) {
      effectiveBottom = PreferredSize(
        preferredSize: Size.fromHeight(
          (bottom?.preferredSize.height ?? 0) + (showDivider ? 1 : 0),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ?bottom,
            if (showDivider)
              Divider(
                height: 1,
                thickness: 1,
                color: isLight ? AppColors.divider : AppColors.borderDark,
              ),
          ],
        ),
      );
    }

    return AppBar(
      leading: leadingWidget,
      leadingWidth: leadingWidth,
      automaticallyImplyLeading: false,
      title: titleWidgetFinal,
      centerTitle: centerTitle,
      actions: actions,
      backgroundColor: effectiveBackgroundColor,
      surfaceTintColor: Colors.transparent,
      elevation: elevation,
      scrolledUnderElevation: 0,
      bottom: effectiveBottom,
      toolbarHeight: AppSpacing.appBarHeight,
      iconTheme: IconThemeData(
        color: isLight ? AppColors.iconGrey : AppColors.white,
        size: AppSpacing.iconDf,
      ),
    );
  }

  Widget _buildBackButton(BuildContext context, bool isLight) {
    return IconButton(
      onPressed: onBackPressed ?? () => Navigator.of(context).pop(),
      padding: EdgeInsets.zero,
      icon: AppIcon(
        AppIcons.back,
        size: AppSpacing.iconDf,
        color: isLight ? AppColors.iconGrey : AppColors.white,
      ),
    );
  }
}

/// Simple AppBar with just back button and title.
class AppSimpleAppBar extends StatelessWidget implements PreferredSizeWidget {
  const AppSimpleAppBar({
    super.key,
    required this.title,
    this.onBackPressed,
  });

  final String title;
  final VoidCallback? onBackPressed;

  @override
  Size get preferredSize => const Size.fromHeight(AppSpacing.appBarHeight);

  @override
  Widget build(BuildContext context) {
    return AppAppBar(
      title: title,
      showBackButton: true,
      onBackPressed: onBackPressed,
    );
  }
}
