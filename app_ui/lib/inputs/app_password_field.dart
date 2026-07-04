import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../icons/app_icons.dart';
import '../icons/app_icon.dart';
import 'app_text_field.dart';

/// Password input field with visibility toggle.
/// 
/// Example:
/// ```dart
/// AppPasswordField(
///   controller: _passwordController,
///   label: 'Password',
/// )
/// ```
class AppPasswordField extends StatefulWidget {
  const AppPasswordField({
    super.key,
    this.controller,
    this.label,
    this.hint,
    this.errorText,
    this.helperText,
    this.onChanged,
    this.onSubmitted,
    this.validator,
    this.enabled = true,
    this.autofocus = false,
    this.focusNode,
    this.textInputAction,
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
  
  /// Callback when text changes.
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

  @override
  State<AppPasswordField> createState() => _AppPasswordFieldState();
}

class _AppPasswordFieldState extends State<AppPasswordField> {
  bool _obscureText = true;

  void _toggleVisibility() {
    setState(() {
      _obscureText = !_obscureText;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;

    return AppTextField(
      controller: widget.controller,
      label: widget.label,
      hint: widget.hint,
      errorText: widget.errorText,
      helperText: widget.helperText,
      onChanged: widget.onChanged,
      onSubmitted: widget.onSubmitted,
      validator: widget.validator,
      enabled: widget.enabled,
      autofocus: widget.autofocus,
      focusNode: widget.focusNode,
      textInputAction: widget.textInputAction,
      obscureText: _obscureText,
      prefixIcon: AppIcon(
        AppIcons.lock,
        color: isLight ? AppColors.iconGrey : AppColors.grey,
      ),
      suffixIcon: IconButton(
        icon: AppIcon(
          _obscureText ? AppIcons.visibility : AppIcons.visibilityOff,
          color: isLight ? AppColors.iconGrey : AppColors.grey,
        ),
        onPressed: widget.enabled ? _toggleVisibility : null,
      ),
    );
  }
}
