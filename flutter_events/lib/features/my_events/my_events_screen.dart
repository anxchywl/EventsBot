import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/cache_store.dart';
import '../../core/localization.dart';
import '../../models/event_model.dart';
import '../events/event_card.dart';
import '../events/event_detail_screen.dart';
import '../shared/stale_banner.dart';
import '../shared/loading_skeleton.dart';

/// Club Head request tracking: the full history of the user's own event
/// requests with the coordinator's decision comment on each status change.
class MyEventsScreen extends StatefulWidget {
  const MyEventsScreen({super.key});

  @override
  State<MyEventsScreen> createState() => _MyEventsScreenState();
}

class _MyEventsScreenState extends State<MyEventsScreen> {
  // Retained as the SSE fallback poll cadence. A tick only hits the network when
  // the cache TTL has elapsed (see [EventCache.my]); otherwise it is a no-op.
  static const _pollInterval = Duration(seconds: 20);

  bool _loading = true;
  String? _error;
  bool _stale = false;
  List<EventModel> _events = [];
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    // Render whatever survived the last session instantly — the spinner only
    // shows when there is genuinely nothing cached yet.
    final cached = EventCache.instance.peekMy();
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

  /// A mutation / SSE elsewhere patched the shared cache: adopt the new list
  /// instantly, then let [_refresh] reconcile membership if it went stale.
  void _onCacheChanged() {
    if (!mounted) return;
    final cached = EventCache.instance.peekMy();
    if (cached != null) {
      setState(() {
        _events = cached;
        _loading = false;
      });
    }
    _refresh();
  }

  /// Revalidate. [EventCache.my] skips the network while the cache is fresh, so
  /// this doubles as the polling guard. Cached content stays on screen on
  /// failure; a persistent offline gap surfaces a subtle staleness hint.
  Future<void> _refresh({bool force = false}) async {
    try {
      final events = await EventCache.instance.my(force: force);
      if (!mounted) return;
      setState(() {
        _events = events;
        _loading = false;
        _error = null;
        _stale = false;
      });
    } catch (e) {
      if (!mounted) return;
      final cached = EventCache.instance.peekMy();
      if (cached != null) {
        // Keep the last known list; only flag staleness once it is genuinely old.
        final at = EventCache.instance.fetchedAtMy();
        setState(() {
          _events = cached;
          _loading = false;
          _stale =
              at != null &&
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

  Future<void> _openDetail(EventModel event) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => EventDetailScreen(event: event, showStatus: true),
      ),
    );
    await _refresh(force: true);
  }

  @override
  Widget build(BuildContext context) {
    final title = AppLocalizations.get('myRequests');
    return Scaffold(
      body: ScrollConfiguration(
        behavior: ScrollConfiguration.of(
          context,
        ).copyWith(physics: const ClampingScrollPhysics()),
        child: NestedScrollView(
          headerSliverBuilder: (ctx, _) => [AppSliverAppBar(title: title)],
          body: _buildBody(context),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) {
      return const AppPanelSkeleton();
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

    if (_events.isEmpty) {
      return CustomScrollView(
        slivers: [
          SliverFillRemaining(
            hasScrollBody: false,
            child: Center(
              child: Padding(
                padding: AppSpacing.screenPadding,
                child: Text(AppLocalizations.get('noBookings')),
              ),
            ),
          ),
        ],
      );
    }

    return RefreshIndicator(
      onRefresh: () => _refresh(force: true),
      child: CustomScrollView(
        slivers: [
          if (_stale) const SliverToBoxAdapter(child: StaleBanner()),
          SliverPadding(
            padding: AppSpacing.screenPadding.copyWith(bottom: 108.0),
            sliver: SliverList(
              delegate: SliverChildBuilderDelegate((context, index) {
                final event = _events[index];
                return Padding(
                  key: ValueKey(event.id),
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: EventCard(
                    event: event,
                    alwaysShowStatus: true,
                    showCategory: false,
                    onTap: () => _openDetail(event),
                  ),
                );
              }, childCount: _events.length),
            ),
          ),
        ],
      ),
    );
  }
}
