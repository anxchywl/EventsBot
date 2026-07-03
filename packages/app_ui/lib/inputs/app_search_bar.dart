import 'package:flutter/material.dart';

import '../icons/app_icon.dart';
import '../icons/app_icons.dart';
import '../tokens/app_colors.dart';

/// Global search bar widget for Hub and other search-enabled pages.
class GlobalSearchBar extends StatelessWidget {
  const GlobalSearchBar({
    super.key,
    this.controller,
    this.hint,
    this.onChanged,
    this.onSubmitted,
    this.onTap,
    this.onClear,
    this.enabled = true,
    this.autofocus = false,
    this.focusNode,
    this.showFilterButton = false,
    this.onFilterPressed,
  });

  final TextEditingController? controller;
  final String? hint;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final VoidCallback? onTap;
  final VoidCallback? onClear;
  final bool enabled;
  final bool autofocus;
  final FocusNode? focusNode;
  final bool showFilterButton;
  final VoidCallback? onFilterPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;

    return Container(
      height: 48,
      decoration: BoxDecoration(
        color: isLight ? AppColors.fieldBackground : const Color(0xFF2E2E2E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          const SizedBox(width: 12),
          AppIcon(AppIcons.search, size: 20, color: AppColors.grey),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              decoration: const InputDecoration(
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                filled: false,
                contentPadding: EdgeInsets.zero,
                isDense: true,
              ),
              style: theme.textTheme.bodyMedium,
              onChanged: onChanged,
              onSubmitted: onSubmitted,
              onTap: onTap,
              enabled: enabled,
              autofocus: autofocus,
            ),
          ),
          if (controller?.text.isNotEmpty ?? false) ...[
            IconButton(
              icon: AppIcon(AppIcons.close, size: 20),
              onPressed: () {
                controller?.clear();
                onClear?.call();
              },
              color: AppColors.grey,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
            ),
          ],
          if (showFilterButton) ...[
            Container(height: 24, width: 1, color: AppColors.dividerColor),
            IconButton(
              icon: AppIcon(AppIcons.filter, size: 20, color: AppColors.grey),
              onPressed: onFilterPressed,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
            ),
          ] else ...[
            const SizedBox(width: 12),
          ],
        ],
      ),
    );
  }
}
