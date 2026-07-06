import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/cache_store.dart';
import '../../core/localization.dart';
import '../../core/realtime_updates.dart';
import '../../models/analytics_model.dart';
import '../../models/category_model.dart';
import 'analytics_event_picker.dart';
import 'analytics_period.dart';
import 'analytics_period_picker.dart';
import 'analytics_ranking_sheet.dart';

/// Coordinator analytics dashboard.
///
/// Every number is computed by the backend (`/api/flutter/analytics/*`); this
/// screen only renders what it is given. Each panel loads, fails and retries
/// independently via [_AnalyticsPanel], so one bad query never blanks the whole
/// dashboard. Polling + realtime events bump [_refreshSignal], which each panel
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
  int? _categoryId;
  String? _categoryName;
  String? _organizer;

  final ValueNotifier<int> _refreshSignal = ValueNotifier(0);
  final _nestedKey = GlobalKey<NestedScrollViewState>();
  ScrollController get _scrollController =>
      _nestedKey.currentState?.innerController ?? ScrollController();
  Timer? _pollTimer;
  Timer? _deferredRefreshTimer;
  StreamSubscription<RealtimeUpdate>? _updatesSub;
  bool _isScrolling = false;
  bool _refreshAfterScroll = false;

  bool get _eventPinned => _selectedEvent != null;

  // Filters compose (AND) server-side. A pinned event drops the other dimensions
  // (it is the strongest selector and shows that event's full history) so an
  // event created outside the current period still shows its analytics instead
  // of an empty — but never mixed — dataset.
  AnalyticsFilters get _filters => _eventPinned
      ? AnalyticsFilters(eventId: _selectedEvent!.id)
      : AnalyticsFilters(
          dateFrom: _period.dateFrom,
          dateTo: _period.dateTo,
          categoryId: _categoryId,
          organizer: _organizer,
        );

  int get _trendDays => _period.trendDays;

  String _reloadKeyFor(AnalyticsFilters filters) {
    return [
      filters.dateFrom ?? '',
      filters.dateTo ?? '',
      filters.categoryId?.toString() ?? '',
      filters.organizer ?? '',
      filters.status ?? '',
      filters.eventId?.toString() ?? '',
    ].join('|');
  }

  @override
  void initState() {
    super.initState();
    _pollTimer = Timer.periodic(_pollInterval, (_) => _bumpTick());
    _updatesSub = RealtimeUpdates.instance.stream.listen(_handleRealtimeUpdate);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _deferredRefreshTimer?.cancel();
    _updatesSub?.cancel();
    _refreshSignal.dispose();
    super.dispose();
  }

  void _handleRealtimeUpdate(RealtimeUpdate update) {
    if (update.type == 'event_status_changed') {
      // Any status change moves the moderation / engagement / ratings figures,
      // so drop the cached panels before re-running their loaders.
      AnalyticsCache.instance.clear();
      _bumpTick();
    }
  }

  void _bumpTick({bool force = false}) {
    if (!mounted) return;
    if (_isScrolling && !force) {
      _refreshAfterScroll = true;
      _deferredRefreshTimer?.cancel();
      return;
    }
    _deferredRefreshTimer?.cancel();
    _refreshAfterScroll = false;
    _refreshSignal.value++;
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    if (notification is ScrollStartNotification) {
      _isScrolling = true;
      _deferredRefreshTimer?.cancel();
    } else if (notification is ScrollEndNotification) {
      _isScrolling = false;
      if (_refreshAfterScroll) {
        _deferredRefreshTimer?.cancel();
        _deferredRefreshTimer = Timer(
          const Duration(seconds: 2),
          () => _bumpTick(force: true),
        );
      }
    }
    return false;
  }

  Future<void> _onPickPeriod() async {
    final result = await pickAnalyticsPeriod(context, current: _period);
    if (result == null || !mounted) return;
    setState(() => _period = result);
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

  Future<void> _onPickCategory() async {
    List<CategoryModel> cats;
    try {
      cats = await EventCache.instance.categories();
    } catch (_) {
      _showLoadError();
      return;
    }
    if (!mounted) return;
    final choice = await showCappedSelection<int>(
      context: context,
      title: AppLocalizations.get('category'),
      selectedValue: _categoryId ?? 0,
      options: [
        SelectionOption(title: AppLocalizations.get('allCategories'), value: 0),
        for (final c in cats) SelectionOption(title: c.name, value: c.id),
      ],
    );
    if (choice == null || !mounted) return; // dismissed: keep current
    setState(() {
      if (choice == 0) {
        _categoryId = null;
        _categoryName = null;
      } else {
        _categoryId = choice;
        _categoryName = cats.firstWhere((c) => c.id == choice).name;
      }
    });
  }

  Future<void> _onPickOrganizer() async {
    List<AnalyticsOrganizer> orgs;
    try {
      // reuse the ranked organizers list (bounded) as the picker source
      orgs = await fetchAnalyticsOrganizers(
        AnalyticsFilters(dateFrom: _period.dateFrom, dateTo: _period.dateTo),
        limit: 50,
      );
    } catch (_) {
      _showLoadError();
      return;
    }
    if (!mounted) return;
    final choice = await showCappedSelection<String>(
      context: context,
      title: AppLocalizations.get('organizer'),
      selectedValue: _organizer ?? '',
      options: [
        SelectionOption(
          title: AppLocalizations.get('allOrganizers'),
          value: '',
        ),
        for (final o in orgs)
          SelectionOption(
            title: o.organizer,
            value: o.organizer,
            subtitle:
                '${o.eventsCreated} ${_pluralize(o.eventsCreated, AppLocalizations.get('event').toLowerCase(), AppLocalizations.get('events').toLowerCase())} · ${o.views} ${AppLocalizations.get('eventViews').toLowerCase()}',
          ),
      ],
    );
    if (choice == null || !mounted) return;
    setState(() => _organizer = choice.isEmpty ? null : choice);
  }

  void _showLoadError() {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(AppLocalizations.get('failedToLoad'))),
    );
  }

  @override
  Widget build(BuildContext context) {
    final filters = _filters;
    final reloadKey = _reloadKeyFor(filters);
    return Scaffold(
      body: NestedScrollView(
        key: _nestedKey,
        headerSliverBuilder: (ctx, _) => [
          AppSliverAppBar(title: AppLocalizations.get('analytics')),
        ],
        body: RefreshIndicator(
          onRefresh: () async => _bumpTick(force: true),
          child: NotificationListener<ScrollNotification>(
            onNotification: _handleScrollNotification,
            child: CustomScrollView(
              slivers: [
                SliverPadding(
                  padding: AppSpacing.screenPadding,
                  sliver: SliverList(
                    delegate: SliverChildListDelegate([
              _FilterBar(
                period: _period,
                selectedEvent: _selectedEvent,
                categoryName: _categoryName,
                organizer: _organizer,
                onPickPeriod: _onPickPeriod,
                onPickEvent: _onPickEvent,
                onClearEvent: _clearEvent,
                onPickCategory: _onPickCategory,
                onPickOrganizer: _onPickOrganizer,
              ),

              // Summary is portfolio-level (donut, weekly counts, totals). When a
              // single event is pinned the engagement + ratings panels already
              // cover all relevant data, so hide this panel to reduce noise.
              if (!_eventPinned) ...[
                const SizedBox(height: AppSpacing.lg),
                _AnalyticsPanel<AnalyticsSummary>(
                  title: AppLocalizations.get('overview'),
                  reloadKey: reloadKey,
                  refreshListenable: _refreshSignal,
                  scrollingListenable: _scrollController,
                  centerTitle: true,
                  loader: () => AnalyticsCache.instance.get(
                    'summary|$reloadKey',
                    () => fetchAnalyticsSummary(filters),
                  ),
                  builder: (s) => _SummaryBody(summary: s),
                  skeletonLines: 4,
                ),
              ],
              const SizedBox(height: AppSpacing.lg),
              if (_eventPinned)
                _AnalyticsPanel<EventModerationDetail>(
                  title: AppLocalizations.get('moderationHealth'),
                  reloadKey: reloadKey,
                  refreshListenable: _refreshSignal,
                  scrollingListenable: _scrollController,
                  centerTitle: true,
                  loader: () => AnalyticsCache.instance.get(
                    'modevent|$reloadKey',
                    () => fetchEventModerationDetail(_selectedEvent!.id),
                  ),
                  builder: (m) => _EventModerationDetailBody(data: m),
                  skeletonLines: 6,
                )
              else
                _AnalyticsPanel<AnalyticsModeration>(
                  title: AppLocalizations.get('moderationHealth'),
                  reloadKey: reloadKey,
                  refreshListenable: _refreshSignal,
                  scrollingListenable: _scrollController,
                  centerTitle: true,
                  loader: () => AnalyticsCache.instance.get(
                    'moderation|$reloadKey',
                    () => fetchAnalyticsModeration(filters),
                  ),
                  builder: (m) => _ModerationBody(data: m, eventPinned: false),
                  skeletonLines: 5,
                ),
              const SizedBox(height: AppSpacing.lg),
              _AnalyticsPanel<AnalyticsEngagement>(
                title: AppLocalizations.get('engagement'),
                reloadKey: reloadKey,
                refreshListenable: _refreshSignal,
                scrollingListenable: _scrollController,
                centerTitle: true,
                loader: () => AnalyticsCache.instance.get(
                  'engagement|$_trendDays|$reloadKey',
                  () => fetchAnalyticsEngagement(filters, trendDays: _trendDays),
                ),
                builder: (e) => _EngagementBody(data: e),
                skeletonLines: 4,
              ),
              // cross-event ranking is meaningless for a single pinned event
              if (!_eventPinned) ...[
                const SizedBox(height: AppSpacing.lg),
                _AnalyticsPanel<List<RankedEvent>>(
                  title: AppLocalizations.get('mostViewed'),
                  reloadKey: reloadKey,
                  refreshListenable: _refreshSignal,
                  scrollingListenable: _scrollController,
                  centerTitle: true,
                  loader: () => AnalyticsCache.instance.get(
                    'top|views|3|$reloadKey',
                    () => fetchAnalyticsTop(filters, metric: 'views', limit: 3),
                  ),
                  builder: (rows) =>
                      _TopViewedBody(rows: rows, filters: filters),
                  skeletonLines: 3,
                ),
              ],
              const SizedBox(height: AppSpacing.lg),
              _AnalyticsPanel<AnalyticsRatings>(
                title: AppLocalizations.get('ratings'),
                reloadKey: reloadKey,
                refreshListenable: _refreshSignal,
                scrollingListenable: _scrollController,
                centerTitle: true,
                loader: () => AnalyticsCache.instance.get(
                  'ratings|3|$reloadKey',
                  () => fetchAnalyticsRatings(filters, topLimit: 3),
                ),
                builder: (r) => _RatingsBody(
                  data: r,
                  filters: filters,
                  showRankings: !_eventPinned,
                  eventId: _eventPinned ? _selectedEvent!.id : null,
                ),
                skeletonLines: 5,
              ),
              // per-category / per-organizer breakdowns are cross-event and hidden
              // while a single event is pinned
              if (!_eventPinned) ...[
                const SizedBox(height: AppSpacing.lg),
                _AnalyticsPanel<List<AnalyticsCategory>>(
                  title: AppLocalizations.get('categories'),
                  reloadKey: reloadKey,
                  refreshListenable: _refreshSignal,
                  scrollingListenable: _scrollController,
                  centerTitle: true,
                  loader: () => AnalyticsCache.instance.get(
                    'categories|$reloadKey',
                    () => fetchAnalyticsCategories(filters),
                  ),
                  builder: (rows) => _CategoriesBody(rows: rows),
                  skeletonLines: 4,
                ),
                const SizedBox(height: AppSpacing.lg),
                _AnalyticsPanel<List<AnalyticsOrganizer>>(
                  title: AppLocalizations.get('organizers'),
                  reloadKey: reloadKey,
                  refreshListenable: _refreshSignal,
                  scrollingListenable: _scrollController,
                  centerTitle: true,
                  loader: () => AnalyticsCache.instance.get(
                    'organizers|3|$reloadKey',
                    () => fetchAnalyticsOrganizers(filters, limit: 3),
                  ),
                  builder: (rows) =>
                      _OrganizersBody(rows: rows, filters: filters),
                  skeletonLines: 4,
                ),
              ],
              const SizedBox(height: AppSpacing.xl),
                    ]),
                  ),
                ),
              ],
            ),
          ),
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
    required this.categoryName,
    required this.organizer,
    required this.onPickPeriod,
    required this.onPickEvent,
    required this.onClearEvent,
    required this.onPickCategory,
    required this.onPickOrganizer,
  });

  final AnalyticsPeriod period;
  final AnalyticsEventOption? selectedEvent;
  final String? categoryName;
  final String? organizer;
  final VoidCallback onPickPeriod;
  final VoidCallback onPickEvent;
  final VoidCallback onClearEvent;
  final VoidCallback onPickCategory;
  final VoidCallback onPickOrganizer;

  @override
  Widget build(BuildContext context) {
    // When an event is pinned it is the sole active filter: show just its pill
    // (with clear). The period/category/organizer selections are preserved in
    // state and reappear when the event filter is cleared.
    if (selectedEvent != null) {
      return _FilterPill(
        label: selectedEvent!.title,
        highlighted: true,
        onTap: onPickEvent,
        trailing: GestureDetector(
          onTap: onClearEvent,
          behavior: HitTestBehavior.opaque,
          child: const Icon(Icons.close, size: 18, color: AppColors.primary),
        ),
      );
    }

    // Single horizontal scroll row of compact chips: sizing to content instead
    // of forcing every filter into an equal-width 2-column grid keeps short
    // labels (e.g. "All Events") from wasting half the row.
    return SizedBox(
      height: 36,
      child: ListView(
        scrollDirection: Axis.horizontal,
        physics: const ClampingScrollPhysics(),
        children: [
          _FilterPill(
            icon: Icons.calendar_today_outlined,
            label: period.type == PeriodType.custom
                ? AppLocalizations.get('custom')
                : period.label,
            highlighted: period.type == PeriodType.custom,
            onTap: onPickPeriod,
            compact: true,
          ),
          const SizedBox(width: AppSpacing.sm),
          _FilterPill(
            icon: Icons.event_note_outlined,
            label: AppLocalizations.get('allEvents'),
            onTap: onPickEvent,
            compact: true,
          ),
          const SizedBox(width: AppSpacing.sm),
          _FilterPill(
            icon: Icons.category_outlined,
            label: categoryName ?? AppLocalizations.get('allCategories'),
            highlighted: categoryName != null,
            onTap: onPickCategory,
            compact: true,
          ),
          const SizedBox(width: AppSpacing.sm),
          _FilterPill(
            icon: Icons.groups_outlined,
            label: organizer ?? AppLocalizations.get('allOrganizers'),
            highlighted: organizer != null,
            onTap: onPickOrganizer,
            compact: true,
          ),
        ],
      ),
    );
  }
}

class _FilterPill extends StatelessWidget {
  const _FilterPill({
    this.icon,
    required this.label,
    this.trailing,
    this.onTap,
    this.highlighted = false,
    this.compact = false,
  });

  final IconData? icon;
  final String label;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool highlighted;
  // Sizes the chip to its content (capped) instead of filling the parent's
  // width — used in the horizontally-scrolling filter row so short labels
  // ("All Events") don't stretch as wide as long ones (an organizer name).
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final fg = highlighted ? AppColors.primary : AppColors.textPrimary;
    final labelText = Text(
      label,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: (compact ? AppTextStyles.bodySmall : AppTextStyles.bodyMedium)
          .copyWith(color: fg, fontWeight: FontWeight.w700),
    );
    final radius = compact
        ? AppSpacing.borderRadiusLg
        : AppSpacing.borderRadiusMd;
    return Material(
      color: highlighted ? AppColors.primaryLight : Colors.white,
      borderRadius: radius,
      child: InkWell(
        onTap: onTap,
        borderRadius: radius,
        child: Container(
          height: compact ? 36 : null,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: compact ? 0 : AppSpacing.sm + 2,
          ),
          child: Row(
            mainAxisSize: compact ? MainAxisSize.min : MainAxisSize.max,
            children: [
              if (icon != null) ...[
                Icon(icon, size: compact ? 14 : 16, color: fg),
                const SizedBox(width: AppSpacing.sm),
              ],
              compact
                  ? ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 140),
                      child: labelText,
                    )
                  : Expanded(child: labelText),
              if (trailing != null) ...[const SizedBox(width: 4), trailing!],
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
    required this.refreshListenable,
    required this.scrollingListenable,
    this.centerTitle = false,
    this.skeletonLines = 3,
    super.key,
  });

  final String title;
  final String reloadKey;
  final Future<T> Function() loader;
  final Widget Function(T data) builder;
  final Listenable refreshListenable;
  final ScrollController scrollingListenable;
  final bool centerTitle;
  final int skeletonLines;

  @override
  State<_AnalyticsPanel<T>> createState() => _AnalyticsPanelState<T>();
}

class _AnalyticsPanelState<T> extends State<_AnalyticsPanel<T>>
    with AutomaticKeepAliveClientMixin {
  T? _data;
  Object? _error;
  bool _loading = false;
  int _requestId = 0;
  Timer? _applyResultTimer;

  @override
  void initState() {
    super.initState();
    widget.refreshListenable.addListener(_refresh);
    _load();
  }

  @override
  void dispose() {
    _applyResultTimer?.cancel();
    widget.refreshListenable.removeListener(_refresh);
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant _AnalyticsPanel<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refreshListenable != widget.refreshListenable) {
      oldWidget.refreshListenable.removeListener(_refresh);
      widget.refreshListenable.addListener(_refresh);
    }
    if (oldWidget.reloadKey != widget.reloadKey) {
      _load(clearData: true);
    }
  }

  void _refresh() => _load(showLoading: false);

  Future<void> _load({bool showLoading = true, bool clearData = false}) async {
    final requestId = ++_requestId;
    if (clearData) {
      _applyResultTimer?.cancel();
      setState(() {
        _data = null;
        _loading = true;
        _error = null;
      });
    } else if (showLoading || _data == null) {
      setState(() {
        _loading = true;
        _error = null;
      });
    } else if (_error != null) {
      setState(() => _error = null);
    }
    try {
      final result = await widget.loader();
      if (!mounted || requestId != _requestId) return;
      _applyResult(result, requestId);
    } catch (e) {
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  void _applyResult(T result, int requestId) {
    _applyResultTimer?.cancel();
    if (widget.scrollingListenable.hasClients &&
        widget.scrollingListenable.position.isScrollingNotifier.value) {
      _applyResultTimer = Timer(const Duration(milliseconds: 300), () {
        if (!mounted || requestId != _requestId) return;
        _applyResult(result, requestId);
      });
      return;
    }
    setState(() {
      _data = result;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return _PanelCard(
      title: widget.title,
      centerTitle: widget.centerTitle,
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

  @override
  bool get wantKeepAlive => true;
}

// ── Shared chrome: card, skeleton, error, empty ──────────────────────────────

class _PanelCard extends StatelessWidget {
  const _PanelCard({
    required this.title,
    required this.child,
    this.centerTitle = false,
  });

  final String title;
  final Widget child;
  final bool centerTitle;

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
                child: Text(
                  title,
                  textAlign: centerTitle ? TextAlign.center : TextAlign.start,
                  style: AppTextStyles.sectionHeader,
                ),
              ),
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
                Expanded(flex: 3, child: _bar(height: 12)),
                const SizedBox(width: AppSpacing.md),
                Expanded(child: _bar(height: 12)),
              ],
            ),
            if (i != widget.lines - 1) const SizedBox(height: AppSpacing.md),
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
          const Icon(
            Icons.error_outline,
            color: AppColors.error,
            size: AppSpacing.iconSm,
          ),
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
    final pending = _int('pending_review');
    final rejected = _int('rejected');
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
                  segments: [
                    _DonutSegment(value: approved, color: AppColors.success),
                    _DonutSegment(value: pending, color: AppColors.orange),
                    _DonutSegment(value: rejected, color: AppColors.error),
                  ],
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
                    label: AppLocalizations.get('rejected'),
                    value: rejected,
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
            _Stat(
              AppLocalizations.get('publishedThisWeek'),
              '${_int('published_this_week')}',
            ),
            _Stat(
              AppLocalizations.get('upcomingEvents'),
              '${_int('upcoming_events')}',
            ),
            _Stat(
              AppLocalizations.get('eventViews'),
              _compact(_int('total_event_views')),
            ),
            _Stat(
              AppLocalizations.get('registrationClicks'),
              '${_int('total_registration_clicks')}',
            ),
            _Stat(
              AppLocalizations.get('totalFavorites'),
              '${_int('total_favorites')}',
            ),
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
  const _ModerationBody({required this.data, this.eventPinned = false});

  final AnalyticsModeration data;
  final bool eventPinned;

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
            // queue size is portfolio-wide for all events only
            if (!eventPinned)
              _Stat(AppLocalizations.get('queueSize'), '${data.queueSize}'),
            _Stat(
              AppLocalizations.get('avgIterations'),
              data.avgReviewIterations?.toStringAsFixed(1) ?? '—',
            ),
            _Stat(
              AppLocalizations.get('timeToFirstDecision'),
              _humanDuration(data.avgTimeToFirstDecisionSeconds),
            ),
            _Stat(
              AppLocalizations.get('avgReviewTime'),
              _humanDuration(data.avgTotalReviewSeconds),
            ),
          ],
        ),
        // longest pending is redundant for a pinned event
        // threshold buckets are not useful for a pinned event
        if (!eventPinned) ...[
          if (data.longestPending != null) ...[
            const SizedBox(height: AppSpacing.md),
            _StatTile(
              stat: _Stat(
                AppLocalizations.get('longestPending'),
                _humanDuration(data.longestPending!.waitingSeconds),
                caption: data.longestPending!.title,
                centered: true,
              ),
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
      ],
    );
  }
}

/// Per-event moderation detail — shown instead of _ModerationBody when a
/// single event is pinned. Renders the full chronological history log plus
/// exact timing/iteration counters. No rates, no averages, no tooltips.
class _EventModerationDetailBody extends StatelessWidget {
  const _EventModerationDetailBody({required this.data});

  final EventModerationDetail data;

  @override
  Widget build(BuildContext context) {
    final history = data.history;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Quick-glance counters ─────────────────────────────────────────
        _StatGrid(
          stats: [
            _Stat(
              AppLocalizations.get('totalReviewTime'),
              _humanDuration(data.totalReviewSeconds),
            ),
            _Stat(
              AppLocalizations.get('reviewIterations'),
              '${data.reviewIterations}',
            ),
            _Stat(
              AppLocalizations.get('needsChangesCount'),
              '${data.needsChangesCount}',
            ),
            _Stat(
              AppLocalizations.get('resubmissionCount'),
              '${data.resubmissionCount}',
            ),
          ],
        ),

        // ── Full history timeline ─────────────────────────────────────────
        if (history.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.lg),
          Text(
            AppLocalizations.get('moderationTimeline'),
            style: AppTextStyles.bodyMedium.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          for (var i = 0; i < history.length; i++)
            _ModerationTimelineEntry(
              entry: history[i],
              isLast: i == history.length - 1,
            ),
        ],
      ],
    );
  }
}

class _ModerationTimelineEntry extends StatelessWidget {
  const _ModerationTimelineEntry({required this.entry, required this.isLast});

  final ModerationLogEntry entry;
  final bool isLast;

  static const _dotSize = 10.0;
  static const _lineWidth = 2.0;

  @override
  Widget build(BuildContext context) {
    final color = _actionColor(entry.action);
    final label = _localizeAction(entry.action);

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Connector column (dot + vertical line) ─────────────────────
          SizedBox(
            width: 24,
            child: Column(
              children: [
                // Offset pushes the dot to the vertical centre of the label
                // text line (bodyMedium ~18 px tall → (18 − 10) / 2 = 4 px).
                const SizedBox(height: 4),
                Container(
                  width: _dotSize,
                  height: _dotSize,
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Center(
                      child: Container(
                        width: _lineWidth,
                        color: AppColors.lightGrey,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          // ── Entry card ─────────────────────────────────────────────────
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Action label + timestamp
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          label,
                          style: AppTextStyles.bodyMedium.copyWith(
                            color: color,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      Text(
                        _fmtDatetime(entry.createdAt),
                        style: AppTextStyles.bodySmall.copyWith(
                          color: AppColors.grey,
                        ),
                      ),
                    ],
                  ),
                  // Actor name
                  if (entry.actorName != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      entry.actorName!,
                      style: AppTextStyles.bodySmall.copyWith(
                        color: AppColors.grey,
                      ),
                    ),
                  ],
                  // Comment bubble
                  if (entry.comment != null && entry.comment!.isNotEmpty) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.sm,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.fieldBackground,
                        borderRadius: AppSpacing.borderRadiusMd,
                      ),
                      child: Text(
                        entry.comment!,
                        style: AppTextStyles.bodyMedium,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  static Color _actionColor(String action) {
    switch (action) {
      case 'approved':
      case 'restored':
        return AppColors.success;
      case 'rejected':
        return AppColors.error;
      case 'needs_changes':
        return AppColors.orange;
      case 'submitted':
      case 'resubmitted':
        return AppColors.primary;
      case 'cancelled':
        return AppColors.error;
      case 'archived':
      case 'edited':
        return AppColors.grey;
      default:
        return AppColors.grey;
    }
  }

  static String _localizeAction(String action) {
    switch (action) {
      case 'approved':
        return AppLocalizations.get('approvedLabel');
      case 'rejected':
        return AppLocalizations.get('rejectedLabel');
      case 'needs_changes':
        return AppLocalizations.get('needsChangesLabel');
      case 'pending':
        return AppLocalizations.get('pendingLabel');
      case 'submitted':
        return AppLocalizations.get('submittedAction');
      case 'resubmitted':
        return AppLocalizations.get('resubmitted');
      case 'cancelled':
        return AppLocalizations.get('cancelledLabel');
      case 'archived':
        return AppLocalizations.get('archivedLabel');
      case 'restored':
        return AppLocalizations.get('restoredAction');
      case 'edited':
        return AppLocalizations.get('editedAction');
      default:
        return action;
    }
  }

  static String _fmtDatetime(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      final mo = dt.month.toString().padLeft(2, '0');
      final d = dt.day.toString().padLeft(2, '0');
      final h = dt.hour.toString().padLeft(2, '0');
      final min = dt.minute.toString().padLeft(2, '0');
      return '$d.$mo ${dt.year} $h:$min';
    } catch (_) {
      return iso;
    }
  }
}

// ── Reviews bottom sheet ─────────────────────────────────────────────────────

class _ReviewsSheet extends StatefulWidget {
  const _ReviewsSheet({required this.eventId});

  final int eventId;

  @override
  State<_ReviewsSheet> createState() => _ReviewsSheetState();
}

class _ReviewsSheetState extends State<_ReviewsSheet> {
  static const _pageSize = 20;

  final List<EventReview> _items = [];
  // Starts false so the initial [_loadMore] in initState actually runs — the
  // method short-circuits while a load is already in flight.
  bool _loading = false;
  bool _hasMore = true;
  Object? _error;
  int _offset = 0;

  @override
  void initState() {
    super.initState();
    _loadMore();
  }

  Future<void> _loadMore() async {
    if (!_hasMore || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await fetchEventReviews(
        widget.eventId,
        limit: _pageSize,
        offset: _offset,
      );
      if (!mounted) return;
      setState(() {
        _items.addAll(page);
        _offset += page.length;
        _hasMore = page.length == _pageSize;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.4,
      minChildSize: 0.3,
      maxChildSize: 0.8,
      expand: false,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              // ── Handle + title ────────────────────────────────────────
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg,
                  vertical: AppSpacing.md,
                ),
                child: Text(
                  AppLocalizations.get('allReviews'),
                  textAlign: TextAlign.center,
                  style: AppTextStyles.sectionHeader,
                ),
              ),
              const Divider(height: 1),
              // ── Body ──────────────────────────────────────────────────
              Expanded(child: _buildBody(scrollController)),
            ],
          ),
        );
      },
    );
  }

  Widget _buildBody(ScrollController scrollController) {
    if (_loading && _items.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.xl),
          child: CircularProgressIndicator(),
        ),
      );
    }
    if (_error != null && _items.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              AppLocalizations.get('failedToLoad'),
              style: AppTextStyles.bodyMedium.copyWith(color: AppColors.error),
            ),
            const SizedBox(height: AppSpacing.sm),
            AppTextButton(
              text: AppLocalizations.get('retry'),
              onPressed: () {
                setState(() {
                  _loading = false;
                });
                _loadMore();
              },
            ),
          ],
        ),
      );
    }
    if (_items.isEmpty) {
      return Center(
        child: Text(
          AppLocalizations.get('noReviewsYet'),
          style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
        ),
      );
    }
    // Trigger the next page as the list approaches the bottom. The list is
    // driven by the DraggableScrollableSheet's controller, so pagination has to
    // hang off scroll notifications rather than a detached ScrollController.
    return NotificationListener<ScrollNotification>(
      onNotification: (notification) {
        final m = notification.metrics;
        if (m.axis == Axis.vertical &&
            m.pixels >= m.maxScrollExtent - 200 &&
            _hasMore &&
            !_loading) {
          _loadMore();
        }
        return false;
      },
      child: ListView.builder(
        controller: scrollController,
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg,
          AppSpacing.sm,
          AppSpacing.lg,
          AppSpacing.lg,
        ),
        itemCount: _items.length + (_hasMore ? 1 : 0),
        itemBuilder: (context, i) {
          if (i == _items.length) {
            if (_error != null) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.md),
                  child: AppTextButton(
                    text: AppLocalizations.get('retry'),
                    onPressed: () {
                      setState(() => _loading = false);
                      _loadMore();
                    },
                  ),
                ),
              );
            }
            if (_loading) {
              return const Center(
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.md),
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              );
            }
            return const SizedBox.shrink();
          }
          return Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: _ReviewCard(review: _items[i], index: i),
          );
        },
      ),
    );
  }
}

class _ReviewCard extends StatefulWidget {
  const _ReviewCard({required this.review, required this.index});

  final EventReview review;
  final int index;

  @override
  State<_ReviewCard> createState() => _ReviewCardState();
}

class _ReviewCardState extends State<_ReviewCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _fade;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 350),
    );
    _fade = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
    _slide = Tween<Offset>(
      begin: const Offset(0, 0.12),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic));

    // stagger each card by its index so they cascade in
    Future.delayed(Duration(milliseconds: widget.index * 60), () {
      if (mounted) _ctrl.forward();
    });
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final review = widget.review;
    final hasContent = review.content != null && review.content!.isNotEmpty;

    return FadeTransition(
      opacity: _fade,
      child: SlideTransition(
        position: _slide,
        child: Container(
          decoration: BoxDecoration(
            color: AppColors.fieldBackground,
            borderRadius: AppSpacing.borderRadiusMd,
          ),
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Header: avatar + name + stars ─────────────────────────
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  _Avatar(photoUrl: review.photoUrl, name: review.displayName),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          review.displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: AppTextStyles.bodyMedium.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        if (review.username != null)
                          Text(
                            '@${review.username}',
                            style: AppTextStyles.bodySmall.copyWith(
                              color: AppColors.grey,
                            ),
                          ),
                      ],
                    ),
                  ),
                  _StarPills(score: review.score),
                ],
              ),
              // ── Review text ───────────────────────────────────────────
              if (hasContent) ...[
                const SizedBox(height: AppSpacing.sm),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md,
                    vertical: AppSpacing.sm,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(AppSpacing.sm),
                  ),
                  child: Text(
                    review.content!,
                    style: AppTextStyles.bodyMedium,
                  ),
                ),
              ],
              // ── Date ──────────────────────────────────────────────────
              const SizedBox(height: AppSpacing.xs),
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  _fmtDate(review.createdAt),
                  style: AppTextStyles.bodySmall.copyWith(
                    color: AppColors.grey,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _fmtDate(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      final y = dt.year;
      final mo = dt.month.toString().padLeft(2, '0');
      final d = dt.day.toString().padLeft(2, '0');
      return '$d.$mo.$y';
    } catch (_) {
      return iso;
    }
  }
}

/// Five filled/empty star dots with the numeric score.
class _StarPills extends StatelessWidget {
  const _StarPills({required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 1; i <= 5; i++)
          Padding(
            padding: const EdgeInsets.only(left: 2),
            child: Icon(
              i <= score ? Icons.star_rounded : Icons.star_outline_rounded,
              size: 16,
              color: i <= score ? AppColors.primary : AppColors.lightGrey,
            ),
          ),
      ],
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({this.photoUrl, required this.name});

  final String? photoUrl;
  final String name;

  @override
  Widget build(BuildContext context) {
    final initials = name.trim().isEmpty
        ? '?'
        : name
            .trim()
            .split(RegExp(r'\s+'))
            .where((w) => w.isNotEmpty)
            .take(2)
            .map((w) => w[0].toUpperCase())
            .join();
    final hasPhoto = photoUrl != null && photoUrl!.isNotEmpty;
    return CircleAvatar(
      radius: 22,
      backgroundColor: AppColors.primaryLight,
      // Foreground image sits over the initials; if it fails to load the
      // initials remain visible instead of a broken-image glyph.
      foregroundImage: hasPhoto ? NetworkImage(photoUrl!) : null,
      onForegroundImageError: hasPhoto ? (_, _) {} : null,
      child: Text(
        initials,
        style: AppTextStyles.bodySmall.copyWith(
          color: AppColors.primary,
          fontWeight: FontWeight.w700,
        ),
      ),
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
            _Stat(
              AppLocalizations.get('eventViews'),
              _compact(t.views),
              span: 2,
            ),
            _Stat(
              AppLocalizations.get('registrationClicks'),
              '${t.registerClicks}',
            ),
            _Stat(AppLocalizations.get('shares'), '${t.shareClicks}'),
            _Stat(AppLocalizations.get('reminders'), '${t.reminderCreates}'),
            _Stat(
              AppLocalizations.get('totalFavorites'),
              '${t.favoritesAdded}',
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.lg),
        _ViewsOverTime(points: data.viewsOverTime),
      ],
    );
  }
}

/// Views-over-time with a peak/total readout so the trend is actually legible,
/// plus a clean empty state when nothing was logged in the window.
class _ViewsOverTime extends StatelessWidget {
  const _ViewsOverTime({required this.points});

  final List<TrendPoint> points;

  @override
  Widget build(BuildContext context) {
    final total = points.fold<int>(0, (a, p) => a + p.count);
    TrendPoint? peak;
    for (final p in points) {
      if (peak == null || p.count > peak.count) peak = p;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: double.infinity,
          child: Text(
            AppLocalizations.get('viewsOverTime'),
            textAlign: TextAlign.center,
            style: AppTextStyles.bodyMedium.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        if (total == 0)
          _EmptyInsight(
            icon: Icons.show_chart,
            text: AppLocalizations.get('noActivityInPeriod'),
          )
        else ...[
          SizedBox(height: 56, child: _Sparkline(points: points)),
          const SizedBox(height: AppSpacing.xs),
          if (peak != null)
            Text(
              '${AppLocalizations.get('peak')}: ${peak.count} · ${_formatTrendDate(peak.date)}',
              style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
            ),
        ],
      ],
    );
  }

  static String _formatTrendDate(String value) {
    try {
      final date = DateTime.parse(value);
      final day = date.day.toString().padLeft(2, '0');
      final month = date.month.toString().padLeft(2, '0');
      return '$day.$month.${date.year}';
    } catch (_) {
      return value;
    }
  }
}

class _RatingsBody extends StatelessWidget {
  const _RatingsBody({
    required this.data,
    required this.filters,
    this.showRankings = true,
    this.eventId,
  });

  final AnalyticsRatings data;
  final AnalyticsFilters filters;
  final bool showRankings;
  final int? eventId;

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
              style: Theme.of(
                context,
              ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(width: AppSpacing.sm),
            const Icon(Icons.star, color: AppColors.primary, size: 20),
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
        // "View reviews" button when a single event is pinned
        if (eventId != null) ...[
          const SizedBox(height: AppSpacing.xs),
          _ShowAllButton(
            label: AppLocalizations.get('viewReviews'),
            onTap: () => _showReviewsSheet(context, eventId!),
          ),
        ],
        if (showRankings && data.eventsWithZeroReviews > 0) ...[
          const SizedBox(height: AppSpacing.xs),
          _InlineFact(
            label: AppLocalizations.get('zeroReviews'),
            value: '${data.eventsWithZeroReviews}',
            boldValue: false,
          ),
        ],
        // top-rated ranking is cross-event and hidden for a pinned event
        if (showRankings) ...[
          const SizedBox(height: AppSpacing.md),
          SizedBox(
            width: double.infinity,
            child: Text(
              AppLocalizations.get('topRated'),
              textAlign: TextAlign.center,
              style: AppTextStyles.bodyMedium.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          _RankedList(rows: data.topRated.take(3).toList(), ratingStyle: true),
          if (data.topRated.length >= 3)
            _ShowAllButton(
              onTap: () => showRankingSheet(
                context: context,
                title: AppLocalizations.get('topRated'),
                loadPage: (offset, limit) async {
                  final page = await fetchAnalyticsTop(
                    filters,
                    metric: 'rated',
                    limit: limit,
                    offset: offset,
                  );
                  return page
                      .map(
                        (e) => RankRow(
                          label: e.title,
                          value: e.value.toStringAsFixed(1),
                          caption: e.count == null
                              ? null
                              : '${e.count} ${AppLocalizations.get('reviews')}',
                        ),
                      )
                      .toList();
                },
              ),
            ),
        ],
      ],
    );
  }

  Future<void> _showReviewsSheet(BuildContext context, int id) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ReviewsSheet(eventId: id),
    );
  }
}

class _CategoriesBody extends StatelessWidget {
  const _CategoriesBody({required this.rows});

  final List<AnalyticsCategory> rows;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return _EmptyInsight(
        icon: Icons.category_outlined,
        text: AppLocalizations.get('nothingYet'),
      );
    }
    final maxCount = rows
        .map((r) => r.eventCount)
        .fold<int>(1, (a, b) => a > b ? a : b);
    final top = rows.take(3).toList();
    return Column(
      children: [
        for (var i = 0; i < top.length; i++) ...[
          _BreakdownRow(
            label: top[i].category,
            value: top[i].eventCount,
            share: top[i].eventCount / maxCount,
            caption: _categoryCaption(top[i]),
            valueLabel: _pluralize(
              top[i].eventCount,
              AppLocalizations.get('event').toLowerCase(),
              AppLocalizations.get('events').toLowerCase(),
            ),
          ),
          if (i != top.length - 1) const SizedBox(height: AppSpacing.md),
        ],
        if (rows.length > 3)
          _ShowAllButton(
            onTap: () => showRankingSheet(
              context: context,
              title: AppLocalizations.get('categories'),
              // categories are already fully loaded — slice in memory
              loadPage: (offset, limit) async => rows
                  .skip(offset)
                  .take(limit)
                  .map(
                    (c) => RankRow(
                      label: c.category,
                      value: '${c.eventCount}',
                      caption: _categoryCaption(c),
                    ),
                  )
                  .toList(),
            ),
          ),
      ],
    );
  }

  static String _categoryCaption(AnalyticsCategory c) =>
      '${AppLocalizations.get('eventViews')} ${_compact(c.views)}  ·  '
      '${(c.approvalRate * 100).toStringAsFixed(0)}% '
      '${AppLocalizations.get('approvedLabel').toLowerCase()}'
      '${c.averageRating != null ? '  ·  ★ ${c.averageRating!.toStringAsFixed(1)}' : ''}';
}

class _OrganizersBody extends StatelessWidget {
  const _OrganizersBody({required this.rows, required this.filters});

  final List<AnalyticsOrganizer> rows;
  final AnalyticsFilters filters;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return _EmptyInsight(
        icon: Icons.groups_outlined,
        text: AppLocalizations.get('nothingYet'),
      );
    }
    final maxCount = rows
        .map((r) => r.eventsCreated)
        .fold<int>(1, (a, b) => a > b ? a : b);
    final top = rows.take(3).toList();
    return Column(
      children: [
        for (var i = 0; i < top.length; i++) ...[
          _BreakdownRow(
            label: top[i].organizer,
            value: top[i].eventsCreated,
            share: top[i].eventsCreated / maxCount,
            caption: _organizerCaption(top[i]),
            valueLabel: _pluralize(
              top[i].eventsCreated,
              AppLocalizations.get('event').toLowerCase(),
              AppLocalizations.get('events').toLowerCase(),
            ),
          ),
          if (i != top.length - 1) const SizedBox(height: AppSpacing.md),
        ],
        if (rows.length >= 3)
          _ShowAllButton(
            onTap: () => showRankingSheet(
              context: context,
              title: AppLocalizations.get('organizers'),
              loadPage: (offset, limit) async {
                final page = await fetchAnalyticsOrganizers(
                  filters,
                  limit: limit,
                  offset: offset,
                );
                return page
                    .map(
                      (o) => RankRow(
                        label: o.organizer,
                        value: '${o.eventsCreated}',
                        caption: _organizerCaption(o),
                      ),
                    )
                    .toList();
              },
            ),
          ),
      ],
    );
  }

  static String _organizerCaption(AnalyticsOrganizer o) =>
      '${AppLocalizations.get('eventViews')} ${_compact(o.views)}  ·  '
      '${(o.approvalRate * 100).toStringAsFixed(0)}% '
      '${AppLocalizations.get('approvedLabel').toLowerCase()}'
      '${o.averageRating != null ? '  ·  ★ ${o.averageRating!.toStringAsFixed(1)}' : ''}';
}

/// A labelled bar with a value and a small caption line — used for the
/// category/organizer breakdown rows.
class _BreakdownRow extends StatelessWidget {
  const _BreakdownRow({
    required this.label,
    required this.value,
    required this.share,
    required this.caption,
    this.valueLabel,
  });

  final String label;
  final int value;
  final double share;
  final String caption;

  /// Optional muted label shown after the number, e.g. "events".
  final String? valueLabel;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
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
            Text(
              '$value',
              style: AppTextStyles.bodyMedium.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
            if (valueLabel != null) ...[
              const SizedBox(width: 3),
              Text(
                valueLabel!,
                style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
              ),
            ],
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
        const SizedBox(height: 4),
        Text(
          caption,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
        ),
      ],
    );
  }
}

// ── Leaf widgets (reused across panels) ──────────────────────────────────────

/// "Show all" affordance that opens the full server-sorted list in a sheet.
class _ShowAllButton extends StatelessWidget {
  const _ShowAllButton({required this.onTap, this.label});

  final VoidCallback onTap;
  final String? label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: AppTextButton(
        text: label ?? AppLocalizations.get('showAll'),
        onPressed: onTap,
      ),
    );
  }
}

/// Most-viewed panel body: top 3 inline + "Show all" (server-paginated).
class _TopViewedBody extends StatelessWidget {
  const _TopViewedBody({required this.rows, required this.filters});

  final List<RankedEvent> rows;
  final AnalyticsFilters filters;

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
        _RankedList(rows: rows.take(3).toList()),
        if (rows.length >= 3)
          _ShowAllButton(
            onTap: () => showRankingSheet(
              context: context,
              title: AppLocalizations.get('mostViewed'),
              loadPage: (offset, limit) async {
                final page = await fetchAnalyticsTop(
                  filters,
                  metric: 'views',
                  limit: limit,
                  offset: offset,
                );
                return page
                    .map(
                      (e) => RankRow(
                        label: e.title,
                        value: _compact(e.value.toInt()),
                      ),
                    )
                    .toList();
              },
            ),
          ),
      ],
    );
  }
}

class _RankedList extends StatelessWidget {
  const _RankedList({required this.rows, this.ratingStyle = false});

  final List<RankedEvent> rows;
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
                  style: AppTextStyles.bodyMedium.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                ratingStyle
                    ? rows[i].value.toStringAsFixed(1)
                    : _compact(rows[i].value.toInt()),
                style: AppTextStyles.bodyMedium.copyWith(
                  fontWeight: FontWeight.w800,
                  color: AppColors.primary,
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
  const _RateRow({
    required this.label,
    required this.rate,
    required this.color,
  });

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
                style: AppTextStyles.bodyMedium.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Text(
              '${(rate * 100).toStringAsFixed(0)}%',
              style: AppTextStyles.bodyMedium.copyWith(
                fontWeight: FontWeight.w800,
              ),
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
  const _Stat(
    this.label,
    this.value, {
    this.caption,
    this.span = 1,
    this.centered = true,
  });
  final String label;
  final String value;
  final String? caption;
  final int span;
  final bool centered;
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
            for (final stat in stats) ...[
              SizedBox(
                width:
                    itemWidth * stat.span.clamp(1, columns) +
                    spacing * (stat.span.clamp(1, columns) - 1),
                child: _StatTile(stat: stat),
              ),
            ],
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
    final centered = stat.centered || stat.span > 1;
    final content = Container(
      constraints: const BoxConstraints(minHeight: 82),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Column(
        crossAxisAlignment: centered
            ? CrossAxisAlignment.center
            : CrossAxisAlignment.start,
        mainAxisAlignment: centered
            ? MainAxisAlignment.center
            : MainAxisAlignment.start,
        children: [
          _AnimatedValue(
            value: stat.value,
            style: AppTextStyles.bodyLarge.copyWith(
              fontWeight: FontWeight.w800,
            ),
            textAlign: centered ? TextAlign.center : TextAlign.start,
          ),
          const SizedBox(height: 2),
          Row(
            mainAxisAlignment: centered
                ? MainAxisAlignment.center
                : MainAxisAlignment.start,
            children: [
              Flexible(
                child: Text(
                  stat.label,
                  textAlign: centered ? TextAlign.center : TextAlign.start,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTextStyles.bodySmall.copyWith(
                    color: AppColors.grey,
                  ),
                ),
              ),
            ],
          ),
          if (stat.caption != null) ...[
            const SizedBox(height: 2),
            Text(
              stat.caption!,
              textAlign: centered ? TextAlign.center : TextAlign.start,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
            ),
          ],
        ],
      ),
    );
    return content;
  }
}

/// Fades between values when a metric changes (e.g. on filter switch), so
/// numbers update smoothly instead of snapping.
class _AnimatedValue extends StatelessWidget {
  const _AnimatedValue({
    required this.value,
    required this.style,
    this.textAlign,
  });

  final String value;
  final TextStyle style;
  final TextAlign? textAlign;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 220),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (child, animation) =>
          FadeTransition(opacity: animation, child: child),
      child: Text(
        value,
        key: ValueKey(value),
        style: style,
        textAlign: textAlign,
      ),
    );
  }
}

class _InlineFact extends StatelessWidget {
  const _InlineFact({
    required this.label,
    required this.value,
    this.icon,
    this.color,
    this.boldValue = true,
  });

  final IconData? icon;
  final String label;
  final String value;
  final Color? color;
  final bool boldValue;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        if (icon != null) ...[
          Icon(icon, size: AppSpacing.iconSm, color: color ?? AppColors.grey),
          const SizedBox(width: AppSpacing.sm),
        ],
        Expanded(
          child: Text(
            label,
            style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
          ),
        ),
        Text(
          value,
          style: AppTextStyles.bodyMedium.copyWith(
            fontWeight: boldValue ? FontWeight.w800 : FontWeight.w400,
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
  const _EmptyInsight({this.icon, required this.text});

  final IconData? icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
      child: Text(
        text,
        style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
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
    return CustomPaint(size: Size.infinite, painter: _SparklinePainter(points));
  }
}

class _SparklinePainter extends CustomPainter {
  _SparklinePainter(this.points);

  final List<TrendPoint> points;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final maxValue = points
        .map((p) => p.count)
        .fold<int>(0, (a, b) => a > b ? a : b);
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

class _DonutSegment {
  const _DonutSegment({required this.value, required this.color});

  final int value;
  final Color color;
}

class _DonutPainter extends CustomPainter {
  const _DonutPainter({required this.segments});

  final List<_DonutSegment> segments;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = size.width * 0.12;
    final rect = Offset.zero & size;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..color = AppColors.lightGrey;
    canvas.drawArc(rect.deflate(stroke / 2), 0, 6.28318, false, paint);
    final total = segments.fold<int>(0, (sum, segment) => sum + segment.value);
    if (total <= 0) return;

    var start = -1.5708;
    for (final segment in segments) {
      if (segment.value <= 0) continue;
      final sweep = 6.28318 * (segment.value / total);
      paint.color = segment.color;
      canvas.drawArc(rect.deflate(stroke / 2), start, sweep, false, paint);
      start += sweep;
    }
  }

  @override
  bool shouldRepaint(_DonutPainter oldDelegate) {
    if (oldDelegate.segments.length != segments.length) return true;
    for (var i = 0; i < segments.length; i++) {
      if (oldDelegate.segments[i].value != segments[i].value ||
          oldDelegate.segments[i].color != segments[i].color) {
        return true;
      }
    }
    return false;
  }
}

// ── Formatting helpers ───────────────────────────────────────────────────────

String _pluralize(int n, String singular, String plural) =>
    n == 1 ? singular : plural;

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
