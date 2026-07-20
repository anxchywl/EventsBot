import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/exceptions.dart';
import '../../core/localization.dart';
import '../../core/realtime_updates.dart';
import '../../models/event_model.dart';
import '../events/event_detail_screen.dart';
import '../shared/loading_skeleton.dart';

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
  StreamSubscription<RealtimeUpdate>? _updatesSub;
  DateTime _selectedDate = DateTime.now();

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(_pollInterval, (_) => _loadSilently());
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
      unawaited(_loadSilently());
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final approved = await fetchApprovedEvents();
      final pending = await fetchPendingEvents();
      if (!mounted) return;
      setState(() {
        _events = [...approved, ...pending];
        _error = null;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = AppLocalizations.get('somethingWentWrong');
        _loading = false;
      });
    }
  }

  Future<void> _loadSilently() async {
    try {
      final approved = await fetchApprovedEvents();
      final pending = await fetchPendingEvents();
      if (!mounted) return;
      setState(() {
        _events = [...approved, ...pending];
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
          title: e.title,
          subtitle: e.location,
          date: date,
          time: _parseTime(e.eventTime),
          endTime: e.eventEndTime != null ? _parseTime(e.eventEndTime!) : null,
          color: e.isPending ? AppColors.grey : AppColors.primary,
          metadata: e,
        ),
      );
    }
    return result;
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
      appBar: AppAppBar(title: AppLocalizations.get('calendar')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const AppPanelSkeleton(cards: 3);
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

    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.df),
        child: AppCalendar(
          events: _calendarEvents(),
          initialDate: _selectedDate,
          showEventList: true,
          showTodayButton: true,
          todayLabel: AppLocalizations.get('today'),
          todayButtonLabel: AppLocalizations.get('today'),
          onDateSelected: (date) {
            setState(() {
              _selectedDate = date;
            });
          },
          onEventTap: (event) {
            final model = event.metadata;
            if (model is EventModel) {
              _openDetail(model);
            }
          },
          accentColor: AppColors.primary,
          emptyStateTitle: AppLocalizations.get('noEventsForDay'),
        ),
      ),
    );
  }
}
