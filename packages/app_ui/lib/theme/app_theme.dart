import 'package:flutter/material.dart';

import '../tokens/app_colors.dart';

/// Application theme configuration.
/// Provides Light and Dark ThemeData for the entire application.
class AppTheme {
  AppTheme._();

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      fontFamily: 'Geist',
      primaryColor: AppColors.primary,
      scaffoldBackgroundColor: AppColors.background,
      // Disable all InkWell/InkResponse ripple and press-highlight app-wide.
      splashFactory: NoSplash.splashFactory,
      splashColor: Colors.transparent,
      highlightColor: Colors.transparent,
      colorScheme: const ColorScheme.light(
        primary: AppColors.primary,
        secondary: AppColors.secondary,
        surface: AppColors.white,
        error: AppColors.red,
        onPrimary: AppColors.white,
        onSecondary: AppColors.textColor,
        onSurface: AppColors.textColor,
        onError: AppColors.white,
      ),
      textTheme: _textTheme(AppColors.textColor),
      appBarTheme: _appBarTheme(isLight: true),
      elevatedButtonTheme: _elevatedButtonTheme(),
      outlinedButtonTheme: _outlinedButtonTheme(),
      textButtonTheme: _textButtonTheme(),
      inputDecorationTheme: _inputDecorationTheme(isLight: true),
      cardTheme: _cardTheme(isLight: true),
      bottomNavigationBarTheme: _bottomNavBarTheme(isLight: true),
      tabBarTheme: const TabBarThemeData(
        splashFactory: NoSplash.splashFactory,
        overlayColor: WidgetStatePropertyAll(Colors.transparent),
      ),
      dividerTheme: const DividerThemeData(color: AppColors.dividerColor, thickness: 1),
      iconTheme: const IconThemeData(color: AppColors.iconGrey, size: 24),
    );
  }

  // Dark mode palette:
  //   Background : #171717
  //   Surface    : #242424  (cards, elevated containers)
  //   Text       : #F5F5F5  ("Up" — near-white for readability)
  //   Accent     : #A78BFA  ("Down" — soft lavender primary)
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      fontFamily: 'Geist',
      primaryColor: AppColors.primaryAccentDark,
      scaffoldBackgroundColor: const Color(0xFF171717),
      // Disable all InkWell/InkResponse ripple and press-highlight app-wide.
      splashFactory: NoSplash.splashFactory,
      splashColor: Colors.transparent,
      highlightColor: Colors.transparent,
      colorScheme: const ColorScheme.dark(
        primary: AppColors.primaryAccentDark,
        secondary: Color(0xFF7C5CBF),
        surface: Color(0xFF242424),
        error: AppColors.red,
        onPrimary: AppColors.white,
        onSecondary: AppColors.white,
        onSurface: Color(0xFFF5F5F5),
        onError: AppColors.white,
      ),
      textTheme: _textTheme(AppColors.textColorDark),
      appBarTheme: _appBarTheme(isLight: false),
      elevatedButtonTheme: _elevatedButtonThemeDark(),
      outlinedButtonTheme: _outlinedButtonThemeDark(),
      textButtonTheme: _textButtonThemeDark(),
      inputDecorationTheme: _inputDecorationTheme(isLight: false),
      cardTheme: _cardTheme(isLight: false),
      bottomNavigationBarTheme: _bottomNavBarTheme(isLight: false),
      tabBarTheme: const TabBarThemeData(
        splashFactory: NoSplash.splashFactory,
        overlayColor: WidgetStatePropertyAll(Colors.transparent),
      ),
      dividerTheme: const DividerThemeData(color: Color(0xFF333333), thickness: 1),
      iconTheme: const IconThemeData(color: Color(0xFFF5F5F5), size: 24),
    );
  }

  static TextTheme _textTheme(Color textColor) {
    return TextTheme(
      displayLarge: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: textColor),
      displayMedium: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: textColor),
      displaySmall: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: textColor),
      headlineLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: textColor),
      headlineMedium: TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: textColor),
      headlineSmall: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: textColor),
      titleLarge: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: textColor),
      titleMedium: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: textColor),
      titleSmall: TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: textColor),
      bodyLarge: TextStyle(fontSize: 16, fontWeight: FontWeight.normal, color: textColor),
      bodyMedium: TextStyle(fontSize: 14, fontWeight: FontWeight.normal, color: textColor),
      bodySmall: TextStyle(fontSize: 12, fontWeight: FontWeight.normal, color: textColor),
      labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: textColor),
      labelMedium: TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: textColor),
      labelSmall: TextStyle(fontSize: 10, fontWeight: FontWeight.w500, color: textColor),
    );
  }

  static AppBarTheme _appBarTheme({required bool isLight}) {
    return AppBarTheme(
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      centerTitle: true,
      backgroundColor: isLight ? AppColors.white : const Color(0xFF1F1F1F),
      foregroundColor: isLight ? AppColors.textColor : const Color(0xFFF5F5F5),
      iconTheme: IconThemeData(
          color: isLight ? AppColors.iconGrey : const Color(0xFFF5F5F5), size: 24),
      titleTextStyle: TextStyle(
        fontFamily: 'Geist',
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: isLight ? AppColors.textColor : const Color(0xFFF5F5F5),
      ),
    );
  }

  static ElevatedButtonThemeData _elevatedButtonTheme() {
    return ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: AppColors.white,
        minimumSize: const Size(double.infinity, 56),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        elevation: 0,
        textStyle: const TextStyle(fontFamily: 'Geist', fontSize: 16, fontWeight: FontWeight.w600),
      ),
    );
  }

  // Dark-mode variant: lavender accent button
  static ElevatedButtonThemeData _elevatedButtonThemeDark() {
    return ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primaryAccentDark,
        foregroundColor: AppColors.white,
        minimumSize: const Size(double.infinity, 56),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        elevation: 0,
        textStyle: const TextStyle(fontFamily: 'Geist', fontSize: 16, fontWeight: FontWeight.w600),
      ),
    );
  }

  static OutlinedButtonThemeData _outlinedButtonTheme() {
    return OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.primary,
        minimumSize: const Size(double.infinity, 56),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        side: const BorderSide(color: AppColors.primary, width: 1.5),
        textStyle: const TextStyle(fontFamily: 'Geist', fontSize: 16, fontWeight: FontWeight.w600),
      ),
    );
  }

  static OutlinedButtonThemeData _outlinedButtonThemeDark() {
    return OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.primaryAccentDark,
        minimumSize: const Size(double.infinity, 56),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        side: const BorderSide(color: AppColors.primaryAccentDark, width: 1.5),
        textStyle: const TextStyle(fontFamily: 'Geist', fontSize: 16, fontWeight: FontWeight.w600),
      ),
    );
  }

  static TextButtonThemeData _textButtonTheme() {
    return TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.primary,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        textStyle: const TextStyle(fontFamily: 'Geist', fontSize: 14, fontWeight: FontWeight.w600),
      ),
    );
  }

  static TextButtonThemeData _textButtonThemeDark() {
    return TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.primaryAccentDark,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        textStyle: const TextStyle(fontFamily: 'Geist', fontSize: 14, fontWeight: FontWeight.w600),
      ),
    );
  }

  static InputDecorationTheme _inputDecorationTheme({required bool isLight}) {
    return InputDecorationTheme(
      filled: true,
      fillColor: isLight ? AppColors.fieldBackground : const Color(0xFF2E2E2E),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      errorBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.red, width: 1.5)),
      focusedErrorBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.red, width: 1.5)),
      hintStyle: const TextStyle(fontFamily: 'Geist', fontSize: 14, color: AppColors.grey),
      labelStyle: TextStyle(fontFamily: 'Geist', fontSize: 14, color: isLight ? AppColors.textColor : AppColors.white),
      errorStyle: const TextStyle(fontFamily: 'Geist', fontSize: 12, color: AppColors.red),
    );
  }

  static CardThemeData _cardTheme({required bool isLight}) {
    return CardThemeData(
      elevation: 0,
      color: isLight ? AppColors.white : const Color(0xFF242424),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
    );
  }

  static BottomNavigationBarThemeData _bottomNavBarTheme({required bool isLight}) {
    return BottomNavigationBarThemeData(
      type: BottomNavigationBarType.fixed,
      backgroundColor: isLight ? AppColors.white : const Color(0xFF1F1F1F),
      selectedItemColor: AppColors.primary,
      unselectedItemColor: AppColors.grey,
      selectedLabelStyle: const TextStyle(fontFamily: 'Geist', fontSize: 12, fontWeight: FontWeight.w500),
      unselectedLabelStyle: const TextStyle(fontFamily: 'Geist', fontSize: 12),
      elevation: 8,
    );
  }
}
