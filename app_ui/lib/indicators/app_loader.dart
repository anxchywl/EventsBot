import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';

/// Loader/spinner widget with consistent styling.
/// 
/// Example:
/// ```dart
/// AppLoader()
/// AppLoader.overlay() // Full screen overlay
/// ```
class AppLoader extends StatelessWidget {
  const AppLoader({
    super.key,
    this.size = AppLoaderSize.medium,
    this.color,
    this.strokeWidth = 3.0,
  });

  /// Size variant.
  final AppLoaderSize size;

  /// Custom color.
  final Color? color;

  /// Stroke width.
  final double strokeWidth;

  @override
  Widget build(BuildContext context) {
    final effectiveColor = color ?? AppColors.primary;

    return SizedBox(
      width: size.value,
      height: size.value,
      child: CircularProgressIndicator(
        strokeWidth: strokeWidth,
        valueColor: AlwaysStoppedAnimation<Color>(effectiveColor),
      ),
    );
  }

  /// Create a centered loader.
  static Widget centered({
    AppLoaderSize size = AppLoaderSize.medium,
    Color? color,
  }) {
    return Center(
      child: AppLoader(size: size, color: color),
    );
  }

  /// Create a full-screen overlay loader.
  static Widget overlay({
    AppLoaderSize size = AppLoaderSize.large,
    Color? color,
    String? message,
  }) {
    return _LoaderOverlay(
      size: size,
      color: color,
      message: message,
    );
  }

  /// Show a loader dialog.
  static Future<void> showDialog({
    required BuildContext context,
    String? message,
    bool barrierDismissible = false,
  }) {
    return showGeneralDialog(
      context: context,
      barrierDismissible: barrierDismissible,
      barrierColor: AppColors.black.withValues(alpha: 0.5),
      pageBuilder: (_, _, _) => _LoaderDialog(message: message),
    );
  }

  /// Hide the loader dialog.
  static void hideDialog(BuildContext context) {
    Navigator.of(context).pop();
  }
}

/// Loader size variants.
enum AppLoaderSize {
  small(20),
  medium(32),
  large(48),
  xLarge(64);

  const AppLoaderSize(this.value);
  final double value;
}

class _LoaderOverlay extends StatelessWidget {
  const _LoaderOverlay({
    required this.size,
    this.color,
    this.message,
  });

  final AppLoaderSize size;
  final Color? color;
  final String? message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final textColor = isLight ? AppColors.textPrimary : AppColors.textPrimaryDark;

    return Container(
      color: AppColors.black.withValues(alpha: 0.5),
      child: Center(
        child: Container(
          padding: AppSpacing.dialogPadding,
          decoration: BoxDecoration(
            color: isLight ? AppColors.white : AppColors.surfaceDark,
            borderRadius: AppSpacing.borderRadiusMd,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              AppLoader(size: size, color: color),
              if (message != null) ...[
                AppSpacing.verticalDf,
                Text(
                  message!,
                  style: theme.textTheme.bodyMedium?.copyWith(color: textColor),
                  textAlign: TextAlign.center,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _LoaderDialog extends StatelessWidget {
  const _LoaderDialog({this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final textColor = isLight ? AppColors.textPrimary : AppColors.textPrimaryDark;

    return Center(
      child: Container(
        margin: AppSpacing.screenPadding,
        padding: AppSpacing.dialogPadding,
        decoration: BoxDecoration(
          color: isLight ? AppColors.white : AppColors.surfaceDark,
          borderRadius: AppSpacing.borderRadiusMd,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const AppLoader(size: AppLoaderSize.large),
            if (message != null) ...[
              AppSpacing.verticalDf,
              Text(
                message!,
                style: theme.textTheme.bodyMedium?.copyWith(color: textColor),
                textAlign: TextAlign.center,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
