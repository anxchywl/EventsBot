import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../models/event_model.dart';
import '../events/event_detail_screen.dart';

/// Event Manager analytics & administration.
///
/// What is REAL (computed client-side from existing endpoints):
///   • Approved event count            ← GET /api/flutter/events
///   • Pending backlog count           ← GET /api/flutter/events/pending
///   • Conflicting requests (same date + location) across approved + pending
///   • Breakdown by club (organizer) and by category
///
/// What is STUBBED (no backend support under /api/flutter yet):
///   • First-pass approval rate — needs rejected/needs_changes totals, which no
///     endpoint exposes (only APPROVED and PENDING are enumerable).
///   • Avg submit→decision time — the event schema carries no created/decided
///     timestamps.
///   • Club role assignment (president / VP / club event manager) — needs the
///     /clubs and /admin endpoints, which are not exposed to Flutter.
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AppAppBar(title: 'Аналитика'),
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
              AppSecondaryButton(text: 'Повторить', onPressed: _load),
            ],
          ),
        ),
      );
    }

    final conflicts = _conflicts;
    final byClub = _countBy((e) => e.organizerName);
    final byCategory = _countBy((e) => e.category);

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: AppSpacing.screenPadding,
        children: [
          // ── Top stats ──────────────────────────────────────────────────
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: 'Одобрено',
                  value: '${_approved.length}',
                  color: AppColors.success,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _StatCard(
                  label: 'На рассмотрении',
                  value: '${_pending.length}',
                  color: AppColors.orange,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _StatCard(
                  label: 'Конфликты',
                  value: '${conflicts.length}',
                  color: conflicts.isEmpty ? AppColors.grey : AppColors.error,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),

          // ── Conflicts ──────────────────────────────────────────────────
          Text('Конфликтующие заявки', style: AppTextStyles.sectionHeader),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Совпадение по дате и месту (одобренные + на рассмотрении)',
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: AppColors.grey),
          ),
          const SizedBox(height: AppSpacing.sm),
          if (conflicts.isEmpty)
            Text(
              'Конфликтов нет',
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: AppColors.grey),
            )
          else
            for (final group in conflicts) _conflictCard(group),
          const SizedBox(height: AppSpacing.lg),

          // ── Breakdown by club ──────────────────────────────────────────
          Text('По клубам', style: AppTextStyles.sectionHeader),
          const SizedBox(height: AppSpacing.sm),
          _breakdown(byClub),
          const SizedBox(height: AppSpacing.lg),

          // ── Breakdown by category ──────────────────────────────────────
          Text('По категориям', style: AppTextStyles.sectionHeader),
          const SizedBox(height: AppSpacing.sm),
          _breakdown(byCategory),
          const SizedBox(height: AppSpacing.lg),

          // ── Requires backend ───────────────────────────────────────────
          _backendGapSection(),
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

  Widget _breakdown(Map<String, int> counts) {
    if (counts.isEmpty) {
      return Text(
        'Нет данных',
        style: Theme.of(
          context,
        ).textTheme.bodyMedium?.copyWith(color: AppColors.grey),
      );
    }
    final maxValue = counts.values.reduce((a, b) => a > b ? a : b);
    final theme = Theme.of(context);
    return Column(
      children: [
        for (final entry in counts.entries)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        entry.key,
                        style: theme.textTheme.bodyMedium,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(
                      '${entry.value}',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: maxValue == 0 ? 0 : entry.value / maxValue,
                    minHeight: 6,
                    color: AppColors.primary,
                    backgroundColor: AppColors.fieldBackground,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _backendGapSection() {
    final theme = Theme.of(context);
    Widget row(String title, String reason) => Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.lock_outline,
                size: AppSpacing.iconSm,
                color: AppColors.grey,
              ),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  title,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(left: 24, top: 2),
            child: Text(
              reason,
              style: theme.textTheme.bodySmall?.copyWith(color: AppColors.grey),
            ),
          ),
        ],
      ),
    );

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Требует доработки бэкенда', style: AppTextStyles.sectionHeader),
          const SizedBox(height: AppSpacing.sm),
          row(
            'Доля одобрения с первого раза',
            'Нужны данные об отклонённых заявках — сейчас API отдаёт только одобренные и ожидающие.',
          ),
          row(
            'Среднее время до решения',
            'В схеме события нет отметок времени подачи и решения.',
          ),
          row(
            'Назначение ролей в клубе',
            'Нужны эндпоинты /clubs и /admin, недоступные из Flutter.',
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

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            value,
            style: theme.textTheme.headlineSmall?.copyWith(
              color: color,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(color: AppColors.grey),
            maxLines: 2,
          ),
        ],
      ),
    );
  }
}
