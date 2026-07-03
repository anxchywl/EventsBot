import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../models/event_model.dart';
import '../events/event_detail_screen.dart';

/// Shared booking calendar for Club Heads.
///
/// Approved events block slots: every approved event is rendered on its date as
/// a booked location. Dates with no events are free. Tapping a day's "+" opens
/// the submit form pre-filled with that date so a Club Head can request a slot.
///
/// Data source: `GET /api/flutter/events` (approved events only) — no new
/// backend endpoint is assumed.
class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key});

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  static const _pollInterval = Duration(seconds: 20);

  bool _loading = true;
  String? _error;
  List<EventModel> _events = [];
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
      final events = await fetchApprovedEvents();
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

  Future<void> _refreshSilently() async {
    try {
      final events = await fetchApprovedEvents();
      if (!mounted) return;
      setState(() {
        _events = events;
        _error = null;
      });
    } catch (_) {}
  }

  DateTime? _parseDate(String iso) {
    try {
      final p = iso.split('-');
      return DateTime(int.parse(p[0]), int.parse(p[1]), int.parse(p[2]));
    } catch (_) {
      return null;
    }
  }

  TimeOfDay? _parseTime(String hhmm) {
    try {
      final p = hhmm.split(':');
      return TimeOfDay(hour: int.parse(p[0]), minute: int.parse(p[1]));
    } catch (_) {
      return null;
    }
  }

  List<AppCalendarEvent> _calendarEvents() {
    final result = <AppCalendarEvent>[];
    for (final e in _events) {
      final date = _parseDate(e.eventDate);
      if (date == null) continue;
      result.add(
        AppCalendarEvent(
          id: e.id.toString(),
          // The booked slot the calendar communicates is the location.
          title: e.location,
          subtitle: e.title,
          date: date,
          time: _parseTime(e.eventTime),
          color: AppColors.error, // booked
          metadata: e,
        ),
      );
    }
    return result;
  }

  Future<void> _openDetail(AppCalendarEvent event) async {
    final model = event.metadata;
    if (model is! EventModel) return;
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => EventDetailScreen(event: model)),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AppAppBar(title: 'Календарь'),
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

    // AppCalendar's outer column is mainAxisSize.max, so it needs a bounded
    // parent (the Scaffold body) rather than an unbounded scroll view.
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.df),
      child: AppCalendar(
        events: _calendarEvents(),
        headerLabel: 'БРОНИРОВАНИЯ',
        accentColor: AppColors.primary,
        emptyStateTitle: 'Свободно',
        emptyStateSubtitle: 'На этот день нет одобренных броней',
        onEventTap: _openDetail,
      ),
    );
  }
}
