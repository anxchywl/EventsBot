import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/localization.dart';
import '../../core/realtime_updates.dart';
import '../../models/event_model.dart';
import '../events/event_card.dart';
import '../events/event_detail_screen.dart';

/// Club Head request tracking: the full history of the user's own event
/// requests with the coordinator's decision comment on each status change.
class MyEventsScreen extends StatefulWidget {
  const MyEventsScreen({super.key});

  @override
  State<MyEventsScreen> createState() => _MyEventsScreenState();
}

class _MyEventsScreenState extends State<MyEventsScreen> {
  static const _pollInterval = Duration(seconds: 20);

  bool _loading = true;
  String? _error;
  List<EventModel> _events = [];
  Timer? _pollTimer;
  StreamSubscription<RealtimeUpdate>? _updatesSub;

  @override
  void initState() {
    super.initState();
    _load();
    _startPolling();
    _updatesSub = RealtimeUpdates.instance.stream.listen(_handleRealtimeUpdate);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _updatesSub?.cancel();
    super.dispose();
  }

  void _handleRealtimeUpdate(RealtimeUpdate update) {
    if (update.type == 'event_status_changed') {
      unawaited(_refreshSilently());
    }
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(_pollInterval, (_) => _refreshSilently());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final events = await fetchMyEvents();
      if (!mounted) return;
      setState(() {
        _events = events;
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

  /// Background refresh (polling / pull-to-refresh) that never shows the
  /// full-screen loader and leaves existing content in place on error.
  Future<void> _refreshSilently() async {
    try {
      final events = await fetchMyEvents();
      if (!mounted) return;
      setState(() {
        _events = events;
        _error = null;
      });
    } catch (_) {
      // Keep showing the last known list; the next tick will retry.
    }
  }

  Future<void> _openDetail(EventModel event) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => EventDetailScreen(event: event, showStatus: true),
      ),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppAppBar(title: AppLocalizations.get('myRequests')),
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

    if (_events.isEmpty) {
      return Center(
        child: Padding(
          padding: AppSpacing.screenPadding,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [Text(AppLocalizations.get('noBookings'))],
          ),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _refreshSilently,
      child: ListView.builder(
        padding: AppSpacing.screenPadding,
        itemCount: _events.length,
        itemBuilder: (context, index) {
          final event = _events[index];
          return Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: EventCard(
              event: event,
              alwaysShowStatus: true,
              showCategory: false,
              onTap: () => _openDetail(event),
            ),
          );
        },
      ),
    );
  }
}
