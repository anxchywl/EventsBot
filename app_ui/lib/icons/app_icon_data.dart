import 'package:flutter/material.dart';

/// Sealed abstraction for icon data.
/// 
/// This hides the implementation details of whether an icon is
/// an SVG asset or a Material icon. Consumers only work with [AppIconData].
/// 
/// Usage:
/// ```dart
/// // Define icons in AppIcons
/// static const AppIconData settings = SvgIcon('assets/icons/settings.svg');
/// static const AppIconData back = MaterialIcon(Icons.arrow_back);
/// 
/// // Use with AppIcon widget
/// AppIcon(AppIcons.settings)
/// ```
sealed class AppIconData {
  const AppIconData();

  /// Extracts the underlying [IconData] for the rare cases where an external
  /// package requires a raw [IconData] (e.g. [SlidableAction.icon]).
  /// Returns null for SVG-backed icons — use [AppIcon] directly instead.
  IconData? get asIconData => null;

  static IconData? get chevronRight => null;

  static IconData? get visibility => null;

  static IconData? get visibilityOff => null;

  static IconData? get lock => null;

  static IconData? get phone => null;
}

/// SVG-based icon from an asset path.
/// 
/// Used for custom/brand icons stored as SVG files.
final class SvgIcon extends AppIconData {
  const SvgIcon(this.assetPath, {this.package});
  
  /// Path to the SVG asset (e.g., 'assets/icons/settings.svg')
  final String assetPath;
  
  /// Optional package name if the asset is from a package
  final String? package;
  
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is SvgIcon && 
      assetPath == other.assetPath && 
      package == other.package;
  
  @override
  int get hashCode => Object.hash(assetPath, package);
  
  @override
  String toString() => 'SvgIcon($assetPath)';
}

/// Material Design icon from Flutter's Icons class.
/// 
/// Used for standard Material icons.
final class MaterialIcon extends AppIconData {
  const MaterialIcon(this.iconData);

  /// The underlying [IconData] (from Lucide or other icon font).
  final IconData iconData;

  @override
  IconData? get asIconData => iconData;
  
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is MaterialIcon && iconData == other.iconData;
  
  @override
  int get hashCode => iconData.hashCode;
  
  @override
  String toString() => 'MaterialIcon(${iconData.codePoint})';
}
