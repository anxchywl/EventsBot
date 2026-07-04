import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../icons/app_icon.dart';
import '../icons/app_icon_data.dart';

/// Apple Wallet-style bottom confirmation sheet.
///
/// Slides up from the bottom with a handle indicator, contextual icon,
/// editorial typography, and native-feeling action buttons. Identical API
/// to the previous center-dialog version — all callers work unchanged.
///
/// ```dart
/// final confirmed = await AppPremiumDialog.show(
///   context: context,
///   icon: AppIcons.logout,
///   iconColor: Color(0xFFFF3B30),
///   title: 'Log out?',
///   description: 'You will need to sign in again.',
///   confirmText: 'Log out',
///   cancelText: 'Cancel',
///   isDestructive: true,
/// );
/// ```
class AppPremiumDialog {
  AppPremiumDialog._();

  static Future<bool> show({
    required BuildContext context,
    required AppIconData icon,
    required Color iconColor,
    required String title,
    required String description,
    required String confirmText,
    required String cancelText,
    bool isDestructive = false,
    bool showIcon = true,
    String? warningText,
  }) async {
    HapticFeedback.mediumImpact();
    final result = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.48),
      isScrollControlled: true,
      enableDrag: true,
      builder: (ctx) => _PremiumConfirmSheet(
        icon: icon,
        iconColor: iconColor,
        title: title,
        description: description,
        confirmText: confirmText,
        cancelText: cancelText,
        isDestructive: isDestructive,
        showIcon: showIcon,
        warningText: warningText,
      ),
    );
    return result ?? false;
  }
}

class _PremiumConfirmSheet extends StatelessWidget {
  const _PremiumConfirmSheet({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.description,
    required this.confirmText,
    required this.cancelText,
    required this.isDestructive,
    this.showIcon = true,
    this.warningText,
  });

  final AppIconData icon;
  final Color iconColor;
  final String title;
  final String description;
  final String confirmText;
  final String cancelText;
  final bool isDestructive;
  final bool showIcon;
  final String? warningText;

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final surface = isLight ? Colors.white : const Color(0xFF1C1C1E);
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;
    final textSub = isLight ? const Color(0xFF6B6B80) : const Color(0xFF8E8EA3);
    final confirmColor = isDestructive ? const Color(0xFFFF3B30) : iconColor;
    final bottom = MediaQuery.of(context).padding.bottom;

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: EdgeInsets.fromLTRB(20, 8, 20, bottom + 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle indicator
          Container(
            width: 32,
            height: 4,
            decoration: BoxDecoration(
              color: isLight
                  ? const Color(0xFFD1D1D6)
                  : const Color(0xFF48484A),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          SizedBox(height: showIcon ? 18 : 14),

          if (showIcon) ...[
            // Contextual icon
            Container(
              width: 54,
              height: 54,
              decoration: BoxDecoration(
                color: iconColor.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(16),
              ),
              child: AppIcon(icon, color: iconColor, size: 26),
            ),
            const SizedBox(height: 12),
          ],

          // Title
          Text(
            title,
            style: TextStyle(
              fontSize: showIcon ? 18 : 16,
              fontWeight: FontWeight.w600,
              letterSpacing: -0.3,
              color: textPrimary,
              height: 1.2,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 4),

          // Description
          Text(
            description,
            style: TextStyle(
              fontSize: 13,
              color: textSub,
              height: 1.4,
            ),
            textAlign: TextAlign.center,
          ),

          // Optional warning chip
          if (warningText != null) ...[
            const SizedBox(height: 10),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: const Color(0xFFFF9500).withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.info_outline_rounded,
                    size: 13,
                    color: Color(0xFFFF9500),
                  ),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      warningText!,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: Color(0xFFFF9500),
                        height: 1.4,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          ],

          const SizedBox(height: 16),

          Row(
            children: [
              // Cancel — smaller, tinted
              GestureDetector(
                onTap: () {
                  HapticFeedback.selectionClick();
                  Navigator.of(context).pop(false);
                },
                child: Container(
                  height: 44,
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  decoration: BoxDecoration(
                    color: isLight
                        ? const Color(0xFFF2F2F7)
                        : const Color(0xFF2C2C2E),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    cancelText,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: textSub,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              // Confirm — fills remaining space
              Expanded(
                child: GestureDetector(
                  onTap: () {
                    HapticFeedback.lightImpact();
                    Navigator.of(context).pop(true);
                  },
                  child: Container(
                    height: 44,
                    decoration: BoxDecoration(
                      color: confirmColor,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      confirmText,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        letterSpacing: -0.2,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
