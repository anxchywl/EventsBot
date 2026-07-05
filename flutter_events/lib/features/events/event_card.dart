import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../models/event_model.dart';

class EventCard extends StatelessWidget {
  const EventCard({
    super.key,
    required this.event,
    this.onTap,
    this.alwaysShowStatus = false,
    this.hideStatus = false,
    this.mutedPending = false,
    this.isFavorite = false,
    this.onToggleFavorite,
    this.statusLabelOverride,
    this.showCategory = true,
  });

  final EventModel event;
  final VoidCallback? onTap;
  final bool alwaysShowStatus;
  final bool hideStatus;
  final bool mutedPending;
  final bool isFavorite;
  final VoidCallback? onToggleFavorite;
  final bool showCategory;

  /// Overrides the status footer text, e.g. queue-specific badges shown to
  /// moderators ("Waiting for creator" / "Ready for review").
  final String? statusLabelOverride;

  String? _timeUntilLabel() {
    try {
      final dateParts = event.eventDate.split('-');
      final timeParts = event.eventTime.split(':');
      if (dateParts.length != 3 || timeParts.length < 2) return null;

      final eventDateTime = DateTime(
        int.parse(dateParts[0]),
        int.parse(dateParts[1]),
        int.parse(dateParts[2]),
        int.parse(timeParts[0]),
        int.parse(timeParts[1]),
      );
      final diff = eventDateTime.difference(DateTime.now());
      if (diff.isNegative) return null;

      final minutes = diff.inMinutes;
      if (minutes < 60) return '${minutes < 1 ? 1 : minutes}m';

      final hours = diff.inHours;
      if (hours < 24) return '${hours}h';

      return '${diff.inDays}d';
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final showStatus = !hideStatus && (alwaysShowStatus || !event.isApproved);
    final isMutedPending = mutedPending && event.isPending;
    final timeUntil = _timeUntilLabel();

    return AppCard(
      onTap: onTap,
      padding: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                // Cover image / gradient thumbnail (with heart overlay)
                Stack(
                  children: [
                    ClipRRect(
                      borderRadius: AppSpacing.borderRadiusSm,
                      child: SizedBox(
                        width: showCategory ? 72 : 76,
                        height: showCategory ? 72 : 76,
                        child: event.coverUrl != null
                            ? Image.network(
                                event.coverUrl!,
                                fit: BoxFit.cover,
                                errorBuilder: (_, e, s) => const _MutedThumb(),
                              )
                            : const _MutedThumb(),
                      ),
                    ),
                    if (onToggleFavorite != null)
                      Positioned(
                        bottom: 4,
                        right: 4,
                        child: GestureDetector(
                          onTap: onToggleFavorite,
                          child: Container(
                            width: 24,
                            height: 24,
                            decoration: BoxDecoration(
                              color: AppColors.black.withValues(alpha: 0.35),
                              shape: BoxShape.circle,
                            ),
                            child: AppIcon(
                              AppIcons.heart,
                              size: 13,
                              color: isFavorite
                                  ? AppColors.error
                                  : AppColors.white,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(width: AppSpacing.md),
                // Content
                Expanded(
                  child: showCategory
                      ? _EventCardText(
                          event: event,
                          theme: theme,
                          minHeight: 72,
                          footer: Row(
                            children: [
                              _Pill(
                                background: isMutedPending
                                    ? AppColors.fieldBackground
                                    : AppColors.primaryLight,
                                foreground: isMutedPending
                                    ? AppColors.grey
                                    : AppColors.primary,
                                label: event.category,
                              ),
                              const Spacer(),
                              if (timeUntil != null)
                                _TimeUntilLabel(text: timeUntil, theme: theme),
                            ],
                          ),
                        )
                      : Row(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            Expanded(
                              child: _EventCardText(
                                event: event,
                                theme: theme,
                                minHeight: 76,
                              ),
                            ),
                            if (timeUntil != null) ...[
                              const SizedBox(width: AppSpacing.sm),
                              _TimeUntilLabel(text: timeUntil, theme: theme),
                            ],
                          ],
                        ),
                ),
              ],
            ),
          ),
          if (showStatus)
            Container(
              padding: const EdgeInsets.symmetric(
                vertical: AppSpacing.sm,
                horizontal: AppSpacing.md,
              ),
              color: isMutedPending
                  ? AppColors.fieldBackground
                  : event.statusColor.withValues(alpha: 0.12),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      statusLabelOverride ?? event.statusLabel,
                      style: AppTextStyles.bodySmall.copyWith(
                        color: isMutedPending
                            ? AppColors.grey
                            : event.statusColor,
                        fontWeight: FontWeight.w600,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _EventCardText extends StatelessWidget {
  const _EventCardText({
    required this.event,
    required this.theme,
    required this.minHeight,
    this.footer,
  });

  final EventModel event;
  final ThemeData theme;
  final double minHeight;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: BoxConstraints(minHeight: minHeight),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            event.title,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w600,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 3),
          Text(
            event.organizerName,
            style: theme.textTheme.bodySmall?.copyWith(
              color: AppColors.textSecondary,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          Text(
            event.location,
            style: theme.textTheme.bodySmall?.copyWith(
              color: AppColors.textSecondary,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          if (footer != null) ...[
            const SizedBox(height: AppSpacing.xs),
            footer!,
          ],
        ],
      ),
    );
  }
}

class _TimeUntilLabel extends StatelessWidget {
  const _TimeUntilLabel({required this.text, required this.theme});

  final String text;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: theme.textTheme.bodySmall?.copyWith(
        color: AppColors.textSecondary,
        fontWeight: FontWeight.w500,
      ),
    );
  }
}

class _MutedThumb extends StatelessWidget {
  const _MutedThumb();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.fieldBackground,
            AppColors.grey.withValues(alpha: 0.28),
            AppColors.fieldBackground,
          ],
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({
    required this.background,
    required this.foreground,
    required this.label,
  });

  final Color background;
  final Color foreground;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: 3,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: AppSpacing.borderRadiusSm,
      ),
      child: Text(
        label,
        style: AppTextStyles.badge.copyWith(color: foreground),
      ),
    );
  }
}
