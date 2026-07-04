import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';

/// Text button without background or border.
/// Use for less prominent actions or links.
/// 
/// Example:
/// ```dart
/// AppTextButton(
///   text: 'Forgot Password?',
///   onPressed: () => navigateToForgotPassword(),
/// )
/// ```
class AppTextButton extends StatelessWidget {
  const AppTextButton({
    super.key,
    required this.text,
    this.onPressed,
    this.isLoading = false,
    this.isEnabled = true,
    this.icon,
    this.textColor,
    this.underline = false,
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

  /// Custom text color (defaults to primary).
  final Color? textColor;

  /// Whether to underline the text.
  final bool underline;

  @override
  Widget build(BuildContext context) {
    final effectiveOnPressed = isEnabled && !isLoading ? onPressed : null;
    final effectiveTextColor = textColor ?? AppColors.primary;

    return TextButton(
      onPressed: effectiveOnPressed,
      style: TextButton.styleFrom(
        foregroundColor: effectiveTextColor,
        disabledForegroundColor: AppColors.grey.withValues(alpha: 0.5),
        padding: AppSpacing.buttonPaddingCompact,
        shape: RoundedRectangleBorder(
          borderRadius: AppSpacing.borderRadiusSm,
        ),
      ),
      child: _buildChild(effectiveTextColor),
    );
  }

  Widget _buildChild(Color color) {
    if (isLoading) {
      return SizedBox(
        width: AppSpacing.iconMd,
        height: AppSpacing.iconMd,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(color),
        ),
      );
    }

    final textStyle = underline
        ? AppTextStyles.buttonSmall.copyWith(decoration: TextDecoration.underline)
        : AppTextStyles.buttonSmall;

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          icon!,
          AppSpacing.horizontalXs,
        ],
        Text(
          text,
          style: textStyle,
        ),
      ],
    );
  }
}
