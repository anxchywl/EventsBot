import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'app_icon_data.dart';
import '../tokens/app_colors.dart';

/// A unified icon widget that renders both SVG and Material icons.
/// 
/// This is the ONLY widget that should be used for rendering icons
/// throughout the application. It abstracts away whether an icon
/// is an SVG or Material icon.
/// 
/// ## Usage
/// 
/// ```dart
/// // Basic usage - shows original SVG colors (no tint)
/// AppIcon(AppIcons.logo)
/// 
/// // With custom size
/// AppIcon(AppIcons.logo, size: 32)
/// 
/// // With color tint (applies colorFilter)
/// AppIcon(AppIcons.settings, color: AppColors.primary)
/// 
/// // With custom colorFilter for advanced effects
/// AppIcon(
///   AppIcons.settings,
///   colorFilter: ColorFilter.mode(Colors.red, BlendMode.srcIn),
/// )
/// ```
/// 
/// ## Default Behavior
/// 
/// - Size defaults to 24
/// - SVG icons show **original colors** by default (no tint)
/// - Pass [color] to apply a tint (uses BlendMode.srcIn)
/// - Pass [colorFilter] for custom color effects
/// - Material icons use [color] or fall back to theme default
class AppIcon extends StatelessWidget {
  const AppIcon(
    this.icon, {
    super.key,
    this.size,
    this.color,
    this.colorFilter,
    this.semanticLabel,
  });
  
  /// The icon to display. Must be an [AppIconData] from [AppIcons].
  final AppIconData icon;
  
  /// The size of the icon in logical pixels.
  /// 
  /// Defaults to 24.0.
  final double? size;
  
  /// The color to use when drawing the icon.
  /// 
  /// For SVG icons: If provided, applies a [ColorFilter] with [BlendMode.srcIn].
  /// If null, the SVG is rendered with its original colors.
  /// 
  /// For Material icons: Falls back to [AppColors.iconPrimary] if null.
  final Color? color;
  
  /// Custom color filter to apply to SVG icons.
  /// 
  /// If provided, this takes precedence over [color] for SVG icons.
  /// Has no effect on Material icons.
  final ColorFilter? colorFilter;
  
  /// Semantic label for accessibility.
  /// 
  /// This label is read by screen readers.
  final String? semanticLabel;
  
  /// Default icon size
  static const double defaultSize = 24.0;

  @override
  Widget build(BuildContext context) {
    final effectiveSize = size ?? defaultSize;
    
    return switch (icon) {
      SvgIcon(:final assetPath, :final package) => SvgPicture.asset(
          assetPath,
          package: package,
          width: effectiveSize,
          height: effectiveSize,
          colorFilter: colorFilter ?? (color != null 
              ? ColorFilter.mode(color!, BlendMode.srcIn) 
              : null),
          semanticsLabel: semanticLabel,
        ),
      MaterialIcon(:final iconData) => Icon(
          iconData,
          size: effectiveSize,
          color: color ?? AppColors.iconPrimary,
          semanticLabel: semanticLabel,
        ),
    };
  }
}

/// Extension for creating AppIcon with common presets.
extension AppIconPresets on AppIcon {
  /// Creates a small icon (16px)
  static AppIcon small(AppIconData icon, {Color? color}) => AppIcon(
    icon,
    size: 16,
    color: color,
  );
  
  /// Creates a medium icon (24px - default)
  static AppIcon medium(AppIconData icon, {Color? color}) => AppIcon(
    icon,
    size: 24,
    color: color,
  );
  
  /// Creates a large icon (32px)
  static AppIcon large(AppIconData icon, {Color? color}) => AppIcon(
    icon,
    size: 32,
    color: color,
  );
  
  /// Creates an extra large icon (48px)
  static AppIcon xl(AppIconData icon, {Color? color}) => AppIcon(
    icon,
    size: 48,
    color: color,
  );
}
