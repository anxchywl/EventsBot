import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/localization.dart';
import '../../core/realtime_updates.dart';
import '../../models/analytics_model.dart';
import 'analytics_event_picker.dart';
import 'analytics_period.dart';

/// Coordinator analytics dashboard.
///
/// Every number is computed by the backend (`/api/flutter/analytics/*`); this
/// screen only renders what it is given. Each panel loads, fails and retries
/// independently via [_AnalyticsPanel], so one bad query never blanks the whole
/// dashboard. Polling + realtime events bump [_refreshTick], which each panel
/// watches to silently reload.
class EventManagerScreen extends StatefulWidget {
  const EventManagerScreen({super.key});

  @override
  State<EventManagerScreen> createState() => _EventManagerScreenState();
}

class _EventManagerScreenState extends State<EventManagerScreen> {
  static const _pollInterval = Duration(seconds: 30);

  // Active filters. The period governs the "all events" view; a pinned event is
  // the stronger selector and shows that event's full history (the period is
  // remembered and reapplied when the event filter is cleared).
  AnalyticsPeriod _period = AnalyticsPeriod.defaultPeriod;
  AnalyticsEventOption? _selectedEvent;

  int _refreshTick = 0;
  Timer? _pollTimer;
  StreamSubscription<RealtimeUpdate>? _updatesSub;

  bool get _eventPinned => _selectedEvent != null;

  // Filters compose (AND) server-side. A pinned event drops the date bounds so
  // an event created outside the current period still shows its analytics
  // instead of an empty — but never mixed — dataset.
  AnalyticsFilters get _filters => _eventPinned
      ? AnalyticsFilters(eventId: _selectedEvent!.id)
      : AnalyticsFilters(dateFrom: _period.dateFrom, dateTo: _period.dateTo);

  int get _trendDays => _period.trendDays;

  @override
  void initState() {
    super.initState();
    _pollTimer = Timer.periodic(_pollInterval, (_) => _bumpTick());
    _updatesSub = RealtimeUpdates.instance.stream.listen(_handleRealtimeUpdate);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _updatesSub?.cancel();
    super.dispose();
  }

  void _handleRealtimeUpdate(RealtimeUpdate update) {
    if (update.type == 'event_status_changed') _bumpTick();
  }

  void _bumpTick() {
    if (!mounted) return;
    setState(() => _refreshTick++);
  }

  Future<void> _onPickPeriod(PeriodType type) async {
    if (type == PeriodType.custom) {
      final now = DateTime.now();
      final range = await showDateRangePicker(
        context: context,
        firstDate: DateTime(now.year - 5),
        lastDate: DateTime(now.year, now.month, now.day),
        initialDateRange: _period.type == PeriodType.custom &&
                _period.customStart != null &&
                _period.customEnd != null
            ? DateTimeRange(
                start: _period.customStart!, end: _period.customEnd!)
            : null,
      );
      if (range == null || !mounted) return;
      setState(() => _period = AnalyticsPeriod(
            PeriodType.custom,
            customStart: range.start,
            customEnd: range.end,
          ));
      return;
    }
    setState(() => _period = AnalyticsPeriod(type));
  }

  Future<void> _onPickEvent() async {
    final result = await pickAnalyticsEvent(
      context,
      selectedId: _selectedEvent?.id,
    );
    if (result == null || !mounted) return; // dismissed: keep current filter
    setState(() => _selectedEvent = result.event);
  }

  void _clearEvent() => setState(() => _selectedEvent = null);

  @override
  Widget build(BuildContext context) {
    // reloadKey combines the active filters and the refresh tick; when either
    // changes every panel reloads against the same filtered dataset. Scroll
    // position is preserved because the ListView itself is never rebuilt.
    final reloadKey = '${_filters.hashCode}:$_refreshTick';
    return Scaffold(
      appBar: AppAppBar(title: AppLocalizations.get('analytics')),
      body: RefreshIndicator(
        onRefresh: () async => _bumpTick(),
        child: ListView(
          padding: AppSpacing.screenPadding,
          children: [
            _FilterBar(
              period: _period,
              selectedEvent: _selectedEvent,
              onPickPeriod: _onPickPeriod,
              onPickEvent: _onPickEvent,
              onClearEvent: _clearEvent,
            ),
            const SizedBox(height: AppSpacing.lg),
            _AnalyticsPanel<AnalyticsSummary>(
              title: AppLocalizations.get('overview'),
              reloadKey: reloadKey,
              loader: () => fetchAnalyticsSummary(_filters),
              builder: (s) => _SummaryBody(summary: s),
              skeletonLines: 4,
            ),
            const SizedBox(height: AppSpacing.lg),
            _AnalyticsPanel<AnalyticsModeration>(
              title: AppLocalizations.get('moderationHealth'),
              reloadKey: reloadKey,
              loader: () => fetchAnalyticsModeration(_filters),
              builder: (m) => _ModerationBody(data: m),
              skeletonLines: 5,
            ),
            const SizedBox(height: AppSpacing.lg),
            _AnalyticsPanel<AnalyticsEngagement>(
              title: AppLocalizations.get('engagement'),
              reloadKey: reloadKey,
              loader: () => fetchAnalyticsEngagement(_filters, trendDays: _trendDays),
              builder: (e) => _EngagementBody(data: e),
              skeletonLines: 4,
            ),
            // cross-event ranking is meaningless for a single pinned event
            if (!_eventPinned) ...[
              const SizedBox(height: AppSpacing.lg),
              _AnalyticsPanel<List<RankedEvent>>(
                title: AppLocalizations.get('mostViewed'),
                reloadKey: reloadKey,
                loader: () =>
                    fetchAnalyticsTop(_filters, metric: 'views', limit: 5),
                builder: (rows) => _RankedList(rows: rows, suffixKey: 'views'),
                skeletonLines: 3,
              ),
            ],
            const SizedBox(height: AppSpacing.lg),
            _AnalyticsPanel<AnalyticsRatings>(
              title: AppLocalizations.get('ratings'),
              reloadKey: reloadKey,
              loader: () => fetchAnalyticsRatings(_filters),
              builder: (r) => _RatingsBody(data: r, showRankings: !_eventPinned),
              skeletonLines: 5,
            ),
            const SizedBox(height: AppSpacing.xl),
          ],
        ),
      ),
    );
  }
}

// ── Filter bar: period selector + event picker ───────────────────────────────

class _FilterBar extends StatelessWidget {
  const _FilterBar({
    required this.period,
    required this.selectedEvent,
    required this.onPickPeriod,
    required this.onPickEvent,
    required this.onClearEvent,
  });

  final AnalyticsPeriod period;
  final AnalyticsEventOption? selectedEvent;
  final ValueChanged<PeriodType> onPickPeriod;
  final VoidCallback onPickEvent;
  final VoidCallback onClearEvent;

  static const _periodOrder = [
    PeriodType.last7,
    PeriodType.last30,
    PeriodType.last90,
    PeriodType.thisMonth,
    PeriodType.thisYear,
    PeriodType.allTime,
    PeriodType.custom,
  ];

  String _periodLabel(PeriodType type) => AnalyticsPeriod(type).label;

  @override
  Widget build(BuildContext context) {
    final eventPinned = selectedEvent != null;
    return Row(
      children: [
        // Period selector — a native Material popup (fade + scale) anchored to
        // the pill, dismissed by selecting or tapping outside. While an event is
        // pinned the period is inactive (event shows full history) but preserved.
        Expanded(
          child: PopupMenuButton<PeriodType>(
            enabled: !eventPinned,
            position: PopupMenuPosition.under,
            shape: RoundedRectangleBorder(
              borderRadius: AppSpacing.borderRadiusMd,
            ),
            onSelected: onPickPeriod,
            itemBuilder: (context) => [
              for (final type in _periodOrder)
                PopupMenuItem<PeriodType>(
                  value: type,
                  child: Row(
                    children: [
                      Expanded(child: Text(_periodLabel(type))),
                      if (!eventPinned && type == period.type)
                        const Icon(Icons.check,
                            size: 18, color: AppColors.primary),
                    ],
                  ),
                ),
            ],
            child: _FilterPill(
              icon: Icons.calendar_today_outlined,
              label: eventPinned
                  ? AppLocalizations.get('period')
                  : period.label,
              muted: eventPinned,
              trailing: const Icon(Icons.expand_more,
                  size: 18, color: AppColors.grey),
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        // Event picker — opens the searchable sheet; when an event is pinned the
        // pill shows its title with an inline clear action.
        Expanded(
          child: eventPinned
              ? _FilterPill(
                  icon: Icons.event_note_outlined,
                  label: selectedEvent!.title,
                  highlighted: true,
                  onTap: onPickEvent,
                  trailing: GestureDetector(
                    onTap: onClearEvent,
                    behavior: HitTestBehavior.opaque,
                    child: const Icon(Icons.close,
                        size: 18, color: AppColors.primary),
                  ),
                )
              : _FilterPill(
                  icon: Icons.event_note_outlined,
                  label: AppLocalizations.get('allEvents'),
                  onTap: onPickEvent,
                  trailing: const Icon(Icons.expand_more,
                      size: 18, color: AppColors.grey),
                ),
        ),
      ],
    );
  }
}

class _FilterPill extends StatelessWidget {
  const _FilterPill({
    required this.icon,
    required this.label,
    this.trailing,
    this.onTap,
    this.highlighted = false,
    this.muted = false,
  });

  final IconData icon;
  final String label;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool highlighted;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    final fg = muted
        ? AppColors.grey
        : (highlighted ? AppColors.primary : AppColors.textPrimary);
    return Material(
      color: highlighted ? AppColors.primaryLight : Colors.white,
      borderRadius: AppSpacing.borderRadiusMd,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppSpacing.borderRadiusMd,
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm + 2,
          ),
          child: Row(
            children: [
              Icon(icon, size: 16, color: fg),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTextStyles.bodyMedium.copyWith(
                    color: fg,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (trailing != null) ...[
                const SizedBox(width: 4),
                trailing!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// ── Generic independently-failable panel ─────────────────────────────────────

class _AnalyticsPanel<T> extends StatefulWidget {
  const _AnalyticsPanel({
    required this.title,
    required this.reloadKey,
    required this.loader,
    required this.builder,
    this.skeletonLines = 3,
    super.key,
  });

  final String title;
  final String reloadKey;
  final Future<T> Function() loader;
  final Widget Function(T data) builder;
  final int skeletonLines;

  @override
  State<_AnalyticsPanel<T>> createState() => _AnalyticsPanelState<T>();
}

class _AnalyticsPanelState<T> extends State<_AnalyticsPanel<T>> {
  T? _data;
  Object? _error;
  bool _loading = false;
  int _requestId = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant _AnalyticsPanel<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.reloadKey != widget.reloadKey) {
      _load(); // silent: keep stale data visible while refreshing
    }
  }

  Future<void> _load() async {
    final requestId = ++_requestId;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.loader();
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _data = result;
        _loading = false;
      });
    } catch (e) {
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      title: widget.title,
      trailing: _loading && _data != null
          ? const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : null,
      child: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_data != null) return widget.builder(_data as T);
    if (_loading) return _PanelSkeleton(lines: widget.skeletonLines);
    if (_error != null) return _PanelError(onRetry: _load);
    return _EmptyInsight(
      icon: Icons.insights_outlined,
      text: AppLocalizations.get('nothingYet'),
    );
  }
}

// ── Shared chrome: card, skeleton, error, empty ──────────────────────────────

class _PanelCard extends StatelessWidget {
  const _PanelCard({required this.title, required this.child, this.trailing});

  final String title;
  final Widget child;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(title, style: AppTextStyles.sectionHeader),
              ),
              ?trailing,
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          child,
        ],
      ),
    );
  }
}

class _PanelSkeleton extends StatefulWidget {
  const _PanelSkeleton({required this.lines});

  final int lines;

  @override
  State<_PanelSkeleton> createState() => _PanelSkeletonState();
}

class _PanelSkeletonState extends State<_PanelSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(begin: 0.45, end: 0.9).animate(_controller),
      child: Column(
        children: [
          for (var i = 0; i < widget.lines; i++) ...[
            Row(
              children: [
                Expanded(
                  flex: 3,
                  child: _bar(height: 12),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(child: _bar(height: 12)),
              ],
            ),
            if (i != widget.lines - 1)
              const SizedBox(height: AppSpacing.md),
          ],
        ],
      ),
    );
  }

  Widget _bar({required double height}) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: AppColors.lightGrey,
        borderRadius: BorderRadius.circular(999),
      ),
    );
  }
}

class _PanelError extends StatelessWidget {
  const _PanelError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.errorLight,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline,
              color: AppColors.error, size: AppSpacing.iconSm),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              AppLocalizations.get('failedToLoad'),
              style: AppTextStyles.bodyMedium.copyWith(color: AppColors.error),
            ),
          ),
          AppTextButton(
            text: AppLocalizations.get('retry'),
            onPressed: onRetry,
          ),
        ],
      ),
    );
  }
}

// ── Panel bodies ─────────────────────────────────────────────────────────────

class _SummaryBody extends StatelessWidget {
  const _SummaryBody({required this.summary});

  final AnalyticsSummary summary;

  int _int(String key) => (summary[key] ?? 0).toInt();

  @override
  Widget build(BuildContext context) {
    final total = _int('total_events');
    final approved = _int('approved');
    final approvedShare = total == 0 ? 0.0 : approved / total;
    final avgRating = summary['average_event_rating'];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
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
                    label: AppLocalizations.get('pendingReview'),
                    value: _int('pending_review'),
                    color: AppColors.orange,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  _MetricRow(
                    label: AppLocalizations.get('rejected'),
                    value: _int('rejected'),
                    color: AppColors.error,
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.lg),
        _StatGrid(
          stats: [
            _Stat(AppLocalizations.get('publishedThisWeek'),
                '${_int('published_this_week')}'),
            _Stat(AppLocalizations.get('upcomingEvents'),
                '${_int('upcoming_events')}'),
            _Stat(AppLocalizations.get('eventViews'),
                _compact(_int('total_event_views'))),
            _Stat(AppLocalizations.get('registrationClicks'),
                '${_int('total_registration_clicks')}'),
            _Stat(AppLocalizations.get('totalFavorites'),
                '${_int('total_favorites')}'),
            _Stat(
              AppLocalizations.get('avgRating'),
              avgRating == null ? '—' : avgRating.toStringAsFixed(1),
            ),
          ],
        ),
      ],
    );
  }
}

class _ModerationBody extends StatelessWidget {
  const _ModerationBody({required this.data});

  final AnalyticsModeration data;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _RateRow(
          label: AppLocalizations.get('approvalRate'),
          rate: data.approvalRate,
          color: AppColors.success,
        ),
        const SizedBox(height: AppSpacing.sm),
        _RateRow(
          label: AppLocalizations.get('rejectionRate'),
          rate: data.rejectionRate,
          color: AppColors.error,
        ),
        const SizedBox(height: AppSpacing.sm),
        _RateRow(
          label: AppLocalizations.get('needsChangesRate'),
          rate: data.needsChangesRate,
          color: AppColors.orange,
        ),
        const SizedBox(height: AppSpacing.lg),
        _StatGrid(
          stats: [
            _Stat(
              AppLocalizations.get('queueSize'),
              '${data.queueSize}',
            ),
            _Stat(
              AppLocalizations.get('avgIterations'),
              data.avgReviewIterations?.toStringAsFixed(1) ?? '—',
              tooltip: AppLocalizations.get('avgIterationsTip'),
            ),
            _Stat(
              AppLocalizations.get('timeToFirstDecision'),
              _humanDuration(data.avgTimeToFirstDecisionSeconds),
              tooltip: AppLocalizations.get('timeToFirstDecisionTip'),
            ),
            _Stat(
              AppLocalizations.get('avgReviewTime'),
              _humanDuration(data.avgTotalReviewSeconds),
              tooltip: AppLocalizations.get('avgReviewTimeTip'),
            ),
          ],
        ),
        if (data.longestPending != null) ...[
          const SizedBox(height: AppSpacing.md),
          _InlineFact(
            icon: Icons.hourglass_bottom,
            label: AppLocalizations.get('longestPending'),
            value:
                '${data.longestPending!.title} · ${_humanDuration(data.longestPending!.waitingSeconds)}',
          ),
        ],
        for (final bucket in data.thresholdBuckets)
          if (bucket.count > 0) ...[
            const SizedBox(height: AppSpacing.sm),
            _InlineFact(
              icon: Icons.warning_amber_rounded,
              color: AppColors.warning,
              label:
                  '${AppLocalizations.get('waitingOver')} ${bucket.thresholdHours}h',
              value: '${bucket.count}',
            ),
          ],
      ],
    );
  }
}

class _EngagementBody extends StatelessWidget {
  const _EngagementBody({required this.data});

  final AnalyticsEngagement data;

  @override
  Widget build(BuildContext context) {
    final t = data.totals;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatGrid(
          stats: [
            _Stat(AppLocalizations.get('eventViews'), _compact(t.views)),
            _Stat(AppLocalizations.get('registrationClicks'),
                '${t.registerClicks}'),
            _Stat(AppLocalizations.get('shares'), '${t.shareClicks}'),
            _Stat(AppLocalizations.get('reminders'), '${t.reminderCreates}'),
            _Stat(AppLocalizations.get('totalFavorites'), '${t.favoritesAdded}'),
          ],
        ),
        const SizedBox(height: AppSpacing.lg),
        Text(
          AppLocalizations.get('viewsOverTime'),
          style: AppTextStyles.bodyMedium.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: AppSpacing.sm),
        SizedBox(
          height: 56,
          child: _Sparkline(points: data.viewsOverTime),
        ),
      ],
    );
  }
}

class _RatingsBody extends StatelessWidget {
  const _RatingsBody({required this.data, this.showRankings = true});

  final AnalyticsRatings data;
  final bool showRankings;

  @override
  Widget build(BuildContext context) {
    if (data.totalReviews == 0) {
      return _EmptyInsight(
        icon: Icons.star_border,
        text: AppLocalizations.get('nothingYet'),
      );
    }
    final total = data.totalReviews;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Text(
              data.average?.toStringAsFixed(1) ?? '—',
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(width: AppSpacing.sm),
            const Icon(Icons.star, color: AppColors.warning, size: 20),
            const Spacer(),
            Text(
              '$total ${AppLocalizations.get('reviews')}',
              style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        for (var star = 5; star >= 1; star--) ...[
          _BarInsight(
            label: '★ $star',
            value: data.distribution['$star'] ?? 0,
            share: total == 0 ? 0 : (data.distribution['$star'] ?? 0) / total,
          ),
          const SizedBox(height: AppSpacing.sm),
        ],
        if (showRankings && data.eventsWithZeroReviews > 0) ...[
          const SizedBox(height: AppSpacing.xs),
          _InlineFact(
            icon: Icons.reviews_outlined,
            label: AppLocalizations.get('zeroReviews'),
            value: '${data.eventsWithZeroReviews}',
          ),
        ],
        // top/lowest rankings are cross-event and hidden for a pinned event
        if (showRankings) ...[
          const SizedBox(height: AppSpacing.md),
          Text(
            AppLocalizations.get('topRated'),
            style:
                AppTextStyles.bodyMedium.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: AppSpacing.sm),
          _RankedList(rows: data.topRated, ratingStyle: true),
          if (data.lowestRated.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              AppLocalizations.get('lowestRated'),
              style: AppTextStyles.bodyMedium
                  .copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: AppSpacing.sm),
            _RankedList(rows: data.lowestRated, ratingStyle: true),
          ],
        ],
      ],
    );
  }
}

// ── Leaf widgets (reused across panels) ──────────────────────────────────────

class _RankedList extends StatelessWidget {
  const _RankedList({
    required this.rows,
    this.suffixKey,
    this.ratingStyle = false,
  });

  final List<RankedEvent> rows;
  final String? suffixKey;
  final bool ratingStyle;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return _EmptyInsight(
        icon: Icons.insights_outlined,
        text: AppLocalizations.get('nothingYet'),
      );
    }
    return Column(
      children: [
        for (var i = 0; i < rows.length; i++) ...[
          Row(
            children: [
              SizedBox(
                width: 20,
                child: Text(
                  '${i + 1}',
                  style: AppTextStyles.bodyMedium.copyWith(
                    color: AppColors.grey,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  rows[i].title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTextStyles.bodyMedium
                      .copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                ratingStyle
                    ? '★ ${rows[i].value.toStringAsFixed(1)}'
                    : _compact(rows[i].value.toInt()),
                style: AppTextStyles.bodyMedium.copyWith(
                  fontWeight: FontWeight.w800,
                  color: ratingStyle ? AppColors.warning : AppColors.primary,
                ),
              ),
            ],
          ),
          if (i != rows.length - 1) const SizedBox(height: AppSpacing.sm),
        ],
      ],
    );
  }
}

class _RateRow extends StatelessWidget {
  const _RateRow({required this.label, required this.rate, required this.color});

  final String label;
  final double rate;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: AppTextStyles.bodyMedium
                    .copyWith(fontWeight: FontWeight.w600),
              ),
            ),
            Text(
              '${(rate * 100).toStringAsFixed(0)}%',
              style:
                  AppTextStyles.bodyMedium.copyWith(fontWeight: FontWeight.w800),
            ),
          ],
        ),
        const SizedBox(height: 5),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(
            value: rate.clamp(0, 1),
            minHeight: 8,
            color: color,
            backgroundColor: AppColors.fieldBackground,
          ),
        ),
      ],
    );
  }
}

class _Stat {
  const _Stat(this.label, this.value, {this.tooltip});
  final String label;
  final String value;
  final String? tooltip;
}

class _StatGrid extends StatelessWidget {
  const _StatGrid({required this.stats});

  final List<_Stat> stats;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // mobile-first: 2 columns on phones, 3 on wider layouts
        final columns = constraints.maxWidth >= 520 ? 3 : 2;
        const spacing = AppSpacing.sm;
        final itemWidth =
            (constraints.maxWidth - spacing * (columns - 1)) / columns;
        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: [
            for (final stat in stats)
              SizedBox(width: itemWidth, child: _StatTile(stat: stat)),
          ],
        );
      },
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({required this.stat});

  final _Stat stat;

  @override
  Widget build(BuildContext context) {
    final content = Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _AnimatedValue(
            value: stat.value,
            style: AppTextStyles.bodyLarge.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 2),
          Row(
            children: [
              Flexible(
                child: Text(
                  stat.label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
                ),
              ),
              if (stat.tooltip != null) ...[
                const SizedBox(width: 3),
                const Icon(Icons.info_outline,
                    size: 12, color: AppColors.grey),
              ],
            ],
          ),
        ],
      ),
    );
    if (stat.tooltip == null) return content;
    return Tooltip(
      message: stat.tooltip!,
      triggerMode: TooltipTriggerMode.tap,
      child: content,
    );
  }
}

/// Fades between values when a metric changes (e.g. on filter switch), so
/// numbers update smoothly instead of snapping.
class _AnimatedValue extends StatelessWidget {
  const _AnimatedValue({required this.value, required this.style});

  final String value;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 260),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: SizeTransition(
          axis: Axis.vertical,
          sizeFactor: animation,
          child: child,
        ),
      ),
      child: Text(
        value,
        key: ValueKey(value),
        style: style,
      ),
    );
  }
}

class _InlineFact extends StatelessWidget {
  const _InlineFact({
    required this.icon,
    required this.label,
    required this.value,
    this.color,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: AppSpacing.iconSm, color: color ?? AppColors.grey),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            label,
            style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
          ),
        ),
        Text(
          value,
          style: AppTextStyles.bodyMedium.copyWith(
            fontWeight: FontWeight.w800,
            color: color ?? AppColors.textPrimary,
          ),
        ),
      ],
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

/// Minimal sparkline for the views-over-time series. Renders a clean zero
/// baseline when every point is 0 (no data yet) rather than an empty box.
class _Sparkline extends StatelessWidget {
  const _Sparkline({required this.points});

  final List<TrendPoint> points;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.infinite,
      painter: _SparklinePainter(points),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  _SparklinePainter(this.points);

  final List<TrendPoint> points;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final maxValue =
        points.map((p) => p.count).fold<int>(0, (a, b) => a > b ? a : b);
    final dx = size.width / (points.length - 1);
    final baseline = size.height - 1;

    final linePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..color = AppColors.primary;

    double yFor(int value) {
      if (maxValue == 0) return baseline;
      return baseline - (value / maxValue) * (size.height - 2);
    }

    final path = Path();
    for (var i = 0; i < points.length; i++) {
      final x = dx * i;
      final y = yFor(points[i].count);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(path, linePaint);
  }

  @override
  bool shouldRepaint(_SparklinePainter oldDelegate) =>
      oldDelegate.points != points;
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

// ── Formatting helpers ───────────────────────────────────────────────────────

String _compact(int value) {
  if (value >= 1000000) return '${(value / 1000000).toStringAsFixed(1)}M';
  if (value >= 1000) return '${(value / 1000).toStringAsFixed(1)}k';
  return '$value';
}

String _humanDuration(double? seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return '${seconds.round()}s';
  final minutes = seconds / 60;
  if (minutes < 60) return '${minutes.round()}m';
  final hours = minutes / 60;
  if (hours < 24) return '${hours.toStringAsFixed(hours < 10 ? 1 : 0)}h';
  final days = hours / 24;
  return '${days.toStringAsFixed(days < 10 ? 1 : 0)}d';
}
