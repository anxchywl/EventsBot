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
class AppSecondaryButton extends StatefulWidget {
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
  State<AppSecondaryButton> createState() => _AppSecondaryButtonState();
}

class _AppSecondaryButtonState extends State<AppSecondaryButton> {
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final effectiveOnPressed = widget.isEnabled && !widget.isLoading ? widget.onPressed : null;
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    
    final effectiveBorderColor = widget.borderColor ?? AppColors.primary;
    final effectiveTextColor = widget.textColor ?? AppColors.primary;
    final disabledColor = isLight 
        ? AppColors.grey.withValues(alpha: 0.5)
        : AppColors.white.withValues(alpha: 0.3);

    return Listener(
      onPointerDown: (_) {
        if (effectiveOnPressed != null) setState(() => _isPressed = true);
      },
      onPointerUp: (_) => setState(() => _isPressed = false),
      onPointerCancel: (_) => setState(() => _isPressed = false),
      child: AnimatedScale(
        scale: _isPressed ? 0.97 : 1.0,
        duration: const Duration(milliseconds: 150),
        curve: Curves.easeInOutCubic,
        child: SizedBox(
          width: widget.width ?? double.infinity,
          height: widget._height,
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
              padding: widget.size.padding,
            ),
            child: _buildChild(effectiveTextColor, disabledColor),
          ),
        ),
      ),
    );
  }

  Widget _buildChild(Color textColor, Color disabledColor) {
    if (widget.isLoading) {
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
        if (widget.icon != null) ...[
          widget.icon!,
          AppSpacing.horizontalSm,
        ],
        Flexible(
          child: Text(
            widget.text,
            style: (widget.size == AppButtonSize.small
                ? AppTextStyles.buttonSmall
                : AppTextStyles.button),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
