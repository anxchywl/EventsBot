import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';

/// Primary button with filled background.
/// Use for main call-to-action buttons.
/// 
/// Example:
/// ```dart
/// AppPrimaryButton(
///   text: 'Continue',
///   onPressed: () => doSomething(),
/// )
/// ```
class AppPrimaryButton extends StatelessWidget {
  const AppPrimaryButton({
    super.key,
    required this.text,
    this.onPressed,
    this.isLoading = false,
    this.isEnabled = true,
    this.icon,
    this.width,
    this.height,
    this.size = AppButtonSize.large,
  });

  /// Button label text.
  final String text;

  /// Callback when button is pressed. If null, button appears disabled.
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

  double get _height => height ?? size.height;

  @override
  Widget build(BuildContext context) {
    final effectiveOnPressed = isEnabled && !isLoading ? onPressed : null;

    return SizedBox(
      width: width ?? double.infinity,
      height: _height,
      child: ElevatedButton(
        onPressed: effectiveOnPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: AppColors.white,
          disabledBackgroundColor: AppColors.primary.withValues(alpha: 0.5),
          disabledForegroundColor: AppColors.white.withValues(alpha: 0.7),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: AppSpacing.borderRadiusMd,
          ),
          padding: size.padding,
        ),
        child: _buildChild(),
      ),
    );
  }

  Widget _buildChild() {
    if (isLoading) {
      return SizedBox(
        width: AppSpacing.iconDf,
        height: AppSpacing.iconDf,
        child: const CircularProgressIndicator(
          strokeWidth: 2.5,
          valueColor: AlwaysStoppedAnimation<Color>(AppColors.white),
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
            style: size == AppButtonSize.small
                ? AppTextStyles.buttonSmall
                : AppTextStyles.button,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}

/// Button size variants.
enum AppButtonSize {
  small(AppSpacing.buttonHeightSm, AppSpacing.buttonPaddingCompact),
  medium(AppSpacing.buttonHeightDf, AppSpacing.buttonPaddingCompact),
  large(AppSpacing.buttonHeightLg, AppSpacing.buttonPadding);

  const AppButtonSize(this.height, this.padding);

  final double height;
  final EdgeInsets padding;
}
