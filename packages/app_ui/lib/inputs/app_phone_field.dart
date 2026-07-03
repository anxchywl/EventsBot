import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';
import '../icons/app_icons.dart';
import '../icons/app_icon.dart';
import 'app_text_field.dart';

/// Phone number input field with country code support.
/// 
/// Example:
/// ```dart
/// AppPhoneField(
///   controller: _phoneController,
///   countryCode: '+7',
///   label: 'Phone Number',
/// )
/// ```
class AppPhoneField extends StatelessWidget {
  const AppPhoneField({
    super.key,
    this.controller,
    this.label,
    this.hint,
    this.errorText,
    this.helperText,
    this.countryCode = '+7',
    this.onChanged,
    this.onSubmitted,
    this.validator,
    this.enabled = true,
    this.autofocus = false,
    this.focusNode,
    this.textInputAction,
    this.onCountryCodeTap,
  });

  /// Controller for the phone number field.
  final TextEditingController? controller;
  
  /// Label text displayed above the field.
  final String? label;
  
  /// Hint text displayed when field is empty.
  final String? hint;
  
  /// Error text displayed below the field.
  final String? errorText;
  
  /// Helper text displayed below the field.
  final String? helperText;
  
  /// Country calling code (e.g., '+7').
  final String countryCode;
  
  /// Callback when phone number changes.
  final ValueChanged<String>? onChanged;
  
  /// Callback when field is submitted.
  final ValueChanged<String>? onSubmitted;
  
  /// Validator function for form validation.
  final FormFieldValidator<String>? validator;
  
  /// Whether the field is enabled.
  final bool enabled;
  
  /// Whether to autofocus the field.
  final bool autofocus;
  
  /// Focus node for the field.
  final FocusNode? focusNode;
  
  /// Text input action for the keyboard.
  final TextInputAction? textInputAction;
  
  /// Callback when country code is tapped.
  final VoidCallback? onCountryCodeTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;

    return AppTextField(
      controller: controller,
      label: label,
      hint: hint ?? '(XXX) XXX-XX-XX',
      errorText: errorText,
      helperText: helperText,
      onChanged: onChanged,
      onSubmitted: onSubmitted,
      validator: validator,
      enabled: enabled,
      autofocus: autofocus,
      focusNode: focusNode,
      textInputAction: textInputAction,
      keyboardType: TextInputType.phone,
      inputFormatters: [
        FilteringTextInputFormatter.allow(RegExp(r'[0-9\s\-\(\)]')),
        LengthLimitingTextInputFormatter(15),
      ],
      prefixIcon: InkWell(
        onTap: enabled ? onCountryCodeTap : null,
        borderRadius: AppSpacing.borderRadiusSm,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              AppIcon(
                AppIcons.phone,
                size: AppSpacing.iconMd,
                color: isLight ? AppColors.iconGrey : AppColors.grey,
              ),
              AppSpacing.horizontalSm,
              Text(
                countryCode,
                style: AppTextStyles.bodyLarge.copyWith(
                  color: isLight ? AppColors.textPrimary : AppColors.textPrimaryDark,
                  fontWeight: FontWeight.w500,
                ),
              ),
              AppSpacing.horizontalXs,
              AppIcon(
                AppIcons.chevronDown,
                size: AppSpacing.iconSm,
                color: isLight ? AppColors.iconGrey : AppColors.grey,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
