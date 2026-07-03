import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../icons/app_icon.dart';
import '../icons/app_icons.dart';
import '../tokens/app_colors.dart';

// ─────────────────────────────────────────────────────────────────────────────
// AppBottomSheet
//
// Premium-styled bottom sheet that matches AppPremiumDialog's visual language:
// same surface colours, corner radius, drag handle, typography, and spacing.
//
// Three entry points:
//
//   AppBottomSheet.show(...)          — arbitrary content
//   AppBottomSheet.showSelection(...) — icon + title + subtitle option list
//
// Example:
//   final kind = await AppBottomSheet.showSelection<_Kind>(
//     context: context,
//     title: 'Choose media',
//     options: [ AppBottomSheetOption(title: 'Photo', value: _Kind.photo, ...) ],
//   );
// ─────────────────────────────────────────────────────────────────────────────

class AppBottomSheet {
  AppBottomSheet._();

  /// Show a bottom sheet with arbitrary [child] content.
  static Future<T?> show<T>({
    required BuildContext context,
    required Widget child,
    String? title,
    bool isDismissible = true,
    bool enableDrag = true,
    double? maxHeightFraction,
  }) {
    HapticFeedback.selectionClick();
    return showModalBottomSheet<T>(
      context: context,
      isDismissible: isDismissible,
      enableDrag: enableDrag,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.48),
      builder: (_) => _Sheet<T>(
        title: title,
        maxHeightFraction: maxHeightFraction ?? 0.9,
        child: child,
      ),
    );
  }

  /// Show a premium option-list bottom sheet.
  ///
  /// Each option renders a leading icon container, title, optional subtitle,
  /// and a check-mark on the selected value.
  static Future<T?> showSelection<T>({
    required BuildContext context,
    required String title,
    required List<AppBottomSheetOption<T>> options,
    T? selectedValue,
  }) {
    HapticFeedback.selectionClick();
    return showModalBottomSheet<T>(
      context: context,
      isDismissible: true,
      enableDrag: true,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.48),
      builder: (_) => _SelectionSheet<T>(
        title: title,
        options: options,
        selectedValue: selectedValue,
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Option model
// ─────────────────────────────────────────────────────────────────────────────

class AppBottomSheetOption<T> {
  const AppBottomSheetOption({
    required this.title,
    required this.value,
    this.subtitle,
    this.leading,
  });

  final String title;
  final T value;
  final String? subtitle;

  /// Optional leading widget. Typically a 40×40 branded circle icon.
  final Widget? leading;
}

// ─────────────────────────────────────────────────────────────────────────────
// _Sheet — generic content wrapper
// ─────────────────────────────────────────────────────────────────────────────

class _Sheet<T> extends StatelessWidget {
  const _Sheet({
    required this.child,
    this.title,
    this.maxHeightFraction = 0.9,
  });

  final Widget child;
  final String? title;
  final double maxHeightFraction;

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final isLight = Theme.of(context).brightness == Brightness.light;
    final surface = isLight ? Colors.white : const Color(0xFF1C1C1E);
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;

    return Container(
      constraints: BoxConstraints(maxHeight: mq.size.height * maxHeightFraction),
      decoration: BoxDecoration(
        color: surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Drag handle ──────────────────────────────────────────
            _DragHandle(isLight: isLight),

            // ── Optional title ───────────────────────────────────────
            if (title != null) ...[
              const SizedBox(height: 2),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                child: Text(
                  title!,
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -0.3,
                    color: textPrimary,
                    height: 1.2,
                  ),
                ),
              ),
            ] else
              const SizedBox(height: 4),

            // ── Content ──────────────────────────────────────────────
            Flexible(
              child: SingleChildScrollView(child: child),
            ),

            SizedBox(height: mq.padding.bottom + 8),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// _SelectionSheet — option list
// ─────────────────────────────────────────────────────────────────────────────

class _SelectionSheet<T> extends StatelessWidget {
  const _SelectionSheet({
    required this.title,
    required this.options,
    this.selectedValue,
  });

  final String title;
  final List<AppBottomSheetOption<T>> options;
  final T? selectedValue;

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final isLight = Theme.of(context).brightness == Brightness.light;
    final surface = isLight ? Colors.white : const Color(0xFF1C1C1E);
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;
    final textSub = isLight ? const Color(0xFF6B6B80) : const Color(0xFF8E8EA3);
    final divider = isLight
        ? Colors.black.withValues(alpha: 0.06)
        : Colors.white.withValues(alpha: 0.06);

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Drag handle ──────────────────────────────────────────
            _DragHandle(isLight: isLight),

            // ── Title ────────────────────────────────────────────────
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 16),
              child: Text(
                title,
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -0.3,
                  color: textPrimary,
                  height: 1.2,
                ),
              ),
            ),

            // ── Options ──────────────────────────────────────────────
            ...List.generate(options.length, (i) {
              final option = options[i];
              final isSelected = option.value == selectedValue;
              final isLast = i == options.length - 1;

              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _OptionTile(
                    option: option,
                    isSelected: isSelected,
                    textPrimary: textPrimary,
                    textSub: textSub,
                    onTap: () {
                      HapticFeedback.selectionClick();
                      Navigator.of(context).pop(option.value);
                    },
                  ),
                  if (!isLast)
                    Divider(
                      height: 1,
                      indent: option.leading != null ? 72 : 20,
                      endIndent: 20,
                      color: divider,
                    ),
                ],
              );
            }),

            SizedBox(height: mq.padding.bottom + 12),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// _OptionTile
// ─────────────────────────────────────────────────────────────────────────────

class _OptionTile<T> extends StatefulWidget {
  const _OptionTile({
    required this.option,
    required this.isSelected,
    required this.textPrimary,
    required this.textSub,
    required this.onTap,
  });

  final AppBottomSheetOption<T> option;
  final bool isSelected;
  final Color textPrimary;
  final Color textSub;
  final VoidCallback onTap;

  @override
  State<_OptionTile<T>> createState() => _OptionTileState<T>();
}

class _OptionTileState<T> extends State<_OptionTile<T>> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final pressedColor = isLight
        ? Colors.black.withValues(alpha: 0.04)
        : Colors.white.withValues(alpha: 0.04);

    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 80),
        color: _pressed ? pressedColor : Colors.transparent,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 13),
        child: Row(
          children: [
            // ── Leading icon ─────────────────────────────────────
            if (widget.option.leading != null) ...[
              widget.option.leading!,
              const SizedBox(width: 14),
            ],

            // ── Text ─────────────────────────────────────────────
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    widget.option.title,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: widget.isSelected
                          ? FontWeight.w600
                          : FontWeight.w500,
                      color: widget.textPrimary,
                      height: 1.3,
                    ),
                  ),
                  if (widget.option.subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      widget.option.subtitle!,
                      style: TextStyle(
                        fontSize: 13,
                        color: widget.textSub,
                        height: 1.3,
                      ),
                    ),
                  ],
                ],
              ),
            ),

            // ── Selection check ───────────────────────────────────
            if (widget.isSelected) ...[
              SizedBox(width: 12),
              AppIcon(
                AppIcons.check,
                size: 18,
                color: AppColors.primary,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// _DragHandle
// ─────────────────────────────────────────────────────────────────────────────

class _DragHandle extends StatelessWidget {
  const _DragHandle({required this.isLight});
  final bool isLight;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Container(
          width: 32,
          height: 4,
          decoration: BoxDecoration(
            color: isLight
                ? const Color(0xFFD1D1D6)
                : const Color(0xFF48484A),
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      ),
    );
  }
}
