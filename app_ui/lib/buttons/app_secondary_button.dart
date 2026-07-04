import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';
import 'app_primary_button.dart';

/// Secondary button with outlined border.
/// Use for secondary actions or cancel buttons.
/// 
/// Example:
/// ```dart
/// AppSecondaryButton(
///   text: 'Cancel',
///   onPressed: () => Navigator.pop(context),
/// )
/// ```
class AppSecondaryButton extends StatelessWidget {
  const AppSecondaryButton({
    super.key,
    required this.text,
    this.onPressed,
    this.isLoading = false,
    this.isEnabled = true,
    this.icon,
    this.width,
    this.height,
    this.size = AppButtonSize.large,
    this.borderColor,
    this.textColor,
  });

  /// Button label text.
  final String text;

  /// Callback when button is pressed.
  final VoidCallback? onPressed;

  /// Whether to show loading indicator.
  final bool isLoading;

  /// Whether the button is enabled.
  final bool isEnabled;

  /// Optional leading icon widget.
  final Widget? icon;

  /// Custom width (defaults to full width).
  final double? width;

  /// Custom height (overrides size).
  final double? height;

  /// Button size variant.
  final AppButtonSize size;

  /// Custom border color.
  final Color? borderColor;

  /// Custom text color.
  final Color? textColor;

  double get _height => height ?? size.height;

  @override
  Widget build(BuildContext context) {
    final effectiveOnPressed = isEnabled && !isLoading ? onPressed : null;
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    
    final effectiveBorderColor = borderColor ?? AppColors.primary;
    final effectiveTextColor = textColor ?? AppColors.primary;
    final disabledColor = isLight 
        ? AppColors.grey.withValues(alpha: 0.5)
        : AppColors.white.withValues(alpha: 0.3);

    return SizedBox(
      width: width ?? double.infinity,
      height: _height,
      child: OutlinedButton(
        onPressed: effectiveOnPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: effectiveTextColor,
          disabledForegroundColor: disabledColor,
          side: BorderSide(
            color: effectiveOnPressed != null 
                ? effectiveBorderColor 
                : disabledColor,
            width: 1.5,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: AppSpacing.borderRadiusMd,
          ),
          padding: size.padding,
        ),
        child: _buildChild(effectiveTextColor, disabledColor),
      ),
    );
  }

  Widget _buildChild(Color textColor, Color disabledColor) {
    if (isLoading) {
      return SizedBox(
        width: AppSpacing.iconDf,
        height: AppSpacing.iconDf,
        child: CircularProgressIndicator(
          strokeWidth: 2.5,
          valueColor: AlwaysStoppedAnimation<Color>(textColor),
        ),
      );
    }

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          icon!,
          AppSpacing.horizontalSm,
        ],
        Flexible(
          child: Text(
            text,
            style: (size == AppButtonSize.small
                ? AppTextStyles.buttonSmall
                : AppTextStyles.button),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
