import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../core/localization.dart';
import '../../core/realtime_updates.dart';
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
  StreamSubscription<RealtimeUpdate>? _updatesSub;

  // Work filters
  String _sort = 'date_asc';
  Set<String> _categories = {};
  Set<String> _locations = {};
  Set<String> _organizers = {};
  // When on, the queue is swapped for a rejected / needs-changes review view.
  // This also opts the backend fetch into returning rejected events.
  bool _showRejected = false;

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(_pollInterval, (_) => _refreshSilently());
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

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final pending = await fetchPendingEvents(includeRejected: _showRejected);
      if (!mounted) return;
      setState(() {
        _events = pending;
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
      final pending = await fetchPendingEvents(includeRejected: _showRejected);
      if (!mounted) return;
      setState(() {
        _events = pending;
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

  Future<void> _toggleRejected() async {
    setState(() => _showRejected = !_showRejected);
    await _refreshSilently();
  }

  List<EventModel> get _filtered {
    // In rejected view only rejected / needs-changes events are shown; the
    // default view keeps the full moderation queue.
    final source = _showRejected
        ? _events.where(
            (e) => e.status == 'rejected' || e.status == 'needs_changes',
          )
        : _events;
    final filtered = source.where((e) {
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
      title: AppLocalizations.get('sorting'),
      selectedValue: _sort,
      options: [
        _RequestPickerOption(
          label: AppLocalizations.get('byDateClosest'),
          value: 'date_asc',
        ),
        _RequestPickerOption(
          label: AppLocalizations.get('byDateFurthest'),
          value: 'date_desc',
        ),
        _RequestPickerOption(
          label: AppLocalizations.get('oldestFirst'),
          value: 'submitted_asc',
        ),
        _RequestPickerOption(
          label: AppLocalizations.get('newestFirst'),
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
    await _showRequestMultiPicker(
      context,
      title: AppLocalizations.get('category'),
      selectedValues: _categories,
      options: options,
      onChanged: (values) {
        if (!mounted) return;
        setState(() => _categories = values);
      },
    );
  }

  Future<void> _pickLocation() async {
    final options = _locationOptions;
    if (options.isEmpty) return;
    await _showRequestMultiPicker(
      context,
      title: AppLocalizations.get('location'),
      selectedValues: _locations,
      options: options,
      onChanged: (values) {
        if (!mounted) return;
        setState(() => _locations = values);
      },
    );
  }

  Future<void> _pickOrganizer() async {
    final options = _organizerOptions;
    if (options.isEmpty) return;
    await _showRequestMultiPicker(
      context,
      title: AppLocalizations.get('organizer'),
      selectedValues: _organizers,
      options: options,
      onChanged: (values) {
        if (!mounted) return;
        setState(() => _organizers = values);
      },
    );
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
      appBar: AppAppBar(title: AppLocalizations.get('requests')),
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

    final filtered = _filtered;

    // Hide sorting / filtering controls entirely when there is nothing under
    // review. The rejected view stays accessible while it is active so it can
    // be toggled back off even if it yields no results.
    final showFilters = _events.isNotEmpty || _showRejected;

    return Column(
      children: [
        if (showFilters) _filterBar(),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _refreshSilently,
            child: filtered.isEmpty
                ? CustomScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    slivers: [
                      SliverFillRemaining(
                        hasScrollBody: false,
                        child: Center(
                          child: Padding(
                            padding: AppSpacing.screenPadding,
                            child: Text(
                              _events.isEmpty
                                  ? AppLocalizations.get(
                                      'noRequestsUnderReview',
                                    )
                                  : AppLocalizations.get('nothingFound'),
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.bodyLarge
                                  ?.copyWith(color: AppColors.grey),
                            ),
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
      padding: const EdgeInsets.only(
        left: AppSpacing.df,
        right: AppSpacing.df,
        top: 0,
        bottom: AppSpacing.df,
      ),
      itemCount: itemCount,
      itemBuilder: (context, index) {
        int remaining = index;
        for (final group in groups) {
          if (remaining == 0) {
            return _RequestDateHeader(label: group.label, first: index == 0);
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
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: EventCard(
        event: event,
        hideStatus: true,
        showCategory: false,
        onTap: () => _openDetail(event),
      ),
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
            child: _DashSortChip(active: _sort != 'date_asc', onTap: _pickSort),
          ),
          const SizedBox(width: AppSpacing.sm),
          Center(
            child: _DashFilterChip(
              label: AppLocalizations.get('category'),
              count: _categories.length,
              active: _categories.isNotEmpty,
              onTap: _pickCategory,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Center(
            child: _DashFilterChip(
              label: AppLocalizations.get('location'),
              count: _locations.length,
              active: _locations.isNotEmpty,
              onTap: _pickLocation,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Center(
            child: _DashFilterChip(
              label: AppLocalizations.get('organizer'),
              count: _organizers.length,
              active: _organizers.isNotEmpty,
              onTap: _pickOrganizer,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Center(
            child: _DashIconFilterChip(
              icon: Icons.block_rounded,
              active: _showRejected,
              onTap: _toggleRejected,
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
    isScrollControlled: true,
    useSafeArea: false,
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
        bottom: false,
        child: Container(
          decoration: BoxDecoration(
            color: surface,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
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
              SizedBox(
                height: MediaQuery.of(context).padding.bottom + AppSpacing.df,
              ),
            ],
          ),
        ),
      );
    },
  );
}

Future<void> _showRequestMultiPicker(
  BuildContext context, {
  required String title,
  required Set<String> selectedValues,
  required List<String> options,
  required ValueChanged<Set<String>> onChanged,
}) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    useSafeArea: false,
    builder: (context) {
      return _RequestMultiPickerSheet(
        title: title,
        selectedValues: selectedValues,
        options: options,
        onChanged: onChanged,
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

class _RequestMultiPickerSheet extends StatefulWidget {
  const _RequestMultiPickerSheet({
    required this.title,
    required this.selectedValues,
    required this.options,
    required this.onChanged,
  });

  final String title;
  final Set<String> selectedValues;
  final List<String> options;
  final ValueChanged<Set<String>> onChanged;

  @override
  State<_RequestMultiPickerSheet> createState() =>
      _RequestMultiPickerSheetState();
}

class _RequestMultiPickerSheetState extends State<_RequestMultiPickerSheet> {
  late final Set<String> _selected = Set.from(widget.selectedValues);
  String _query = '';

  void _toggle(String value) {
    HapticFeedback.selectionClick();
    setState(() {
      if (_selected.contains(value)) {
        _selected.remove(value);
      } else {
        _selected.add(value);
      }
    });
    widget.onChanged(Set.from(_selected));
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final isLight = Theme.of(context).brightness == Brightness.light;
    final surface = isLight ? Colors.white : const Color(0xFF1C1C1E);
    final textPrimary = isLight ? AppColors.textPrimary : AppColors.white;
    final filtered = _query.isEmpty
        ? widget.options
        : widget.options
              .where((option) => option.toLowerCase().contains(_query))
              .toList();

    return AnimatedPadding(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOutCubic,
      padding: EdgeInsets.only(bottom: mq.viewInsets.bottom),
      child: Container(
        constraints: BoxConstraints(
          maxHeight: (mq.size.height - mq.viewInsets.bottom) * 0.72,
        ),
        decoration: BoxDecoration(
          color: surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
        ),
        child: SafeArea(
          top: false,
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
                    widget.title,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: textPrimary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.df),
                child: TextField(
                  onChanged: (value) {
                    setState(() => _query = value.trim().toLowerCase());
                  },
                  decoration: InputDecoration(
                    hintText: AppLocalizations.get('search'),
                    prefixIcon: Icon(
                      Icons.search,
                      size: 18,
                      color: AppColors.grey,
                    ),
                    filled: true,
                    fillColor: AppColors.fieldBackground,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.df,
                    0,
                    AppSpacing.df,
                    AppSpacing.df,
                  ),
                  child: Wrap(
                    spacing: AppSpacing.sm,
                    runSpacing: AppSpacing.sm,
                    children: [
                      for (final option in filtered)
                        _RequestSelectorChip(
                          label: option,
                          active: _selected.contains(option),
                          onTap: () => _toggle(option),
                        ),
                      if (filtered.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(
                            vertical: AppSpacing.lg,
                          ),
                          child: Center(
                            child: Text(
                              AppLocalizations.get('nothingFound'),
                              style: AppTextStyles.bodyMedium.copyWith(
                                color: AppColors.grey,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.df),
            ],
          ),
        ),
      ),
    );
  }
}

class _RequestSelectorChip extends StatelessWidget {
  const _RequestSelectorChip({
    required this.label,
    required this.active,
    required this.onTap,
  });

  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: active ? AppColors.primary : AppColors.fieldBackground,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          label,
          style: AppTextStyles.bodyMedium.copyWith(
            color: active ? Colors.white : AppColors.textPrimary,
            fontWeight: FontWeight.w600,
          ),
        ),
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

class _DashFilterChip extends StatelessWidget {
  const _DashFilterChip({
    required this.label,
    required this.count,
    required this.active,
    required this.onTap,
  });

  final String label;
  final int count;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.primary : AppColors.textSecondary;
    final bg = active ? AppColors.primaryLight : AppColors.fieldBackground;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        height: 36,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
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
            if (count > 0) ...[
              const SizedBox(width: 6),
              Container(
                height: 18,
                constraints: const BoxConstraints(minWidth: 18),
                alignment: Alignment.center,
                padding: const EdgeInsets.symmetric(horizontal: 5),
                decoration: BoxDecoration(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  '$count',
                  style: AppTextStyles.labelSmall.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    height: 1,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _DashSortChip extends StatelessWidget {
  const _DashSortChip({required this.active, required this.onTap});

  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.primary : AppColors.textSecondary;
    final bg = active ? AppColors.primaryLight : AppColors.fieldBackground;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Icon(Icons.swap_vert_rounded, size: 18, color: color),
      ),
    );
  }
}

/// Icon-only filter chip (no text label), styled to match [_DashFilterChip]'s
/// active / inactive colour logic. Used for the rejected review-view toggle.
class _DashIconFilterChip extends StatelessWidget {
  const _DashIconFilterChip({
    required this.icon,
    required this.active,
    required this.onTap,
  });

  final IconData icon;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.primary : AppColors.textSecondary;
    final bg = active ? AppColors.primaryLight : AppColors.fieldBackground;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Icon(icon, size: 18, color: color),
      ),
    );
  }
}
