import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api_client.dart';
import '../../core/localization.dart';
import '../../models/category_model.dart';
import '../../models/event_model.dart';
import '../submit/submit_screen.dart';
import 'event_card.dart';
import 'event_detail_screen.dart';

// ── Sort options ──────────────────────────────────────────────────────────────

const _sortGroups = [
  (
    label: 'Time',
    options: [
      (value: 'time_asc', label: 'Nearest first'),
      (value: 'time_desc', label: 'Furthest first'),
    ],
  ),
  (
    label: 'Reminders',
    options: [
      (value: 'reminders_desc', label: 'Most reminders'),
      (value: 'reminders_asc', label: 'Least reminders'),
    ],
  ),
  (
    label: 'Participants',
    options: [
      (value: 'participants_desc', label: 'Most participants'),
      (value: 'participants_asc', label: 'Least participants'),
    ],
  ),
];

// ── Relevance ─────────────────────────────────────────────────────────────────

enum _Relevance { active, all, archived }

// ── Time of day ───────────────────────────────────────────────────────────────

const _timeOfDayOptions = [
  (value: 'morning', label: 'Morning', start: 5, end: 12),
  (value: 'afternoon', label: 'Afternoon', start: 12, end: 17),
  (value: 'evening', label: 'Evening', start: 17, end: 22),
  (value: 'night', label: 'Night', start: 22, end: 5),
];

// ─────────────────────────────────────────────────────────────────────────────

class EventsScreen extends StatefulWidget {
  const EventsScreen({super.key, this.initialCalendarMode = false});

  final bool initialCalendarMode;

  @override
  State<EventsScreen> createState() => _EventsScreenState();
}

class _EventsScreenState extends State<EventsScreen> {
  // Feature flag: the student-facing browse UX (global search, time-of-day /
  // category / organizer / location filters, favorites) belongs to the Telegram
  // Mini App and is hidden in the Flutter organizer app. The logic is kept intact
  // below so it can be re-enabled by flipping this flag. When false, only the
  // grouped, date-sorted event list renders and `_applyFilters` applies default
  // relevance/sort behaviour.
  bool get _browseUiEnabled => false;

  bool _loading = true;
  String? _error;
  late bool _calendarMode = widget.initialCalendarMode;
  DateTime _selectedCalendarDate = DateTime.now();

  List<EventModel> _events = [];
  List<CategoryModel> _categories = [];

  // Derived option lists from loaded events
  List<String> _organizerOptions = [];
  List<String> _locationOptions = [];

  final _searchController = TextEditingController();
  String _search = '';

  // Filters
  String _sort = 'time_asc';
  _Relevance _relevance = _Relevance.active;
  Set<String> _selectedCategories = {};
  Set<String> _selectedOrganizers = {};
  Set<String> _selectedLocations = {};
  Set<String> _selectedTimeOfDay = {};
  bool _favoritesOnly = false;
  Set<int> _favoriteIds = {};

  static const _kFavoritesKey = 'flutter_favorite_event_ids';

  List<({String label, List<EventModel> events})> _grouped = [];

  @override
  void initState() {
    super.initState();
    if (_browseUiEnabled) {
      _loadFavorites().then((_) => _load());
    } else {
      _load();
    }
  }

  Future<void> _loadFavorites() async {
    final prefs = await SharedPreferences.getInstance();
    final ids = prefs.getStringList(_kFavoritesKey) ?? [];
    setState(
      () => _favoriteIds = ids.map((s) => int.tryParse(s) ?? -1).toSet(),
    );
  }

  Future<void> _toggleFavorite(int eventId) async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      if (_favoriteIds.contains(eventId)) {
        _favoriteIds.remove(eventId);
      } else {
        _favoriteIds.add(eventId);
      }
    });
    await prefs.setStringList(
      _kFavoritesKey,
      _favoriteIds.map((id) => '$id').toList(),
    );
    _applyFilters();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final approved = await fetchApprovedEvents();
      final pending = await fetchPendingEvents();
      final categories = await fetchCategories();
      if (!mounted) return;
      final events = [...approved, ...pending];
      setState(() {
        _events = events;
        _categories = categories;
        _organizerOptions = events.map((e) => e.organizerName).toSet().toList()
          ..sort();
        _locationOptions = events.map((e) => e.location).toSet().toList()
          ..sort();
        _loading = false;
        _applyFilters();
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _applyFilters() {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final search = _search.trim().toLowerCase();

    var filtered = _events.where((e) {
      if (search.isNotEmpty &&
          !e.title.toLowerCase().contains(search) &&
          !e.description.toLowerCase().contains(search)) {
        return false;
      }
      if (_favoritesOnly && !_favoriteIds.contains(e.id)) {
        return false;
      }
      if (_selectedCategories.isNotEmpty &&
          !_selectedCategories.contains(e.category)) {
        return false;
      }
      if (_selectedOrganizers.isNotEmpty &&
          !_selectedOrganizers.contains(e.organizerName)) {
        return false;
      }
      if (_selectedLocations.isNotEmpty &&
          !_selectedLocations.contains(e.location)) {
        return false;
      }

      final date = _parseDate(e.eventDate);
      if (date != null) {
        final isPast = date.isBefore(today);
        if (_relevance == _Relevance.active && isPast) return false;
        if (_relevance == _Relevance.archived && !isPast) return false;
      }

      if (_selectedTimeOfDay.isNotEmpty) {
        final hour = _parseHour(e.eventTime);
        if (hour != null) {
          final matchesAny = _selectedTimeOfDay.any((tod) {
            final opt = _timeOfDayOptions.firstWhere((o) => o.value == tod);
            if (opt.start < opt.end) return hour >= opt.start && hour < opt.end;
            return hour >= opt.start || hour < opt.end;
          });
          if (!matchesAny) return false;
        }
      }

      return true;
    }).toList();

    // Sort
    filtered.sort((a, b) {
      final ta = _eventTimestamp(a);
      final tb = _eventTimestamp(b);
      return _sort == 'time_desc' ? tb.compareTo(ta) : ta.compareTo(tb);
    });

    // Group by date
    final groups = <String, List<EventModel>>{};
    for (final e in filtered) {
      groups.putIfAbsent(_formatDateLabel(e.eventDate), () => []).add(e);
    }
    _grouped = groups.entries
        .map((en) => (label: en.key, events: en.value))
        .toList();
  }

  DateTime? _parseDate(String iso) {
    try {
      final p = iso.split('-');
      return DateTime(int.parse(p[0]), int.parse(p[1]), int.parse(p[2]));
    } catch (_) {
      return null;
    }
  }

  int? _parseHour(String time) {
    try {
      return int.parse(time.split(':')[0]);
    } catch (_) {
      return null;
    }
  }

  TimeOfDay? _parseTime(String time) {
    try {
      final p = time.split(':');
      return TimeOfDay(hour: int.parse(p[0]), minute: int.parse(p[1]));
    } catch (_) {
      return null;
    }
  }

  int _eventTimestamp(EventModel e) {
    try {
      final p = e.eventDate.split('-');
      final d = DateTime(
        int.parse(p[0]),
        int.parse(p[1]),
        int.parse(p[2]),
        _parseHour(e.eventTime) ?? 0,
      );
      return d.millisecondsSinceEpoch;
    } catch (_) {
      return 0;
    }
  }

  String _formatDateLabel(String iso) {
    final d = _parseDate(iso);
    return d != null ? DateFormat('MMMM d, yyyy').format(d) : iso;
  }

  // ── Active filter count helpers ──────────────────────────────────────────

  bool get _sortActive => _sort != 'time_asc';
  bool get _relevanceActive => _relevance != _Relevance.active;

  String get _relevanceLabel {
    switch (_relevance) {
      case _Relevance.active:
        return 'Relevance';
      case _Relevance.all:
        return 'All';
      case _Relevance.archived:
        return 'Archived';
    }
  }

  String _multiLabel(String base, Set<String> sel) =>
      sel.isEmpty ? base : '$base (${sel.length})';

  // ── Bottom sheets ────────────────────────────────────────────────────────

  Future<void> _pickSort() async {
    HapticFeedback.selectionClick();
    await AppBottomSheet.show(
      context: context,
      title: 'Sorting',
      child: _SortSheet(
        current: _sort,
        onPick: (v) {
          setState(() {
            _sort = v;
            _applyFilters();
          });
        },
      ),
    );
  }

  Future<void> _pickRelevance() async {
    final result = await AppBottomSheet.showSelection<_Relevance>(
      context: context,
      title: 'Relevance',
      selectedValue: _relevance,
      options: const [
        AppBottomSheetOption(title: 'Active', value: _Relevance.active),
        AppBottomSheetOption(title: 'All', value: _Relevance.all),
        AppBottomSheetOption(title: 'Archived', value: _Relevance.archived),
      ],
    );
    if (result == null || !mounted) return;
    setState(() {
      _relevance = result;
      _applyFilters();
    });
  }

  Future<void> _pickCategories() async {
    final options = _categories.map((c) => c.name).toList();
    if (options.isEmpty) return;
    await _showMultiSelect(
      title: 'Categories',
      options: options,
      selected: _selectedCategories,
      onChanged: (v) => setState(() {
        _selectedCategories = v;
        _applyFilters();
      }),
      withSearch: true,
    );
  }

  Future<void> _pickOrganizers() async {
    if (_organizerOptions.isEmpty) return;
    await _showMultiSelect(
      title: 'Organizers',
      options: _organizerOptions,
      selected: _selectedOrganizers,
      onChanged: (v) => setState(() {
        _selectedOrganizers = v;
        _applyFilters();
      }),
      withSearch: true,
    );
  }

  Future<void> _pickLocations() async {
    if (_locationOptions.isEmpty) return;
    await _showMultiSelect(
      title: 'Locations',
      options: _locationOptions,
      selected: _selectedLocations,
      onChanged: (v) => setState(() {
        _selectedLocations = v;
        _applyFilters();
      }),
      withSearch: true,
    );
  }

  Future<void> _pickTimeOfDay() async {
    final options = _timeOfDayOptions.map((o) => o.label).toList();
    final valueByLabel = {for (final o in _timeOfDayOptions) o.label: o.value};
    final labelByValue = {for (final o in _timeOfDayOptions) o.value: o.label};
    final selectedLabels = _selectedTimeOfDay
        .map((v) => labelByValue[v] ?? v)
        .toSet();

    await _showMultiSelect(
      title: 'Time of day',
      options: options,
      selected: selectedLabels,
      onChanged: (v) => setState(() {
        _selectedTimeOfDay = v.map((l) => valueByLabel[l] ?? l).toSet();
        _applyFilters();
      }),
      withSearch: false,
    );
  }

  Future<void> _showMultiSelect({
    required String title,
    required List<String> options,
    required Set<String> selected,
    required ValueChanged<Set<String>> onChanged,
    required bool withSearch,
  }) {
    HapticFeedback.selectionClick();
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.48),
      enableDrag: true,
      builder: (_) => _MultiSelectSheet(
        title: title,
        options: options,
        selected: Set.from(selected),
        withSearch: withSearch,
        onChanged: onChanged,
      ),
    );
  }

  // ── Navigation ────────────────────────────────────────────────────────────

  Future<void> _openSubmit() async {
    final initialDate = _calendarMode ? _selectedCalendarDate : null;
    final submitted = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      useSafeArea: false,
      builder: (context) => SubmitScreen(initialDate: initialDate, asSheet: true),
    );
    if (submitted == true) {
      await _load(silent: true);
    }
  }

  Future<void> _openCalendarEvent(AppCalendarEvent event) async {
    final model = event.metadata;
    if (model is! EventModel) return;
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => EventDetailScreen(event: model)),
    );
    await _load(silent: true);
  }

  List<AppCalendarEvent> _calendarEvents() {
    final result = <AppCalendarEvent>[];
    for (final event in _events) {
      final date = _parseDate(event.eventDate);
      if (date == null) continue;
      result.add(
        AppCalendarEvent(
          id: event.id.toString(),
          title: event.location,
          subtitle: event.title,
          date: date,
          time: _parseTime(event.eventTime),
          endTime: event.eventEndTime != null ? _parseTime(event.eventEndTime!) : null,
          color: event.isPending ? AppColors.grey : AppColors.error,
          metadata: event,
        ),
      );
    }
    return result;
  }

  void _toggleCalendarMode() {
    HapticFeedback.selectionClick();
    setState(() => _calendarMode = !_calendarMode);
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppAppBar(
        title: _calendarMode ? 'Event Calendar' : 'Events',
        leading: IconButton(
          tooltip: _calendarMode ? 'Events' : 'Calendar',
          icon: AnimatedSwitcher(
            duration: const Duration(milliseconds: 240),
            transitionBuilder: (child, animation) {
              return RotationTransition(
                turns: Tween<double>(begin: -0.18, end: 0).animate(animation),
                child: ScaleTransition(scale: animation, child: child),
              );
            },
            child: Icon(
              _calendarMode
                  ? Icons.view_agenda_outlined
                  : Icons.calendar_month_outlined,
              key: ValueKey(_calendarMode),
            ),
          ),
          onPressed: _toggleCalendarMode,
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_outlined),
            onPressed: _openSubmit,
          ),
        ],
      ),
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
              AppSecondaryButton(text: 'Retry', onPressed: _load),
            ],
          ),
        ),
      );
    }

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 520),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      transitionBuilder: (child, animation) {
        return _WaveModeTransition(
          animation: animation,
          child: FadeTransition(opacity: animation, child: child),
        );
      },
      child: _calendarMode
          ? _CalendarModeView(
              key: const ValueKey('calendar'),
              events: _calendarEvents(),
              selectedDate: _selectedCalendarDate,
              onDateSelected: (date) {
                setState(() => _selectedCalendarDate = date);
              },
              onEventTap: _openCalendarEvent,
            )
          : _EventsListModeView(
              key: const ValueKey('events'),
              browseUiEnabled: _browseUiEnabled,
              searchController: _searchController,
              searchChanged: (value) => setState(() {
                _search = value;
                _applyFilters();
              }),
              clearSearch: () => setState(() {
                _search = '';
                _applyFilters();
              }),
              sortActive: _sortActive,
              relevanceLabel: _relevanceLabel,
              relevanceActive: _relevanceActive,
              selectedTimeOfDay: _selectedTimeOfDay,
              selectedCategories: _selectedCategories,
              selectedOrganizers: _selectedOrganizers,
              selectedLocations: _selectedLocations,
              favoritesOnly: _favoritesOnly,
              pickSort: _pickSort,
              pickRelevance: _pickRelevance,
              pickTimeOfDay: _pickTimeOfDay,
              pickCategories: _pickCategories,
              pickOrganizers: _pickOrganizers,
              pickLocations: _pickLocations,
              toggleFavoritesOnly: () => setState(() {
                _favoritesOnly = !_favoritesOnly;
                _applyFilters();
              }),
              grouped: _grouped,
              favoriteIds: _favoriteIds,
              multiLabel: _multiLabel,
              onToggleFavorite: _toggleFavorite,
            ),
    );
  }
}

// ── Sub-widgets ───────────────────────────────────────────────────────────────

class _EventsListModeView extends StatelessWidget {
  const _EventsListModeView({
    super.key,
    required this.browseUiEnabled,
    required this.searchController,
    required this.searchChanged,
    required this.clearSearch,
    required this.sortActive,
    required this.relevanceLabel,
    required this.relevanceActive,
    required this.selectedTimeOfDay,
    required this.selectedCategories,
    required this.selectedOrganizers,
    required this.selectedLocations,
    required this.favoritesOnly,
    required this.pickSort,
    required this.pickRelevance,
    required this.pickTimeOfDay,
    required this.pickCategories,
    required this.pickOrganizers,
    required this.pickLocations,
    required this.toggleFavoritesOnly,
    required this.grouped,
    required this.favoriteIds,
    required this.multiLabel,
    required this.onToggleFavorite,
  });

  final bool browseUiEnabled;
  final TextEditingController searchController;
  final ValueChanged<String> searchChanged;
  final VoidCallback clearSearch;
  final bool sortActive;
  final String relevanceLabel;
  final bool relevanceActive;
  final Set<String> selectedTimeOfDay;
  final Set<String> selectedCategories;
  final Set<String> selectedOrganizers;
  final Set<String> selectedLocations;
  final bool favoritesOnly;
  final VoidCallback pickSort;
  final VoidCallback pickRelevance;
  final VoidCallback pickTimeOfDay;
  final VoidCallback pickCategories;
  final VoidCallback pickOrganizers;
  final VoidCallback pickLocations;
  final VoidCallback toggleFavoritesOnly;
  final List<({String label, List<EventModel> events})> grouped;
  final Set<int> favoriteIds;
  final String Function(String base, Set<String> selected) multiLabel;
  final ValueChanged<int> onToggleFavorite;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (browseUiEnabled) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.df,
              AppSpacing.sm,
              AppSpacing.df,
              0,
            ),
            child: GlobalSearchBar(
              controller: searchController,
              hint: 'Search',
              onChanged: searchChanged,
              onClear: clearSearch,
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          SizedBox(
            height: 36,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: AppSpacing.screenHorizontal,
              children: [
                _SortButton(active: sortActive, onTap: pickSort),
                const SizedBox(width: AppSpacing.sm),
                _FilterChip(
                  label: relevanceLabel,
                  active: relevanceActive,
                  onTap: pickRelevance,
                ),
                const SizedBox(width: AppSpacing.sm),
                _FilterChip(
                  label: multiLabel('Time of day', selectedTimeOfDay),
                  active: selectedTimeOfDay.isNotEmpty,
                  onTap: pickTimeOfDay,
                ),
                const SizedBox(width: AppSpacing.sm),
                _FilterChip(
                  label: multiLabel('Categories', selectedCategories),
                  active: selectedCategories.isNotEmpty,
                  onTap: pickCategories,
                ),
                const SizedBox(width: AppSpacing.sm),
                _FilterChip(
                  label: multiLabel('Organizers', selectedOrganizers),
                  active: selectedOrganizers.isNotEmpty,
                  onTap: pickOrganizers,
                ),
                const SizedBox(width: AppSpacing.sm),
                _FilterChip(
                  label: multiLabel('Locations', selectedLocations),
                  active: selectedLocations.isNotEmpty,
                  onTap: pickLocations,
                ),
                const SizedBox(width: AppSpacing.sm),
                _FavoritesChip(
                  active: favoritesOnly,
                  onTap: toggleFavoritesOnly,
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
        ],
        Expanded(
          child: grouped.isEmpty
              ? Center(
                  child: Text(
                    'Nothing found',
                    style: Theme.of(
                      context,
                    ).textTheme.bodyLarge?.copyWith(color: AppColors.grey),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.only(
                    left: AppSpacing.df,
                    right: AppSpacing.df,
                    top: 0,
                    bottom: AppSpacing.df,
                  ),
                  itemCount: grouped.fold<int>(
                    0,
                    (sum, group) => sum + 1 + group.events.length,
                  ),
                  itemBuilder: (context, index) {
                    int remaining = index;
                    for (final group in grouped) {
                      if (remaining == 0) {
                        return _DateHeader(
                          label: group.label,
                          first: index == 0,
                        );
                      }
                      remaining--;
                      if (remaining < group.events.length) {
                        final event = group.events[remaining];
                        return Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: EventCard(
                            event: event,
                            mutedPending: event.isPending,
                            isFavorite:
                                browseUiEnabled &&
                                favoriteIds.contains(event.id),
                            onToggleFavorite: browseUiEnabled
                                ? () => onToggleFavorite(event.id)
                                : null,
                            onTap: () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => EventDetailScreen(event: event),
                              ),
                            ),
                          ),
                        );
                      }
                      remaining -= group.events.length;
                    }
                    return const SizedBox.shrink();
                  },
                ),
        ),
      ],
    );
  }
}

class _CalendarModeView extends StatelessWidget {
  const _CalendarModeView({
    super.key,
    required this.events,
    required this.selectedDate,
    required this.onDateSelected,
    required this.onEventTap,
  });

  final List<AppCalendarEvent> events;
  final DateTime selectedDate;
  final ValueChanged<DateTime> onDateSelected;
  final ValueChanged<AppCalendarEvent> onEventTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.df),
      child: AppCalendar(
        events: events,
        initialDate: selectedDate,
        showEventList: true,
        onDateSelected: onDateSelected,
        onEventTap: onEventTap,
        headerLabel: AppLocalizations.get('bookings'),
        accentColor: AppColors.primary,
        emptyStateTitle: AppLocalizations.get('available'),
        emptyStateSubtitle: AppLocalizations.get('noBookingsOrRequests'),
      ),
    );
  }
}

class _WaveModeTransition extends StatelessWidget {
  const _WaveModeTransition({required this.animation, required this.child});

  final Animation<double> animation;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, _) {
        return ClipPath(clipper: _WaveClipper(animation.value), child: child);
      },
    );
  }
}

class _WaveClipper extends CustomClipper<Path> {
  const _WaveClipper(this.progress);

  final double progress;

  @override
  Path getClip(Size size) {
    final eased = Curves.easeOutCubic.transform(progress.clamp(0, 1));
    final origin = Offset(size.width - 48, 0);
    final radius = size.longestSide * 1.35 * eased;
    return Path()..addOval(Rect.fromCircle(center: origin, radius: radius));
  }

  @override
  bool shouldReclip(_WaveClipper oldClipper) => oldClipper.progress != progress;
}

class _DateHeader extends StatelessWidget {
  const _DateHeader({required this.label, this.first = false});
  final String label;
  final bool first;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        top: first ? AppSpacing.sm : AppSpacing.df,
        bottom: AppSpacing.sm,
      ),
      child: Text(
        label,
        style: Theme.of(
          context,
        ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _SortButton extends StatelessWidget {
  const _SortButton({required this.active, required this.onTap});
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.primary : AppColors.textPrimary;
    final bg = active ? AppColors.primaryLight : AppColors.fieldBackground;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(20),
          border: active
              ? null
              : Border.all(
                  color: AppColors.primary.withValues(alpha: 0.18),
                  width: 1,
                ),
        ),
        child: Icon(Icons.swap_vert_rounded, size: 18, color: color),
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.active,
    required this.onTap,
  });
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.primary : AppColors.textPrimary;
    final bg = active ? AppColors.primaryLight : AppColors.fieldBackground;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(20),
          border: active
              ? null
              : Border.all(
                  color: AppColors.primary.withValues(alpha: 0.18),
                  width: 1,
                ),
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
            Icon(Icons.keyboard_arrow_down_rounded, size: 16, color: color),
          ],
        ),
      ),
    );
  }
}

class _FavoritesChip extends StatelessWidget {
  const _FavoritesChip({required this.active, required this.onTap});
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.error : AppColors.textPrimary;
    final bg = active
        ? AppColors.error.withValues(alpha: 0.12)
        : AppColors.fieldBackground;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(20),
          border: active
              ? null
              : Border.all(
                  color: AppColors.primary.withValues(alpha: 0.18),
                  width: 1,
                ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              active ? Icons.favorite_rounded : Icons.favorite_border_rounded,
              size: 15,
              color: color,
            ),
            const SizedBox(width: 4),
            Text(
              'Favorites',
              style: AppTextStyles.chip.copyWith(
                color: color,
                fontWeight: active ? FontWeight.w600 : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Sort bottom sheet ─────────────────────────────────────────────────────────

class _SortSheet extends StatefulWidget {
  const _SortSheet({required this.current, required this.onPick});
  final String current;
  final ValueChanged<String> onPick;

  @override
  State<_SortSheet> createState() => _SortSheetState();
}

class _SortSheetState extends State<_SortSheet> {
  late String _selected;

  @override
  void initState() {
    super.initState();
    _selected = widget.current;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;
    final textSub = isLight ? const Color(0xFF6B6B80) : const Color(0xFF8E8EA3);
    final divider = isLight
        ? Colors.black.withValues(alpha: 0.06)
        : Colors.white.withValues(alpha: 0.06);

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final group in _sortGroups) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 6),
            child: Text(
              group.label,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: textSub,
                letterSpacing: 0.3,
              ),
            ),
          ),
          for (int i = 0; i < group.options.length; i++) ...[
            _SortOption(
              label: group.options[i].label,
              value: group.options[i].value,
              selected: _selected == group.options[i].value,
              textColor: textPrimary,
              onTap: () {
                HapticFeedback.selectionClick();
                setState(() => _selected = group.options[i].value);
                widget.onPick(group.options[i].value);
                Navigator.of(context).pop();
              },
            ),
            if (i < group.options.length - 1)
              Divider(height: 1, indent: 20, endIndent: 20, color: divider),
          ],
        ],
        const SizedBox(height: 8),
      ],
    );
  }
}

class _SortOption extends StatefulWidget {
  const _SortOption({
    required this.label,
    required this.value,
    required this.selected,
    required this.textColor,
    required this.onTap,
  });
  final String label;
  final String value;
  final bool selected;
  final Color textColor;
  final VoidCallback onTap;

  @override
  State<_SortOption> createState() => _SortOptionState();
}

class _SortOptionState extends State<_SortOption> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final pressedColor = isLight
        ? Colors.black.withValues(alpha: 0.04)
        : Colors.white.withValues(alpha: 0.04);

    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 80),
        color: _pressed ? pressedColor : Colors.transparent,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 13),
        child: Row(
          children: [
            Expanded(
              child: Text(
                widget.label,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: widget.selected
                      ? FontWeight.w600
                      : FontWeight.w500,
                  color: widget.textColor,
                ),
              ),
            ),
            if (widget.selected)
              Icon(Icons.check_rounded, size: 18, color: AppColors.primary),
          ],
        ),
      ),
    );
  }
}

// ── Multi-select bottom sheet ─────────────────────────────────────────────────

class _MultiSelectSheet extends StatefulWidget {
  const _MultiSelectSheet({
    required this.title,
    required this.options,
    required this.selected,
    required this.withSearch,
    required this.onChanged,
  });
  final String title;
  final List<String> options;
  final Set<String> selected;
  final bool withSearch;
  final ValueChanged<Set<String>> onChanged;

  @override
  State<_MultiSelectSheet> createState() => _MultiSelectSheetState();
}

class _MultiSelectSheetState extends State<_MultiSelectSheet> {
  late Set<String> _selected;
  String _query = '';
  final _focusNode = FocusNode();
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    _selected = Set.from(widget.selected);
    _focusNode.addListener(() => setState(() => _focused = _focusNode.hasFocus));
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

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
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;

    final filtered = _query.isEmpty
        ? widget.options
        : widget.options
              .where((o) => o.toLowerCase().contains(_query))
              .toList();

    return AnimatedPadding(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOutCubic,
      padding: EdgeInsets.only(bottom: mq.viewInsets.bottom),
      child: Container(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        constraints: BoxConstraints(
          maxHeight: (mq.size.height - mq.viewInsets.bottom) * 0.7,
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Handle
              Center(
                child: Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Container(
                    width: 32,
                    height: 4,
                    decoration: BoxDecoration(
                      color: isLight
                          ? const Color(0xFFD1D1D6)
                          : const Color(0xFF48484A),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
              ),
              // Title
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 10, 20, 12),
                child: Text(
                  widget.title,
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -0.3,
                    color: textPrimary,
                    height: 1.2,
                  ),
                ),
              ),
              // Content
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (widget.withSearch) ...[
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 160),
                          decoration: BoxDecoration(
                            color: isLight
                                ? const Color(0xFFF2F2F7)
                                : const Color(0xFF2C2C2E),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: _focused
                                  ? AppColors.primary.withValues(alpha: 0.6)
                                  : Colors.transparent,
                              width: 1.5,
                            ),
                          ),
                          child: TextField(
                            focusNode: _focusNode,
                            onChanged: (v) =>
                                setState(() => _query = v.trim().toLowerCase()),
                            decoration: InputDecoration(
                              hintText: 'Search',
                              prefixIcon: Icon(
                                Icons.search,
                                size: 18,
                                color: _focused
                                    ? AppColors.primary
                                    : AppColors.grey,
                              ),
                              border: InputBorder.none,
                              contentPadding:
                                  const EdgeInsets.symmetric(vertical: 10),
                            ),
                            style: const TextStyle(fontSize: 15),
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: filtered.map((option) {
                          final active = _selected.contains(option);
                          return GestureDetector(
                            onTap: () => _toggle(option),
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 120),
                              padding: const EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 8,
                              ),
                              decoration: BoxDecoration(
                                color: active
                                    ? AppColors.primary
                                    : (isLight
                                          ? const Color(0xFFF2F2F7)
                                          : const Color(0xFF2C2C2E)),
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Text(
                                option,
                                style: TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500,
                                  color: active
                                      ? Colors.white
                                      : (isLight
                                            ? const Color(0xFF0A0A1A)
                                            : Colors.white),
                                ),
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                      if (filtered.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Center(
                            child: Text(
                              'Nothing found',
                              style:
                                  TextStyle(color: AppColors.grey, fontSize: 14),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              SizedBox(height: mq.padding.bottom + 8),
            ],
          ),
        ),
      ),
    );
  }
}
