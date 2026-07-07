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
class AppPrimaryButton extends StatefulWidget {
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
  State<AppPrimaryButton> createState() => _AppPrimaryButtonState();
}

class _AppPrimaryButtonState extends State<AppPrimaryButton> {
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final effectiveOnPressed = widget.isEnabled && !widget.isLoading ? widget.onPressed : null;

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
              padding: widget.size.padding,
            ),
            child: _buildChild(),
          ),
        ),
      ),
    );
  }

  Widget _buildChild() {
    if (widget.isLoading) {
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
        if (widget.icon != null) ...[
          widget.icon!,
          AppSpacing.horizontalSm,
        ],
        Flexible(
          child: Text(
            widget.text,
            style: widget.size == AppButtonSize.small
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
