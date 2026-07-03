import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../models/event_model.dart';

/// Compact event card used by the events feed and the submissions list.
class EventCard extends StatelessWidget {
  const EventCard({
    super.key,
    required this.event,
    this.onTap,
    this.alwaysShowStatus = false,
  });

  final EventModel event;
  final VoidCallback? onTap;

  /// When true the status chip is shown even for approved events.
  final bool alwaysShowStatus;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final showStatus = alwaysShowStatus || !event.isApproved;

    return AppCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _CategoryBadge(label: event.category),
              const Spacer(),
              if (showStatus) _StatusChip(event: event),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            event.title,
            style: theme.textTheme.titleMedium,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            children: [
              const Icon(
                Icons.calendar_today_outlined,
                size: 14,
                color: AppColors.grey,
              ),
              const SizedBox(width: 4),
              Text(
                '${event.eventDate} · ${event.eventTime}',
                style: theme.textTheme.bodySmall?.copyWith(color: AppColors.grey),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            children: [
              const Icon(
                Icons.location_on_outlined,
                size: 14,
                color: AppColors.grey,
              ),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  event.location,
                  style:
                      theme.textTheme.bodySmall?.copyWith(color: AppColors.grey),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CategoryBadge extends StatelessWidget {
  const _CategoryBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return _Pill(
      background: AppColors.primaryLight,
      foreground: AppColors.primary,
      label: label,
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.event});

  final EventModel event;

  @override
  Widget build(BuildContext context) {
    return _Pill(
      background: event.statusColor.withValues(alpha: 0.15),
      foreground: event.statusColor,
      label: event.statusLabel,
    );
  }
}

/// Small rounded label shared by the category badge and status chip.
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
        vertical: AppSpacing.xs,
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
