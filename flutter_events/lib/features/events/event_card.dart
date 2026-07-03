import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../models/event_model.dart';

class EventCard extends StatelessWidget {
  const EventCard({
    super.key,
    required this.event,
    this.onTap,
    this.alwaysShowStatus = false,
    this.isFavorite = false,
    this.onToggleFavorite,
  });

  final EventModel event;
  final VoidCallback? onTap;
  final bool alwaysShowStatus;
  final bool isFavorite;
  final VoidCallback? onToggleFavorite;

  // Deterministic vibrant gradient seeded by event id, mirroring the Mini App.
  LinearGradient _gradient() {
    final seed = event.id;
    final h1 = (seed * 137) % 360;
    final h2 = (h1 + 90 + seed * 37 % 90) % 360;
    final h3 = (h2 + 90 + seed * 17 % 90) % 360;
    final angle = (seed * 73) % 360;
    final a = HSLColor.fromAHSL(1, h1.toDouble(), 0.95, 0.65).toColor();
    final b = HSLColor.fromAHSL(1, h2.toDouble(), 0.95, 0.65).toColor();
    final c = HSLColor.fromAHSL(1, h3.toDouble(), 0.95, 0.72).toColor();
    final rad = angle * 3.14159 / 180;
    return LinearGradient(
      begin: Alignment(
        -1 * (rad < 3.14 ? 1 : -1) * (rad % 1.57 / 1.57),
        -1,
      ),
      end: Alignment(
        (rad < 3.14 ? 1 : -1) * (rad % 1.57 / 1.57),
        1,
      ),
      colors: [a, b, c],
      stops: const [0, 0.55, 1],
    );
  }

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
    final showStatus = alwaysShowStatus || !event.isApproved;
    final days = _daysUntil();

    return AppCard(
      onTap: onTap,
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
                          errorBuilder: (_, e, s) => _GradientThumb(gradient: _gradient()),
                        )
                      : _GradientThumb(gradient: _gradient()),
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
                        isFavorite ? Icons.favorite_rounded : Icons.favorite_border_rounded,
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
                      background: AppColors.primaryLight,
                      foreground: AppColors.primary,
                      label: event.category,
                    ),
                    if (showStatus) ...[
                      const SizedBox(width: AppSpacing.xs),
                      _Pill(
                        background: event.statusColor.withValues(alpha: 0.15),
                        foreground: event.statusColor,
                        label: event.statusLabel,
                      ),
                    ],
                    const Spacer(),
                    if (!showStatus && days != null)
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
    );
  }
}

class _GradientThumb extends StatelessWidget {
  const _GradientThumb({required this.gradient});
  final LinearGradient gradient;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(gradient: gradient),
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
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 3),
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
