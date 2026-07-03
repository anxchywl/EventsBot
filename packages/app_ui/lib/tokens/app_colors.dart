import 'package:flutter/material.dart';

/// App Colors - Single source of truth for all colors in the application.
/// 
/// Usage:
/// ```dart
/// Container(color: AppColors.primary)
/// ```
/// 
/// NEVER use Colors.* directly in feature code.
abstract class AppColors {
  // ─────────────────────────────────────────────────────────────────────────────
  // PRIMARY BRAND COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Primary brand color - Vibrant Purple
  static const Color primary = Color(0xFF7100FF);

  /// Primary accent color for dark mode — soft lavender
  static const Color primaryAccentDark = Color(0xFFA78BFA);

  /// Primary dark variant
  static const Color primaryDark = Color(0xFF4A00E0);

  /// Primary light variant for backgrounds (light mode)
  static const Color primaryLight = Color(0xFFEEE5FF);

  /// Primary light tint for dark mode backgrounds
  static const Color primaryLightDark = Color(0x26A78BFA);
  
  /// Secondary color - 10% opacity of primary
  static const Color secondary = Color(0xFFE5D4FF);

  // ─────────────────────────────────────────────────────────────────────────────
  // BACKGROUND COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Main background color (light mode)
  static const Color background = Color(0xFFF9F9FF);
  
  /// Surface color for cards (light mode)
  static const Color surface = Color(0xFFFFFFFF);
  
  /// Dark surface for dark mode cards — slightly elevated above #171717
  static const Color surfaceDark = Color(0xFF242424);
  
  /// Field background color
  static const Color fieldBackground = Color(0xFFEAEAFF);
  
  /// Balance card background
  static const Color balanceCardBackground = Color(0xFFF2F2FF);
  
  /// Service item background
  static const Color serviceBackground = Color(0xFFF5F5F5);

  // ─────────────────────────────────────────────────────────────────────────────
  // TEXT COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Primary text color (light mode)
  static const Color textPrimary = Color(0xFF5D5186);
  
  /// Alias for textPrimary (backward compatibility)
  static const Color textColor = textPrimary;
  
  /// Primary text color (dark mode)
  static const Color textPrimaryDark = Color(0xFFF5F5F5);
  
  /// Alias for textPrimaryDark (backward compatibility)
  static const Color textColorDark = textPrimaryDark;
  
  /// Secondary text color / hints
  static const Color textSecondary = Color(0xFF91919F);
  
  /// Disabled text color
  static const Color textDisabled = Color(0xFFBDBDBD);

  // ─────────────────────────────────────────────────────────────────────────────
  // ICON COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Primary icon color (adapts to theme)
  static const Color iconPrimary = Color(0xFF5D5186);
  
  /// Secondary icon color
  static const Color iconSecondary = Color(0xFF91919F);
  
  /// Disabled icon color
  static const Color iconDisabled = Color(0xFFBDBDBD);

  // ─────────────────────────────────────────────────────────────────────────────
  // SEMANTIC COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Success / positive actions
  static const Color success = Color(0xFF00A86B);
  
  /// Error / destructive actions
  static const Color error = Color(0xFFFD3C4A);
  
  /// Warning / caution
  static const Color warning = Color(0xFFFFE34F);
  
  /// Info / neutral information
  static const Color info = Color(0xFF0077FF);
  
  /// Light green background for success states
  static const Color successLight = Color(0xFFD4F7E5);
  
  /// Alias for successLight (backward compatibility)
  static const Color lightGreen = successLight;
  
  /// Light red background for error states
  static const Color errorLight = Color(0xFFFFEBEE);
  
  /// Light blue background for info states
  static const Color infoLight = Color(0xFFD4E5FF);
  
  /// Alias for infoLight (backward compatibility)
  static const Color lightBlue = infoLight;
  
  /// Light orange background for warning states
  static const Color warningLight = Color(0xFFFFF3E0);

  // ─────────────────────────────────────────────────────────────────────────────
  // NEUTRAL COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Pure white
  static const Color white = Color(0xFFFFFFFF);
  
  /// Pure black
  static const Color black = Color(0xFF0D0E0F);
  
  /// Grey for secondary elements
  static const Color grey = Color(0xFF91919F);
  
  /// Light grey for borders
  static const Color lightGrey = Color(0xFFE3E5E5);
  
  /// Border grey
  static const Color borderGrey = Color(0xFFEEEEEE);
  
  /// Border dark (dark mode) — visible on #242424 surface
  static const Color borderDark = Color(0xFF333333);
  
  /// Divider color
  static const Color divider = Color(0xFFE0E0E0);
  
  /// Alias for divider (backward compatibility)
  static const Color dividerColor = divider;
  
  /// Icon grey
  static const Color iconGrey = Color(0xFF9487C1);
  
  /// Overlay color
  static const Color overlay = Color(0x0D000000);
  
  /// Transparent
  static const Color transparent = Color(0x00000000);

  // ─────────────────────────────────────────────────────────────────────────────
  // ACCENT COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Blue accent
  static const Color blue = Color(0xFF0077FF);
  
  /// Light blue accent
  static const Color blueLight = Color(0xFFE1F5FE);
  
  /// Green accent
  static const Color green = Color(0xFF00A86B);
  
  /// Red accent
  static const Color red = Color(0xFFFD3C4A);
  
  /// Yellow accent
  static const Color yellow = Color(0xFFFFE34F);
  
  /// Orange accent
  static const Color orange = Color(0xFFFF9800);
  
  /// Orange light background
  static const Color orangeLight = Color(0xFFFFF3E0);
  
  /// Gold accent
  static const Color gold = Color(0xFFFFD700);
  
  /// Purple accent
  static const Color purple = Color(0xFF9C27B0);
  
  /// Purple light background
  static const Color purpleLight = Color(0xFFF3E5F5);
  
  /// Deep purple
  static const Color deepPurple = Color(0xFF673AB7);
  
  /// Deep purple light
  static const Color deepPurpleLight = Color(0xFFEDE7F6);
  
  /// Cyan accent
  static const Color cyan = Color(0xFF00BCD4);
  
  /// Promoted item blue
  static const Color promotedBlue = Color(0xFF4FA0FF);

  // ─────────────────────────────────────────────────────────────────────────────
  // SOCIAL MEDIA COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// WhatsApp green
  static const Color socialWhatsapp = Color(0xFF25D366);
  
  /// Twitter/X blue
  static const Color socialTwitter = Color(0xFF1DA1F2);
  
  /// Facebook/LinkedIn blue
  static const Color socialFacebook = Color(0xFF0A66C2);
  
  /// Instagram pink
  static const Color socialInstagram = Color(0xFFE4405F);

  // ─────────────────────────────────────────────────────────────────────────────
  // AVATAR COLORS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Avatar background color 1
  static const Color avatar1 = Color(0xFFFF6B35);
  
  /// Avatar background color 2
  static const Color avatar2 = Color(0xFF52B788);
  
  /// Avatar background color 3
  static const Color avatar3 = Color(0xFF7367F0);
  
  /// Avatar background color 4
  static const Color avatar4 = Color(0xFFFF6B9D);
  
  /// Avatar background color 5
  static const Color avatar5 = Color(0xFFC98BDB);

  // ─────────────────────────────────────────────────────────────────────────────
  // GRADIENT DEFINITIONS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /// Primary gradient
  static const LinearGradient primaryGradient = LinearGradient(
    colors: [primary, primaryDark],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
  
  /// Gold gradient for premium features
  static const LinearGradient goldGradient = LinearGradient(
    colors: [Color(0xFFFFD700), Color(0xFFFFA500)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}
