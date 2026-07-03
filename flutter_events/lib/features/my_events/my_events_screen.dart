import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../models/event_model.dart';
import '../events/event_card.dart';
import '../events/event_detail_screen.dart';

/// Club Head request tracking: the full history of the user's own event
/// requests with the coordinator's decision comment on each status change.
///
/// Realtime note: the backend currently exposes no WebSocket, so near-realtime
/// updates are approximated by polling `GET /api/flutter/events/my` on an
/// interval while the screen is visible, plus pull-to-refresh. If a WS endpoint
/// is added later, swap [_pollInterval]/[_startPolling] for a socket subscription.
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

  @override
  void initState() {
    super.initState();
    _load();
    _startPolling();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
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
      MaterialPageRoute(builder: (_) => EventDetailScreen(event: event)),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AppAppBar(title: 'Мои заявки'),
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

    if (_events.isEmpty) {
      return Center(
        child: Padding(
          padding: AppSpacing.screenPadding,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [const Text('Нет заявок')],
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
          final note = event.moderationNote;
          // Show the coordinator's comment on every decided status, not just
          // "needs_changes" — approvals and rejections can carry context too.
          final showNote = note != null && note.trim().isNotEmpty;
          return Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                EventCard(
                  event: event,
                  alwaysShowStatus: true,
                  onTap: () => _openDetail(event),
                ),
                if (showNote) _coordinatorNote(event, note),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _coordinatorNote(EventModel event, String note) {
    final theme = Theme.of(context);
    final color = event.statusColor;
    return Container(
      margin: const EdgeInsets.only(top: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        border: Border(left: BorderSide(color: color, width: 4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Комментарий координатора',
            style: theme.textTheme.labelSmall?.copyWith(
              color: color,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(note, style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}
