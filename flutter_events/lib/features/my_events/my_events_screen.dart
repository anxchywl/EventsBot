import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../models/event_model.dart';
import '../events/event_card.dart';
import '../events/event_detail_screen.dart';
import '../submit/submit_screen.dart';

class MyEventsScreen extends StatefulWidget {
  const MyEventsScreen({super.key});

  @override
  State<MyEventsScreen> createState() => _MyEventsScreenState();
}

class _MyEventsScreenState extends State<MyEventsScreen> {
  bool _loading = true;
  String? _error;
  List<EventModel> _events = [];

  @override
  void initState() {
    super.initState();
    _load();
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

  Future<void> _openSubmit() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const SubmitScreen()),
    );
    await _load();
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
            children: [
              const Text('Нет заявок'),
              const SizedBox(height: AppSpacing.df),
              AppPrimaryButton(text: 'Подать заявку', onPressed: _openSubmit),
            ],
          ),
        ),
      );
    }

    return ListView.builder(
      padding: AppSpacing.screenPadding,
      itemCount: _events.length,
      itemBuilder: (context, index) {
        final event = _events[index];
        final showNote =
            event.status == 'needs_changes' && event.moderationNote != null;
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
              if (showNote) _moderationNote(event.moderationNote!),
            ],
          ),
        );
      },
    );
  }

  Widget _moderationNote(String note) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(top: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.warningLight,
        border: Border(left: BorderSide(color: AppColors.warning, width: 4)),
      ),
      child: Text(
        note,
        style: theme.textTheme.bodySmall,
      ),
    );
  }
}
