import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/cache_store.dart';
import '../../core/localization.dart';
import '../../models/event_model.dart';
import '../events/event_card.dart';
import '../events/event_detail_screen.dart';
import '../shared/stale_banner.dart';

/// University Coordinator dashboard: every incoming request awaiting a decision,
/// with work filters by club (organizer) and by date.
///
/// Data source: `GET /api/flutter/events/pending` (admin-only). Tapping a
/// request opens [EventDetailScreen], which already carries the full context
/// (IT needs, materials, location, organizer) and the approve / request-changes
/// / reject actions wired to `PATCH /events/{id}/status`. On approval the slot
/// auto-blocks in the shared calendar, since the calendar reads approved events.
class CoordinatorDashboardScreen extends StatefulWidget {
  const CoordinatorDashboardScreen({super.key});

  @override
  State<CoordinatorDashboardScreen> createState() =>
      _CoordinatorDashboardScreenState();
}

class _CoordinatorDashboardScreenState
    extends State<CoordinatorDashboardScreen> {
  // The queue is time-critical; the poll cadence is retained as an SSE fallback,
  // but a tick only reaches the network when the (shorter) pending TTL has
  // elapsed — see [EventCache.pending].
  static const _pollInterval = Duration(seconds: 20);

  bool _loading = true;
  String? _error;
  bool _stale = false;
  List<EventModel> _events = [];
  Timer? _pollTimer;

  // When on, the queue shows rejected / needs-changes events instead of pending.
  // Backend fetch also switches to the rejected cache key.
  bool _showRejected = false;

  @override
  void initState() {
    super.initState();
    final cached = EventCache.instance.peekPending(includeRejected: _showRejected);
    _events = cached ?? [];
    _loading = cached == null;
    EventCache.instance.addListener(_onCacheChanged);
    _refresh();
    _pollTimer = Timer.periodic(_pollInterval, (_) => _refresh());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    EventCache.instance.removeListener(_onCacheChanged);
    super.dispose();
  }

  void _onCacheChanged() {
    if (!mounted) return;
    final cached = EventCache.instance.peekPending(includeRejected: _showRejected);
    if (cached != null) {
      setState(() {
        _events = cached;
        _loading = false;
      });
    }
    _refresh();
  }

  /// Revalidate the active queue. Skips the network while the cache is fresh;
  /// keeps the last list visible on failure and flags staleness once it is old.
  Future<void> _refresh({bool force = false}) async {
    final includeRejected = _showRejected;
    try {
      final pending = await EventCache.instance.pending(
        includeRejected: includeRejected,
        force: force,
      );
      if (!mounted || includeRejected != _showRejected) return;
      setState(() {
        _events = pending;
        _loading = false;
        _error = null;
        _stale = false;
      });
    } catch (e) {
      if (!mounted || includeRejected != _showRejected) return;
      final cached =
          EventCache.instance.peekPending(includeRejected: includeRejected);
      if (cached != null) {
        final at =
            EventCache.instance.fetchedAtPending(includeRejected: includeRejected);
        setState(() {
          _events = cached;
          _loading = false;
          _stale = at != null &&
              DateTime.now().difference(at) > CacheTtl.stalenessThreshold;
        });
      } else {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  Future<void> _toggleRejected() async {
    setState(() {
      _showRejected = !_showRejected;
      // Adopt the other key's cached contents instantly (may be null → spinner
      // only if that view was never loaded this session).
      final cached =
          EventCache.instance.peekPending(includeRejected: _showRejected);
      _events = cached ?? [];
      _loading = cached == null;
    });
    await _refresh();
  }

  List<EventModel> get _filtered {
    final source = _showRejected
        ? _events.where(
            (e) => e.status == 'rejected' || e.status == 'needs_changes',
          )
        : _events;
    return source.toList()
      ..sort((a, b) => _eventTimestamp(a).compareTo(_eventTimestamp(b)));
  }

  List<({String date, String label, List<EventModel> events})> _dateGroups(
    List<EventModel> events,
  ) {
    final groups = <String, List<EventModel>>{};
    for (final event in events) {
      groups.putIfAbsent(event.eventDate, () => []).add(event);
    }
    final entries = groups.entries.toList()..sort((a, b) => a.key.compareTo(b.key));
    return [
      for (final entry in entries)
        (
          date: entry.key,
          label: _formatDateLabel(entry.key),
          events: entry.value,
        ),
    ];
  }

  int _eventTimestamp(EventModel event) {
    try {
      final date = event.eventDate.split('-');
      final time = event.eventTime.split(':');
      return DateTime(
        int.parse(date[0]),
        int.parse(date[1]),
        int.parse(date[2]),
        int.parse(time[0]),
        int.parse(time[1]),
      ).millisecondsSinceEpoch;
    } catch (_) {
      return 0;
    }
  }

  String _formatDateLabel(String iso) {
    try {
      final parts = iso.split('-');
      final date = DateTime(
        int.parse(parts[0]),
        int.parse(parts[1]),
        int.parse(parts[2]),
      );
      return DateFormat('MMMM d, yyyy').format(date);
    } catch (_) {
      return iso;
    }
  }

  Future<void> _openDetail(EventModel event) async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => EventDetailScreen(event: event)),
    );
    await _refresh(force: true);
  }

  @override
  Widget build(BuildContext context) {
    final title = AppLocalizations.get('requests');
    return Scaffold(
      body: ScrollConfiguration(
        behavior: ScrollConfiguration.of(
          context,
        ).copyWith(physics: const ClampingScrollPhysics()),
        child: NestedScrollView(
          headerSliverBuilder: (ctx, _) => [
            AppSliverAppBar(
              title: title,
              actions: [
                IconButton(
                  tooltip: _showRejected
                      ? AppLocalizations.get('showPending')
                      : AppLocalizations.get('showRejected'),
                  icon: Icon(
                    Icons.block_rounded,
                    color: _showRejected
                        ? AppColors.primary
                        : AppColors.textSecondary,
                  ),
                  onPressed: _toggleRejected,
                ),
              ],
            ),
          ],
          body: _buildBody(context),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) {
      return const CustomScrollView(
        slivers: [
          SliverFillRemaining(
            hasScrollBody: false,
            child: Center(child: AppLoader()),
          ),
        ],
      );
    }

    if (_error != null) {
      return CustomScrollView(
        slivers: [
          SliverFillRemaining(
            hasScrollBody: false,
            child: Center(
              child: Padding(
                padding: AppSpacing.screenPadding,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_error!, textAlign: TextAlign.center),
                    const SizedBox(height: AppSpacing.df),
                    AppSecondaryButton(
                      text: AppLocalizations.get('retry'),
                      onPressed: () => _refresh(force: true),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      );
    }

    final filtered = _filtered;

    return RefreshIndicator(
      onRefresh: () => _refresh(force: true),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          if (_stale) const SliverToBoxAdapter(child: StaleBanner()),
          if (filtered.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: Center(
                child: Padding(
                  padding: AppSpacing.screenPadding,
                  child: Text(
                    AppLocalizations.get('noRequestsUnderReview'),
                    textAlign: TextAlign.center,
                    style: Theme.of(
                      context,
                    ).textTheme.bodyLarge?.copyWith(color: AppColors.grey),
                  ),
                ),
              ),
            )
          else
            _dateGroupedSliver(filtered),
        ],
      ),
    );
  }

  Widget _dateGroupedSliver(List<EventModel> events) {
    final groups = _dateGroups(events);
    final items = <Widget>[];
    for (var g = 0; g < groups.length; g++) {
      final group = groups[g];
      items.add(
        _RequestDateHeader(label: group.label, first: g == 0),
      );
      for (final event in group.events) {
        items.add(_requestCard(event));
      }
    }
    return SliverPadding(
      padding: const EdgeInsets.only(
        left: AppSpacing.df,
        right: AppSpacing.df,
        bottom: 108.0,
      ),
      sliver: SliverList(
        delegate: SliverChildListDelegate(items),
      ),
    );
  }

  Widget _requestCard(EventModel event) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: EventCard(
        event: event,
        hideStatus: true,
        showCategory: false,
        onTap: () => _openDetail(event),
      ),
    );
  }
}


class _RequestDateHeader extends StatelessWidget {
  const _RequestDateHeader({required this.label, this.first = false});

  final String label;
  final bool first;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        top: first ? AppSpacing.sm : AppSpacing.df,
        bottom: AppSpacing.sm,
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: Theme.of(
                  context,
                ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
