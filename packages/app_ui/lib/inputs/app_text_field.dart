import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';

/// Standard text input field with consistent styling.
/// 
/// Example:
/// ```dart
/// AppTextField(
///   controller: _controller,
///   label: 'Email',
///   hint: 'Enter your email',
///   keyboardType: TextInputType.emailAddress,
/// )
/// ```
class AppTextField extends StatelessWidget {
  const AppTextField({
    super.key,
    this.controller,
    this.label,
    this.hint,
    this.errorText,
    this.helperText,
    this.prefixIcon,
    this.suffixIcon,
    this.keyboardType,
    this.textInputAction,
    this.onChanged,
    this.onSubmitted,
    this.onTap,
    this.validator,
    this.enabled = true,
    this.readOnly = false,
    this.autofocus = false,
    this.obscureText = false,
    this.maxLines = 1,
    this.minLines,
    this.maxLength,
    this.focusNode,
    this.inputFormatters,
    this.textCapitalization = TextCapitalization.none,
    this.filled = true,
    this.fillColor,
    this.borderRadius,
    this.contentPadding,
  });

  /// Controller for the text field.
  final TextEditingController? controller;
  
  /// Label text displayed above the field.
  final String? label;
  
  /// Hint text displayed when field is empty.
  final String? hint;
  
  /// Error text displayed below the field.
  final String? errorText;
  
  /// Helper text displayed below the field.
  final String? helperText;
  
  /// Prefix icon widget.
  final Widget? prefixIcon;
  
  /// Suffix icon widget.
  final Widget? suffixIcon;
  
  /// Keyboard type for the field.
  final TextInputType? keyboardType;
  
  /// Text input action for the keyboard.
  final TextInputAction? textInputAction;
  
  /// Callback when text changes.
  final ValueChanged<String>? onChanged;
  
  /// Callback when field is submitted.
  final ValueChanged<String>? onSubmitted;
  
  /// Callback when field is tapped.
  final VoidCallback? onTap;
  
  /// Validator function for form validation.
  final FormFieldValidator<String>? validator;
  
  /// Whether the field is enabled.
  final bool enabled;
  
  /// Whether the field is read-only.
  final bool readOnly;
  
  /// Whether to autofocus the field.
  final bool autofocus;
  
  /// Whether to obscure text (for passwords).
  final bool obscureText;
  
  /// Maximum number of lines.
  final int? maxLines;
  
  /// Minimum number of lines.
  final int? minLines;
  
  /// Maximum character length.
  final int? maxLength;
  
  /// Focus node for the field.
  final FocusNode? focusNode;
  
  /// Input formatters for text manipulation.
  final List<TextInputFormatter>? inputFormatters;
  
  /// Text capitalization behavior.
  final TextCapitalization textCapitalization;
  
  /// Whether to fill the background.
  final bool filled;
  
  /// Custom fill color.
  final Color? fillColor;
  
  /// Custom border radius.
  final BorderRadius? borderRadius;
  
  /// Custom content padding.
  final EdgeInsets? contentPadding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    
    final effectiveFillColor = fillColor 
        ?? (isLight ? AppColors.fieldBackground : AppColors.surfaceDark);
    final effectiveBorderRadius = borderRadius ?? AppSpacing.borderRadiusMd;
    final effectiveContentPadding = contentPadding 
        ?? const EdgeInsets.symmetric(horizontal: AppSpacing.df, vertical: AppSpacing.md);

    return TextFormField(
      controller: controller,
      focusNode: focusNode,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        errorText: errorText,
        helperText: helperText,
        prefixIcon: prefixIcon,
        suffixIcon: suffixIcon,
        filled: filled,
        fillColor: effectiveFillColor,
        contentPadding: effectiveContentPadding,
        hintStyle: AppTextStyles.hint.copyWith(color: AppColors.grey),
        labelStyle: AppTextStyles.labelLarge.copyWith(
          color: isLight ? AppColors.textPrimary : AppColors.textPrimaryDark,
        ),
        errorStyle: AppTextStyles.error.copyWith(color: AppColors.error),
        helperStyle: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
        border: OutlineInputBorder(
          borderRadius: effectiveBorderRadius,
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: effectiveBorderRadius,
          borderSide: isLight
              ? BorderSide.none
              : const BorderSide(color: AppColors.primary, width: 0.5),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: effectiveBorderRadius,
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: effectiveBorderRadius,
          borderSide: const BorderSide(color: AppColors.error, width: 1.5),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: effectiveBorderRadius,
          borderSide: const BorderSide(color: AppColors.error, width: 1.5),
        ),
        disabledBorder: OutlineInputBorder(
          borderRadius: effectiveBorderRadius,
          borderSide: BorderSide.none,
        ),
      ),
      style: AppTextStyles.bodyLarge.copyWith(
        color: isLight ? AppColors.textPrimary : AppColors.textPrimaryDark,
      ),
      keyboardType: keyboardType,
      textInputAction: textInputAction,
      onChanged: onChanged,
      onFieldSubmitted: onSubmitted,
      onTap: onTap,
      validator: validator,
      enabled: enabled,
      readOnly: readOnly,
      autofocus: autofocus,
      obscureText: obscureText,
      maxLines: obscureText ? 1 : maxLines,
      minLines: minLines,
      maxLength: maxLength,
      inputFormatters: inputFormatters,
      textCapitalization: textCapitalization,
    );
  }
}
