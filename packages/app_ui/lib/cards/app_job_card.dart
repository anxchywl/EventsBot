import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';
import 'app_card.dart';

/// Job listing card for job finder feature.
/// 
/// Example:
/// ```dart
/// AppJobCard(
///   title: 'Flutter Developer',
///   company: 'Tech Corp',
///   location: 'Almaty',
///   salary: '500,000 - 800,000 KZT',
///   onTap: () => navigateToJobDetails(),
/// )
/// ```
class AppJobCard extends StatelessWidget {
  const AppJobCard({
    super.key,
    required this.title,
    required this.company,
    this.location,
    this.salary,
    this.employmentType,
    this.logoUrl,
    this.logoWidget,
    this.tags = const [],
    this.isPromoted = false,
    this.isFavorite = false,
    this.onTap,
    this.onFavoritePressed,
    this.postedAt,
  });

  /// Job title.
  final String title;

  /// Company name.
  final String company;

  /// Job location.
  final String? location;

  /// Salary range.
  final String? salary;

  /// Employment type (Full-time, Part-time, etc.).
  final String? employmentType;

  /// Company logo URL.
  final String? logoUrl;

  /// Custom logo widget.
  final Widget? logoWidget;

  /// Tags/skills for the job.
  final List<String> tags;

  /// Whether the job is promoted.
  final bool isPromoted;

  /// Whether the job is favorited.
  final bool isFavorite;

  /// Tap callback.
  final VoidCallback? onTap;

  /// Favorite button callback.
  final VoidCallback? onFavoritePressed;

  /// When the job was posted.
  final String? postedAt;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final textColor = isLight ? AppColors.textPrimary : AppColors.textPrimaryDark;

    return AppCard(
      onTap: onTap,
      backgroundColor: isPromoted 
          ? AppColors.infoLight.withValues(alpha: 0.3)
          : null,
      border: isPromoted
          ? Border.all(color: AppColors.promotedBlue.withValues(alpha: 0.3))
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header with logo and favorite button
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildLogo(),
              AppSpacing.horizontalMd,
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: AppTextStyles.titleSmall.copyWith(
                        color: textColor,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    AppSpacing.verticalXs,
                    Text(
                      company,
                      style: AppTextStyles.bodySmall.copyWith(
                        color: AppColors.grey,
                      ),
                    ),
                  ],
                ),
              ),
              if (onFavoritePressed != null)
                IconButton(
                  onPressed: onFavoritePressed,
                  icon: Icon(
                    isFavorite ? Icons.favorite : Icons.favorite_border,
                    color: isFavorite ? AppColors.error : AppColors.grey,
                    size: AppSpacing.iconDf,
                  ),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
            ],
          ),
          AppSpacing.verticalMd,
          // Details
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            children: [
              if (location != null)
                _buildInfoChip(Icons.location_on_outlined, location!),
              if (employmentType != null)
                _buildInfoChip(Icons.work_outline_rounded, employmentType!),
              if (postedAt != null)
                _buildInfoChip(Icons.access_time, postedAt!),
            ],
          ),
          if (salary != null) ...[
            AppSpacing.verticalMd,
            Text(
              salary!,
              style: AppTextStyles.titleSmall.copyWith(
                color: AppColors.success,
              ),
            ),
          ],
          if (tags.isNotEmpty) ...[
            AppSpacing.verticalMd,
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: tags.take(5).map((tag) => _buildTag(tag)).toList(),
            ),
          ],
          if (isPromoted) ...[
            AppSpacing.verticalMd,
            Container(
              padding: AppSpacing.tagPadding,
              decoration: BoxDecoration(
                color: AppColors.promotedBlue,
                borderRadius: AppSpacing.borderRadiusXs,
              ),
              child: Text(
                'PROMOTED',
                style: AppTextStyles.badge.copyWith(
                  color: AppColors.white,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildLogo() {
    if (logoWidget != null) {
      return SizedBox(
        width: AppSpacing.avatarDf,
        height: AppSpacing.avatarDf,
        child: logoWidget,
      );
    }

    return Container(
      width: AppSpacing.avatarDf,
      height: AppSpacing.avatarDf,
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: AppSpacing.borderRadiusSm,
      ),
      child: logoUrl != null
          ? ClipRRect(
              borderRadius: AppSpacing.borderRadiusSm,
              child: Image.network(
                logoUrl!,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => _defaultLogo(),
              ),
            )
          : _defaultLogo(),
    );
  }

  Widget _defaultLogo() {
    return Icon(
      Icons.business,
      size: AppSpacing.iconDf,
      color: AppColors.iconGrey,
    );
  }

  Widget _buildInfoChip(IconData icon, String text) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          icon,
          size: AppSpacing.iconSm,
          color: AppColors.grey,
        ),
        AppSpacing.horizontalXs,
        Text(
          text,
          style: AppTextStyles.bodySmall.copyWith(
            color: AppColors.grey,
          ),
        ),
      ],
    );
  }

  Widget _buildTag(String tag) {
    return Container(
      padding: AppSpacing.tagPadding,
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: AppSpacing.borderRadiusXs,
      ),
      child: Text(
        tag,
        style: AppTextStyles.chip.copyWith(
          color: AppColors.primary,
        ),
      ),
    );
  }
}
