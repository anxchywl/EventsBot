import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../models/event_model.dart';
import '../events/event_card.dart';
import '../events/event_detail_screen.dart';

/// University Coordinator dashboard: every incoming request awaiting a decision,
/// with work filters by club (organizer) and by date.
///
/// Data source: `GET /api/flutter/events/pending` (admin-only). Tapping a
/// request opens [EventDetailScreen], which already carries the full context
/// (IT needs, materials, location, organizer) and the approve / request-changes
/// / reject actions wired to `PATCH /events/{id}/status`. On approval the slot
/// auto-blocks in the shared calendar, since the calendar reads approved events.
///
/// Realtime note: no backend WebSocket exists, so new requests are picked up via
/// [_pollInterval] polling plus pull-to-refresh.
class CoordinatorDashboardScreen extends StatefulWidget {
  const CoordinatorDashboardScreen({super.key});

  @override
  State<CoordinatorDashboardScreen> createState() =>
      _CoordinatorDashboardScreenState();
}

class _CoordinatorDashboardScreenState
    extends State<CoordinatorDashboardScreen> {
  static const _pollInterval = Duration(seconds: 20);

  bool _loading = true;
  String? _error;
  List<EventModel> _events = [];
  Timer? _pollTimer;

  // Work filters
  String _sort = 'date_asc';
  Set<String> _categories = {};
  Set<String> _locations = {};
  Set<String> _organizers = {};

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
      final events = await fetchPendingEvents();
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
      final events = await fetchPendingEvents();
      if (!mounted) return;
      setState(() {
        _events = events;
        _error = null;
      });
    } catch (_) {
      // Keep last known list; next tick retries.
    }
  }

  List<String> get _categoryOptions =>
      (_events.map((e) => e.category).toSet().toList()..sort());

  List<String> get _locationOptions =>
      (_events.map((e) => e.location).toSet().toList()..sort());

  List<String> get _organizerOptions =>
      (_events.map((e) => e.organizerName).toSet().toList()..sort());

  bool get _sortByDate => _sort == 'date_asc' || _sort == 'date_desc';

  String get _sortLabel {
    switch (_sort) {
      case 'date_asc':
        return 'Ближайшие';
      case 'date_desc':
        return 'Дальние';
      case 'submitted_desc':
        return 'Новые заявки';
      default:
        return 'Старые заявки';
    }
  }

  List<EventModel> get _filtered {
    final filtered = _events.where((e) {
      if (_categories.isNotEmpty && !_categories.contains(e.category)) {
        return false;
      }
      if (_locations.isNotEmpty && !_locations.contains(e.location)) {
        return false;
      }
      if (_organizers.isNotEmpty && !_organizers.contains(e.organizerName)) {
        return false;
      }
      return true;
    }).toList();

    filtered.sort((a, b) {
      if (_sort == 'date_asc' || _sort == 'date_desc') {
        final compared = _eventTimestamp(a).compareTo(_eventTimestamp(b));
        return _sort == 'date_desc' ? -compared : compared;
      }
      final compared = a.id.compareTo(b.id);
      return _sort == 'submitted_desc' ? -compared : compared;
    });

    return filtered;
  }

  List<({String date, String label, List<EventModel> events})> _dateGroups(
    List<EventModel> events,
  ) {
    final groups = <String, List<EventModel>>{};
    for (final event in events) {
      groups.putIfAbsent(event.eventDate, () => []).add(event);
    }
    final entries = groups.entries.toList()
      ..sort((a, b) {
        final compared = a.key.compareTo(b.key);
        return _sort == 'date_desc' ? -compared : compared;
      });
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

  Future<void> _pickSort() async {
    final result = await _showRequestPicker<String>(
      context,
      title: 'Сортировка',
      selectedValue: _sort,
      options: const [
        _RequestPickerOption(
          label: 'По дате: сначала ближайшие',
          value: 'date_asc',
        ),
        _RequestPickerOption(
          label: 'По дате: сначала дальние',
          value: 'date_desc',
        ),
        _RequestPickerOption(
          label: 'Сначала первые заявки',
          value: 'submitted_asc',
        ),
        _RequestPickerOption(
          label: 'Сначала последние заявки',
          value: 'submitted_desc',
        ),
      ],
    );
    if (result == null || !mounted) return;
    setState(() => _sort = result);
  }

  Future<void> _pickCategory() async {
    final options = _categoryOptions;
    if (options.isEmpty) return;
    final result = await _showRequestMultiPicker(
      context,
      title: 'Категория',
      selectedValues: _categories,
      options: options,
    );
    if (result == null || !mounted) return;
    setState(() => _categories = result);
  }

  Future<void> _pickLocation() async {
    final options = _locationOptions;
    if (options.isEmpty) return;
    final result = await _showRequestMultiPicker(
      context,
      title: 'Локация',
      selectedValues: _locations,
      options: options,
    );
    if (result == null || !mounted) return;
    setState(() => _locations = result);
  }

  Future<void> _pickOrganizer() async {
    final options = _organizerOptions;
    if (options.isEmpty) return;
    final result = await _showRequestMultiPicker(
      context,
      title: 'Организатор',
      selectedValues: _organizers,
      options: options,
    );
    if (result == null || !mounted) return;
    setState(() => _organizers = result);
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
      appBar: const AppAppBar(title: 'Заявки'),
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

    final filtered = _filtered;

    return Column(
      children: [
        _filterBar(),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _refreshSilently,
            child: filtered.isEmpty
                ? ListView(
                    // ListView keeps pull-to-refresh working even when empty.
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 80),
                        child: Center(
                          child: Text(
                            _events.isEmpty
                                ? 'Нет заявок на рассмотрении'
                                : 'Ничего не найдено',
                            style: Theme.of(context).textTheme.bodyLarge
                                ?.copyWith(color: AppColors.grey),
                          ),
                        ),
                      ),
                    ],
                  )
                : _sortByDate
                ? _dateGroupedList(filtered)
                : _queueList(filtered),
          ),
        ),
      ],
    );
  }

  Widget _dateGroupedList(List<EventModel> events) {
    final groups = _dateGroups(events);
    final itemCount = groups.fold<int>(
      0,
      (sum, group) => sum + 1 + group.events.length,
    );
    return ListView.builder(
      padding: AppSpacing.screenPadding,
      itemCount: itemCount,
      itemBuilder: (context, index) {
        int remaining = index;
        for (final group in groups) {
          if (remaining == 0) {
            return _RequestDateHeader(label: group.label);
          }
          remaining--;
          if (remaining < group.events.length) {
            final event = group.events[remaining];
            return _requestCard(event);
          }
          remaining -= group.events.length;
        }
        return const SizedBox.shrink();
      },
    );
  }

  Widget _queueList(List<EventModel> events) {
    return ListView.builder(
      padding: AppSpacing.screenPadding,
      itemCount: events.length,
      itemBuilder: (context, index) {
        final event = events[index];
        return _requestCard(event);
      },
    );
  }

  Widget _requestCard(EventModel event) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: EventCard(event: event, onTap: () => _openDetail(event)),
    );
  }

  Widget _filterBar() {
    return SizedBox(
      height: 36 + AppSpacing.sm * 2,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: AppSpacing.screenHorizontal,
        children: [
          const SizedBox(width: 0),
          Center(
            child: _DashSortChip(
              active: _sort != 'date_asc',
              onTap: _pickSort,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Center(
            child: _DashFilterChip(
              label: 'Категория',
              count: _categories.length,
              active: _categories.isNotEmpty,
              onTap: _pickCategory,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Center(
            child: _DashFilterChip(
              label: 'Локация',
              count: _locations.length,
              active: _locations.isNotEmpty,
              onTap: _pickLocation,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Center(
            child: _DashFilterChip(
              label: 'Организатор',
              count: _organizers.length,
              active: _organizers.isNotEmpty,
              onTap: _pickOrganizer,
            ),
          ),
        ],
      ),
    );
  }
}

class _RequestPickerOption<T> {
  const _RequestPickerOption({required this.label, required this.value});

  final String label;
  final T value;
}

Future<T?> _showRequestPicker<T>(
  BuildContext context, {
  required String title,
  required T selectedValue,
  required List<_RequestPickerOption<T>> options,
}) {
  return showModalBottomSheet<T>(
    context: context,
    backgroundColor: Colors.transparent,
    builder: (context) {
      final isLight = Theme.of(context).brightness == Brightness.light;
      final surface = isLight ? Colors.white : const Color(0xFF1C1C1E);
      final textPrimary = isLight ? AppColors.textPrimary : AppColors.white;
      final selectedBg = AppColors.primary.withValues(alpha: 0.10);
      final divider = isLight
          ? Colors.black.withValues(alpha: 0.06)
          : Colors.white.withValues(alpha: 0.08);

      return SafeArea(
        top: false,
        child: Container(
          margin: const EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: surface,
            borderRadius: BorderRadius.circular(22),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: AppSpacing.sm),
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.grey.withValues(alpha: 0.35),
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 12),
                child: Center(
                  child: Text(
                    title,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: textPrimary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              for (var i = 0; i < options.length; i++) ...[
                _RequestPickerTile<T>(
                  option: options[i],
                  selected: options[i].value == selectedValue,
                  selectedBg: selectedBg,
                  textPrimary: textPrimary,
                ),
                if (i < options.length - 1)
                  Divider(height: 1, indent: 20, endIndent: 20, color: divider),
              ],
              const SizedBox(height: AppSpacing.sm),
            ],
          ),
        ),
      );
    },
  );
}

class _RequestPickerTile<T> extends StatelessWidget {
  const _RequestPickerTile({
    required this.option,
    required this.selected,
    required this.selectedBg,
    required this.textPrimary,
  });

  final _RequestPickerOption<T> option;
  final bool selected;
  final Color selectedBg;
  final Color textPrimary;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? selectedBg : Colors.transparent,
      child: InkWell(
        onTap: () {
          HapticFeedback.selectionClick();
          Navigator.of(context).pop(option.value);
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.md,
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  option.label,
                  style: AppTextStyles.bodyMedium.copyWith(
                    color: selected ? AppColors.primary : textPrimary,
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
              ),
              if (selected)
                const Icon(
                  Icons.check_rounded,
                  size: 19,
                  color: AppColors.primary,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RequestDateHeader extends StatelessWidget {
  const _RequestDateHeader({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.df, bottom: AppSpacing.sm),
      child: Text(
        label,
        style: Theme.of(
          context,
        ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _DashFilterChip extends StatelessWidget {
  const _DashFilterChip({
    required this.label,
    required this.active,
    required this.onTap,
    this.onClear,
  });

  final String label;
  final bool active;
  final VoidCallback onTap;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.primary : AppColors.textSecondary;
    final bg = active ? AppColors.primaryLight : AppColors.fieldBackground;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: AppTextStyles.chip.copyWith(
                color: color,
                fontWeight: active ? FontWeight.w600 : FontWeight.w500,
              ),
            ),
            const SizedBox(width: 4),
            GestureDetector(
              onTap: active ? onClear : onTap,
              child: Icon(
                active
                    ? Icons.close_rounded
                    : Icons.keyboard_arrow_down_rounded,
                size: 16,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
