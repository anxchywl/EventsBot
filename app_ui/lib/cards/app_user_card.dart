import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';
import 'app_card.dart';

/// User card displaying avatar, name, and optional info.
/// Use in user lists, search results, followers, etc.
/// 
/// Example:
/// ```dart
/// AppUserCard(
///   name: 'John Doe',
///   subtitle: '@johndoe',
///   avatarUrl: 'https://...',
///   onTap: () => navigateToProfile(),
/// )
/// ```
class AppUserCard extends StatelessWidget {
  const AppUserCard({
    super.key,
    required this.name,
    this.subtitle,
    this.avatarUrl,
    this.avatarWidget,
    this.trailing,
    this.onTap,
    this.isVerified = false,
    this.avatarSize = AppSpacing.avatarDf,
    this.padding,
    this.backgroundColor,
  });

  /// User's display name.
  final String name;

  /// Subtitle text (username, role, etc.).
  final String? subtitle;

  /// Avatar image URL.
  final String? avatarUrl;

  /// Custom avatar widget (takes precedence over avatarUrl).
  final Widget? avatarWidget;

  /// Trailing widget (action button, status, etc.).
  final Widget? trailing;

  /// Tap callback.
  final VoidCallback? onTap;

  /// Whether to show verified badge.
  final bool isVerified;

  /// Avatar size.
  final double avatarSize;

  /// Custom padding.
  final EdgeInsets? padding;

  /// Custom background color.
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final textColor = isLight ? AppColors.textPrimary : AppColors.textPrimaryDark;

    return AppCard(
      padding: padding ?? AppSpacing.listItemPadding,
      backgroundColor: backgroundColor,
      onTap: onTap,
      child: Row(
        children: [
          // Avatar
          _buildAvatar(isLight),
          AppSpacing.horizontalMd,
          // Name and subtitle
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        name,
                        style: AppTextStyles.titleSmall.copyWith(
                          color: textColor,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (isVerified) ...[
                      AppSpacing.horizontalXs,
                      Icon(
                        Icons.verified,
                        size: AppSpacing.iconSm,
                        color: AppColors.primary,
                      ),
                    ],
                  ],
                ),
                if (subtitle != null) ...[
                  AppSpacing.verticalXs,
                  Text(
                    subtitle!,
                    style: AppTextStyles.bodySmall.copyWith(
                      color: AppColors.grey,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
          // Trailing
          if (trailing != null) ...[
            AppSpacing.horizontalMd,
            trailing!,
          ],
        ],
      ),
    );
  }

  Widget _buildAvatar(bool isLight) {
    if (avatarWidget != null) {
      return SizedBox(
        width: avatarSize,
        height: avatarSize,
        child: avatarWidget,
      );
    }

    return CircleAvatar(
      radius: avatarSize / 2,
      backgroundColor: AppColors.primaryLight,
      backgroundImage: avatarUrl != null ? NetworkImage(avatarUrl!) : null,
      child: avatarUrl == null
          ? Icon(
              Icons.person,
              size: avatarSize * 0.6,
              color: AppColors.primary,
            )
          : null,
    );
  }
}
