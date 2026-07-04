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
  });

  final EventModel event;
  final VoidCallback? onTap;
  final bool alwaysShowStatus;
  final bool hideStatus;
  final bool mutedPending;
  final bool isFavorite;
  final VoidCallback? onToggleFavorite;


  int? _daysUntil() {
    try {
      final parts = event.eventDate.split('-');
      if (parts.length != 3) return null;
      final date = DateTime(
        int.parse(parts[0]),
        int.parse(parts[1]),
        int.parse(parts[2]),
      );
      final diff = date.difference(DateTime.now()).inDays;
      return diff < 0 ? null : diff;
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final showStatus = !hideStatus && (alwaysShowStatus || !event.isApproved);
    final isMutedPending = mutedPending && event.isPending;
    final days = _daysUntil();

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
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Cover image / gradient thumbnail (with heart overlay)
                Stack(
                  children: [
                    ClipRRect(
                      borderRadius: AppSpacing.borderRadiusSm,
                      child: SizedBox(
                        width: 72,
                        height: 72,
                        child: event.coverUrl != null
                            ? Image.network(
                                event.coverUrl!,
                                fit: BoxFit.cover,
                                errorBuilder: (_, e, s) =>
                                    const _MutedThumb(),
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
                              color: Colors.black.withValues(alpha: 0.35),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              isFavorite
                                  ? Icons.favorite_rounded
                                  : Icons.favorite_border_rounded,
                              size: 13,
                              color: isFavorite ? Colors.red[300] : Colors.white,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(width: AppSpacing.md),
                // Content
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
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
                      const SizedBox(height: AppSpacing.xs),
                      Row(
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
                          if (days != null)
                            Text(
                              '${days}d',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: AppColors.textSecondary,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                        ],
                      ),
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
                  if (event.status != 'approved' &&
                      event.status != 'rejected' &&
                      event.status != 'pending') ...[
                    Icon(
                      Icons.info_outline_rounded,
                      size: 14,
                      color: isMutedPending ? AppColors.grey : event.statusColor,
                    ),
                    const SizedBox(width: AppSpacing.xs),
                  ],
                  Expanded(
                    child: Text(
                      event.statusLabel,
                      style: AppTextStyles.bodySmall.copyWith(
                        color: isMutedPending ? AppColors.grey : event.statusColor,
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
