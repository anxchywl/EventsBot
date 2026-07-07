import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';

/// OTP/PIN input field with individual digit boxes.
/// 
/// Example:
/// ```dart
/// AppOtpField(
///   length: 6,
///   onCompleted: (code) => verifyCode(code),
/// )
/// ```
class AppOtpField extends StatefulWidget {
  const AppOtpField({
    super.key,
    this.length = 6,
    this.onChanged,
    this.onCompleted,
    this.errorText,
    this.autofocus = true,
    this.enabled = true,
    this.obscureText = false,
    this.fieldWidth = 48,
    this.fieldHeight = 56,
  });

  /// Number of OTP digits.
  final int length;
  
  /// Callback when any digit changes.
  final ValueChanged<String>? onChanged;
  
  /// Callback when all digits are entered.
  final ValueChanged<String>? onCompleted;
  
  /// Error text to display below.
  final String? errorText;
  
  /// Whether to autofocus the first field.
  final bool autofocus;
  
  /// Whether the fields are enabled.
  final bool enabled;
  
  /// Whether to obscure the digits.
  final bool obscureText;
  
  /// Width of each digit field.
  final double fieldWidth;
  
  /// Height of each digit field.
  final double fieldHeight;

  @override
  State<AppOtpField> createState() => _AppOtpFieldState();
}

class _AppOtpFieldState extends State<AppOtpField> {
  late List<TextEditingController> _controllers;
  late List<FocusNode> _focusNodes;

  @override
  void initState() {
    super.initState();
    _controllers = List.generate(widget.length, (_) => TextEditingController());
    _focusNodes = List.generate(widget.length, (_) => FocusNode());
  }

  @override
  void dispose() {
    for (final controller in _controllers) {
      controller.dispose();
    }
    for (final node in _focusNodes) {
      node.dispose();
    }
    super.dispose();
  }

  String get _currentValue => _controllers.map((c) => c.text).join();

  void _onChanged(int index, String value) {
    if (value.length > 1) {
      // Handle paste
      final pastedValue = value.replaceAll(RegExp(r'[^0-9]'), '');
      for (var i = 0; i < widget.length && i < pastedValue.length; i++) {
        _controllers[i].text = pastedValue[i];
      }
      final focusIndex = (pastedValue.length < widget.length) 
          ? pastedValue.length 
          : widget.length - 1;
      _focusNodes[focusIndex].requestFocus();
    } else if (value.isNotEmpty && index < widget.length - 1) {
      _focusNodes[index + 1].requestFocus();
    }
    
    final currentValue = _currentValue;
    widget.onChanged?.call(currentValue);
    
    if (currentValue.length == widget.length) {
      widget.onCompleted?.call(currentValue);
    }
  }

  void _onKeyEvent(int index, KeyEvent event) {
    if (event is KeyDownEvent &&
        event.logicalKey == LogicalKeyboardKey.backspace &&
        _controllers[index].text.isEmpty &&
        index > 0) {
      _focusNodes[index - 1].requestFocus();
      _controllers[index - 1].clear();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final hasError = widget.errorText != null && widget.errorText!.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(widget.length, (index) {
            return Padding(
              padding: EdgeInsets.only(
                left: index == 0 ? 0 : AppSpacing.sm,
              ),
              child: _buildDigitField(index, isLight, hasError),
            );
          }),
        ),
        if (hasError) ...[
          AppSpacing.verticalSm,
          Text(
            widget.errorText!,
            style: AppTextStyles.error.copyWith(color: AppColors.error),
          ),
        ],
      ],
    );
  }

  Widget _buildDigitField(int index, bool isLight, bool hasError) {
    final isFocused = _focusNodes[index].hasFocus;
    final borderColor = hasError
        ? AppColors.error
        : isFocused
            ? AppColors.primary
            : AppColors.transparent;

    return SizedBox(
      width: widget.fieldWidth,
      height: widget.fieldHeight,
      child: KeyboardListener(
        focusNode: FocusNode(),
        onKeyEvent: (event) => _onKeyEvent(index, event),
        child: TextField(
          controller: _controllers[index],
          focusNode: _focusNodes[index],
          enabled: widget.enabled,
          autofocus: widget.autofocus && index == 0,
          obscureText: widget.obscureText,
          textAlign: TextAlign.center,
          keyboardType: TextInputType.number,
          maxLength: 1,
          style: AppTextStyles.code.copyWith(
            color: isLight ? AppColors.textPrimary : AppColors.textPrimaryDark,
          ),
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
          ],
          decoration: InputDecoration(
            counterText: '',
            filled: true,
            fillColor: isLight ? AppColors.fieldBackground : AppColors.surfaceDark,
            contentPadding: EdgeInsets.zero,
            border: OutlineInputBorder(
              borderRadius: AppSpacing.borderRadiusMd,
              borderSide: BorderSide(color: borderColor, width: 1.5),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: AppSpacing.borderRadiusMd,
              borderSide: BorderSide(color: borderColor, width: 1.5),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: AppSpacing.borderRadiusMd,
              borderSide: BorderSide(
                color: hasError ? AppColors.error : AppColors.primary,
                width: 1.5,
              ),
            ),
          ),
          onChanged: (value) => _onChanged(index, value),
        ),
      ),
    );
  }
}
