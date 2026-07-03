import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';

/// Icon button with optional background.
/// Use for icon-only actions like close, menu, etc.
/// 
/// Example:
/// ```dart
/// AppIconButton(
///   icon: Icon(AppIcons.closeIcon),
///   onPressed: () => Navigator.pop(context),
/// )
/// ```
class AppIconButton extends StatelessWidget {
  const AppIconButton({
    super.key,
    required this.icon,
    this.onPressed,
    this.isEnabled = true,
    this.size = AppIconButtonSize.medium,
    this.backgroundColor,
    this.iconColor,
    this.tooltip,
    this.isLoading = false,
  });

  /// Icon widget to display.
  final Widget icon;

  /// Callback when button is pressed.
  final VoidCallback? onPressed;

  /// Whether the button is enabled.
  final bool isEnabled;

  /// Button size variant.
  final AppIconButtonSize size;

  /// Background color (transparent by default).
  final Color? backgroundColor;

  /// Icon color override.
  final Color? iconColor;

  /// Tooltip text.
  final String? tooltip;

  /// Whether to show loading indicator.
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    
    final effectiveIconColor = iconColor 
        ?? (isLight ? AppColors.textPrimary : AppColors.textPrimaryDark);
    final disabledColor = AppColors.grey.withValues(alpha: 0.5);
    final effectiveOnPressed = isEnabled && !isLoading ? onPressed : null;

    Widget button = Container(
      width: size.containerSize,
      height: size.containerSize,
      decoration: backgroundColor != null
          ? BoxDecoration(
              color: backgroundColor,
              borderRadius: AppSpacing.borderRadiusRound,
            )
          : null,
      child: Material(
        color: AppColors.transparent,
        child: InkWell(
          onTap: effectiveOnPressed,
          borderRadius: AppSpacing.borderRadiusRound,
          child: Center(
            child: _buildChild(effectiveIconColor, disabledColor),
          ),
        ),
      ),
    );

    if (tooltip != null) {
      button = Tooltip(
        message: tooltip!,
        child: button,
      );
    }

    return button;
  }

  Widget _buildChild(Color iconColor, Color disabledColor) {
    if (isLoading) {
      return SizedBox(
        width: size.iconSize,
        height: size.iconSize,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(iconColor),
        ),
      );
    }

    return IconTheme(
      data: IconThemeData(
        size: size.iconSize,
        color: isEnabled ? iconColor : disabledColor,
      ),
      child: icon,
    );
  }
}

/// Icon button size variants.
enum AppIconButtonSize {
  small(32, 16),
  medium(40, 20),
  large(48, 24);

  const AppIconButtonSize(this.containerSize, this.iconSize);

  final double containerSize;
  final double iconSize;
}
