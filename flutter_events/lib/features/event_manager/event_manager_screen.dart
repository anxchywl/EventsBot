import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/localization.dart';
import '../../models/event_model.dart';
import '../events/event_detail_screen.dart';

/// Event Manager analytics from the Flutter event endpoints.
class EventManagerScreen extends StatefulWidget {
  const EventManagerScreen({super.key});

  @override
  State<EventManagerScreen> createState() => _EventManagerScreenState();
}

class _EventManagerScreenState extends State<EventManagerScreen> {
  static const _pollInterval = Duration(seconds: 20);

  bool _loading = true;
  String? _error;
  List<EventModel> _approved = [];
  List<EventModel> _pending = [];
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(_pollInterval, (_) => _refreshSilently());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        fetchApprovedEvents(),
        fetchPendingEvents(),
      ]);
      if (!mounted) return;
      setState(() {
        _approved = results[0];
        _pending = results[1];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _refreshSilently() async {
    try {
      final results = await Future.wait([
        fetchApprovedEvents(),
        fetchPendingEvents(),
      ]);
      if (!mounted) return;
      setState(() {
        _approved = results[0];
        _pending = results[1];
        _error = null;
      });
    } catch (_) {}
  }

  // ── Derived analytics ──────────────────────────────────────────────────────

  /// Groups of events that collide on the same date + location (case-insensitive),
  /// across approved and pending. Each returned group has 2+ events.
  List<List<EventModel>> get _conflicts {
    final bySlot = <String, List<EventModel>>{};
    for (final e in [..._approved, ..._pending]) {
      final key = '${e.eventDate}|${e.location.trim().toLowerCase()}';
      bySlot.putIfAbsent(key, () => []).add(e);
    }
    return bySlot.values.where((g) => g.length > 1).toList();
  }

  Map<String, int> _countBy(String Function(EventModel) key) {
    final map = <String, int>{};
    for (final e in [..._approved, ..._pending]) {
      map.update(key(e), (v) => v + 1, ifAbsent: () => 1);
    }
    final sorted = map.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return {for (final e in sorted) e.key: e.value};
  }

  int get _totalVisible => _approved.length + _pending.length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppAppBar(title: AppLocalizations.get('analytics')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: AppLoader());
    if (_error != null) {
      return Center(
        child: Padding(
          padding: AppSpacing.screenPadding,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.df),
              AppSecondaryButton(
                text: AppLocalizations.get('retry'),
                onPressed: _load,
              ),
            ],
          ),
        ),
      );
    }

    final conflicts = _conflicts;
    final byClub = _countBy((e) => e.organizerName);
    final byCategory = _countBy((e) => e.category);
    final total = _totalVisible;

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: AppSpacing.screenPadding,
        children: [
          _OverviewPanel(
            approved: _approved.length,
            pending: _pending.length,
            conflicts: conflicts.length,
          ),
          const SizedBox(height: AppSpacing.lg),
          _DistributionPanel(
            title: AppLocalizations.get('categories'),
            subtitle: AppLocalizations.get('categoriesSub'),
            counts: byCategory,
            total: total,
          ),
          const SizedBox(height: AppSpacing.lg),
          _DistributionPanel(
            title: AppLocalizations.get('organizers'),
            subtitle: AppLocalizations.get('organizersSub'),
            counts: byClub,
            total: total,
          ),
          const SizedBox(height: AppSpacing.lg),
          Text(AppLocalizations.get('slotConflicts'), style: AppTextStyles.sectionHeader),
          const SizedBox(height: AppSpacing.xs),
          Text(
            AppLocalizations.get('slotConflictsSub'),
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: AppColors.grey),
          ),
          const SizedBox(height: AppSpacing.sm),
          if (conflicts.isEmpty)
            _EmptyInsight(
              icon: Icons.check_circle_outline_rounded,
              text: AppLocalizations.get('noConflicts'),
            )
          else
            for (final group in conflicts) _conflictCard(group),
        ],
      ),
    );
  }

  Widget _conflictCard(List<EventModel> group) {
    final theme = Theme.of(context);
    final first = group.first;
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.error.withValues(alpha: 0.08),
        borderRadius: AppSpacing.borderRadiusMd,
        border: Border.all(color: AppColors.error.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.warning_amber_rounded,
                size: AppSpacing.iconSm,
                color: AppColors.error,
              ),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  '${first.eventDate} · ${first.location}',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          for (final e in group)
            InkWell(
              onTap: () => _openDetail(e),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      margin: const EdgeInsets.only(right: AppSpacing.sm),
                      decoration: BoxDecoration(
                        color: e.statusColor,
                        shape: BoxShape.circle,
                      ),
                    ),
                    Expanded(
                      child: Text(
                        '${e.title} — ${e.organizerName}',
                        style: theme.textTheme.bodySmall,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(
                      e.eventTime,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: AppColors.grey,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _openDetail(EventModel event) async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => EventDetailScreen(event: event)),
    );
    await _load();
  }
}

class _OverviewPanel extends StatelessWidget {
  const _OverviewPanel({
    required this.approved,
    required this.pending,
    required this.conflicts,
  });

  final int approved;
  final int pending;
  final int conflicts;

  @override
  Widget build(BuildContext context) {
    final total = approved + pending;
    final approvedShare = total == 0 ? 0.0 : approved / total;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(AppLocalizations.get('summary'), style: AppTextStyles.sectionHeader),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              SizedBox(
                width: 92,
                height: 92,
                child: CustomPaint(
                  painter: _DonutPainter(
                    value: approvedShare,
                    color: AppColors.success,
                    background: AppColors.orange.withValues(alpha: 0.24),
                  ),
                  child: Center(
                    child: Text(
                      '$total',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Column(
                  children: [
                    _MetricRow(
                      label: AppLocalizations.get('approvedLabel'),
                      value: approved,
                      color: AppColors.success,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    _MetricRow(
                      label: AppLocalizations.get('pending'),
                      value: pending,
                      color: AppColors.orange,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    _MetricRow(
                      label: AppLocalizations.get('slotConflicts'),
                      value: conflicts,
                      color: conflicts == 0 ? AppColors.grey : AppColors.error,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MetricRow extends StatelessWidget {
  const _MetricRow({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final int value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 9,
          height: 9,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(child: Text(label, style: AppTextStyles.bodyMedium)),
        Text(
          '$value',
          style: AppTextStyles.bodyMedium.copyWith(fontWeight: FontWeight.w800),
        ),
      ],
    );
  }
}

class _DistributionPanel extends StatelessWidget {
  const _DistributionPanel({
    required this.title,
    required this.subtitle,
    required this.counts,
    required this.total,
  });

  final String title;
  final String subtitle;
  final Map<String, int> counts;
  final int total;

  @override
  Widget build(BuildContext context) {
    final entries = counts.entries.take(5).toList();
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: AppTextStyles.sectionHeader),
          const SizedBox(height: 2),
          Text(
            subtitle,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: AppColors.grey),
          ),
          const SizedBox(height: AppSpacing.md),
          if (entries.isEmpty)
            _EmptyInsight(
              icon: Icons.insights_outlined,
              text: AppLocalizations.get('noData'),
            )
          else
            for (final entry in entries) ...[
              _BarInsight(
                label: entry.key,
                value: entry.value,
                share: total == 0 ? 0 : entry.value / total,
              ),
              const SizedBox(height: AppSpacing.sm),
            ],
        ],
      ),
    );
  }
}

class _BarInsight extends StatelessWidget {
  const _BarInsight({
    required this.label,
    required this.value,
    required this.share,
  });

  final String label;
  final int value;
  final double share;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: AppTextStyles.bodyMedium.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Text('$value', style: AppTextStyles.bodyMedium),
          ],
        ),
        const SizedBox(height: 5),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(
            value: share.clamp(0, 1),
            minHeight: 8,
            color: AppColors.primary,
            backgroundColor: AppColors.primaryLight,
          ),
        ),
      ],
    );
  }
}

class _EmptyInsight extends StatelessWidget {
  const _EmptyInsight({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Row(
        children: [
          Icon(icon, color: AppColors.grey, size: AppSpacing.iconSm),
          const SizedBox(width: AppSpacing.sm),
          Text(
            text,
            style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
          ),
        ],
      ),
    );
  }
}

class _DonutPainter extends CustomPainter {
  const _DonutPainter({
    required this.value,
    required this.color,
    required this.background,
  });

  final double value;
  final Color color;
  final Color background;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = size.width * 0.12;
    final rect = Offset.zero & size;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..color = background;
    canvas.drawArc(rect.deflate(stroke / 2), 0, 6.28318, false, paint);
    paint.color = color;
    canvas.drawArc(
      rect.deflate(stroke / 2),
      -1.5708,
      6.28318 * value.clamp(0, 1),
      false,
      paint,
    );
  }

  @override
  bool shouldRepaint(_DonutPainter oldDelegate) {
    return oldDelegate.value != value ||
        oldDelegate.color != color ||
        oldDelegate.background != background;
  }
}
