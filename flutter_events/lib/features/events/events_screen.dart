import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../core/auth_store.dart';
import '../../core/cache_store.dart';
import '../../core/localization.dart';
import '../../models/category_model.dart';
import '../../models/event_model.dart';
import '../submit/submit_screen.dart';
import '../shared/loading_skeleton.dart';
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
];

// ── Relevance ─────────────────────────────────────────────────────────────────

enum _Relevance { active, all, archived }

// ─────────────────────────────────────────────────────────────────────────────

String _sanitizeSearchInput(String input) {
  return input
      .trim()
      .replaceAll("'", "")
      .replaceAll('"', "")
      .replaceAll(';', "")
      .replaceAll('--', "")
      .replaceAll('/*', "")
      .replaceAll('*/', "");
}

class SanitizingFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    String text = newValue.text;
    if (text.startsWith(' ')) {
      text = text.trimLeft();
    }
    text = text.replaceAll(RegExp(r'\s{2,}'), ' ');
    text = text
        .replaceAll("'", "")
        .replaceAll('"', "")
        .replaceAll(';', "")
        .replaceAll('--', "")
        .replaceAll('/*', "")
        .replaceAll('*/', "");

    int selectionIndex =
        newValue.selection.end - (newValue.text.length - text.length);
    if (selectionIndex < 0) selectionIndex = 0;
    if (selectionIndex > text.length) selectionIndex = text.length;

    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: selectionIndex),
    );
  }
}

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
  bool get _browseUiEnabled => true;

  bool _loading = true;
  String? _error;
  late bool _calendarMode = widget.initialCalendarMode;
  DateTime _selectedCalendarDate = DateTime.now();

  // Bumped whenever a search should reposition the calendar. AppCalendar reads
  // its target date only in initState, so changing this nonce (used as its key)
  // remounts it onto [_selectedCalendarDate] — navigating to that month and
  // marking the matched day.
  int _calendarJumpNonce = 0;

  List<EventModel> _events = [];
  List<CategoryModel> _categories = [];

  // Derived option lists from loaded events
  List<String> _organizerOptions = [];
  List<String> _locationOptions = [];

  final _searchController = TextEditingController();
  String _search = '';

  bool _searchOpen = false;

  // Filters
  String _sort = 'time_asc';
  _Relevance _relevance = _Relevance.active;
  Set<String> _selectedCategories = {};
  Set<String> _selectedOrganizers = {};
  Set<String> _selectedLocations = {};

  List<({String label, List<EventModel> events})> _grouped = [];

  // Single source of truth for the active search + filter result, shared by the
  // list (grouped) and calendar views. Rebuilt by [_applyFilters].
  List<EventModel> _filteredEvents = [];

  @override
  void initState() {
    super.initState();
    // Render from cache instantly (survives restart); the spinner shows only
    // when nothing has been fetched yet this install.
    _adoptCache();
    _loading =
        EventCache.instance.peekApproved() == null &&
        EventCache.instance.peekPending() == null;
    EventCache.instance.addListener(_onCacheChanged);
    _refresh();
  }

  /// Pull the latest cached approved + pending events and categories into local
  /// state, rebuilding the derived option lists and grouped view.
  void _adoptCache() {
    final approved = EventCache.instance.peekApproved() ?? const [];
    final pending = EventCache.instance.peekPending() ?? const [];
    final categories = EventCache.instance.peekCategories();
    final events = [...approved, ...pending];
    _events = events;
    if (categories != null) _categories = categories;
    _organizerOptions = events.map((e) => e.organizerName).toSet().toList()
      ..sort();
    _locationOptions = events.map((e) => e.location).toSet().toList()..sort();
    _applyFilters();
  }

  void _onCacheChanged() {
    if (!mounted) return;
    setState(() {
      _adoptCache();
      _loading = false;
    });
    _refresh();
  }

  @override
  void dispose() {
    EventCache.instance.removeListener(_onCacheChanged);
    _searchController.dispose();
    super.dispose();
  }

  /// Revalidate approved + pending + categories. Each call is stale-while-
  /// revalidate: fresh cache entries skip the network. Cached content stays on
  /// screen if the fetch fails; the error state shows only when nothing is
  /// cached at all.
  Future<void> _refresh({bool force = false}) async {
    try {
      await Future.wait([
        EventCache.instance.approved(force: force),
        EventCache.instance.pending(force: force),
        EventCache.instance.categories(force: force),
      ]);
      if (!mounted) return;
      setState(() {
        _adoptCache();
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      final hasCache =
          EventCache.instance.peekApproved() != null ||
          EventCache.instance.peekPending() != null;
      setState(() {
        _loading = false;
        if (hasCache) {
          _adoptCache();
        } else {
          _error = e.toString();
        }
      });
    }
  }

  void _applyFilters() {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final search = _sanitizeSearchInput(_search).toLowerCase();

    var filtered = _events.where((e) {
      if (search.isNotEmpty &&
          !e.title.toLowerCase().contains(search) &&
          !e.description.toLowerCase().contains(search) &&
          !e.organizerName.toLowerCase().contains(search) &&
          !e.category.toLowerCase().contains(search) &&
          !e.location.toLowerCase().contains(search)) {
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

      return true;
    }).toList();

    // Sort
    filtered.sort((a, b) {
      final ta = _eventTimestamp(a);
      final tb = _eventTimestamp(b);
      return _sort == 'time_desc' ? tb.compareTo(ta) : ta.compareTo(tb);
    });

    // Shared filtered set — both the calendar and the grouped list derive from
    // this, so there is a single filtering pass.
    _filteredEvents = filtered;

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

  /// True when any search or filter deviates from the default state. Drives the
  /// visibility of the "Clear All" pill.
  bool get _anyFilterActive =>
      _search.trim().isNotEmpty ||
      _selectedCategories.isNotEmpty ||
      _selectedOrganizers.isNotEmpty ||
      _selectedLocations.isNotEmpty ||
      _relevance != _Relevance.active ||
      _sort != 'time_asc';

  void _clearAllFilters() {
    HapticFeedback.selectionClick();
    setState(() {
      _search = '';
      _searchController.clear();
      _searchOpen = false;
      _selectedCategories = {};
      _selectedOrganizers = {};
      _selectedLocations = {};
      _relevance = _Relevance.active;
      _sort = 'time_asc';
      _applyFilters();
    });
  }

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
      backgroundColor: AppColors.transparent,
      barrierColor: AppColors.black.withValues(alpha: 0.48),
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
      backgroundColor: AppColors.transparent,
      isScrollControlled: true,
      useSafeArea: false,
      builder: (context) =>
          SubmitScreen(initialDate: initialDate, asSheet: true),
    );
    if (submitted == true) {
      await _refresh(force: true);
    }
  }

  Future<void> _openCalendarEvent(AppCalendarEvent event) async {
    final model = event.metadata;
    if (model is! EventModel) return;
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => EventDetailScreen(event: model)),
    );
    await _refresh(force: true);
  }

  /// Move the calendar to the first matching event so a search in calendar mode
  /// opens the right month and marks the day. No-op when nothing matches, so the
  /// calendar stays put on an empty search result.
  void _jumpCalendarToFirstMatch() {
    for (final e in _filteredEvents) {
      final date = _parseDate(e.eventDate);
      if (date != null) {
        _selectedCalendarDate = date;
        _calendarJumpNonce++;
        break;
      }
    }
  }

  List<AppCalendarEvent> _calendarEvents(List<EventModel> events) {
    final result = <AppCalendarEvent>[];
    for (final event in events) {
      final date = _parseDate(event.eventDate);
      if (date == null) continue;
      result.add(
        AppCalendarEvent(
          id: event.id.toString(),
          title: event.title,
          subtitle: event.location,
          date: date,
          time: _parseTime(event.eventTime),
          endTime: event.eventEndTime != null
              ? _parseTime(event.eventEndTime!)
              : null,
          color: event.isPending ? AppColors.grey : AppColors.primary,
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
      resizeToAvoidBottomInset: false,
      // ClampingScrollPhysics avoids the stretch overscroll indicator, which
      // throws a benign "Build scheduled during frame" assertion when it
      // interacts with NestedScrollView's inner/outer scroll coordination.
      body: ScrollConfiguration(
        behavior: ScrollConfiguration.of(
          context,
        ).copyWith(physics: const ClampingScrollPhysics()),
        child: NestedScrollView(
          headerSliverBuilder: (context2, _) => [
            AppSliverAppBar(
              title: _calendarMode ? 'Events Calendar' : 'Events',
              leading: IconButton(
                tooltip: _calendarMode ? 'Events' : 'Calendar',
                icon: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 240),
                  transitionBuilder: (child, animation) {
                    return RotationTransition(
                      turns: Tween<double>(
                        begin: -0.18,
                        end: 0,
                      ).animate(animation),
                      child: ScaleTransition(scale: animation, child: child),
                    );
                  },
                  child: AppIcon(
                    _calendarMode
                        ? AppIcons.assignment
                        : AppIcons.calendarMonth,
                    key: ValueKey(_calendarMode),
                  ),
                ),
                onPressed: _toggleCalendarMode,
              ),
              actions: [
                IconButton(
                  tooltip: 'Submit event',
                  icon: const AppIcon(AppIcons.add),
                  onPressed: _openSubmit,
                ),
              ],
            ),
            if (_browseUiEnabled)
              SliverToBoxAdapter(child: _buildFilterStrip()),
          ],
          body: _buildBody(),
        ),
      ),
    );
  }

  Widget _buildBody() {
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
                      text: 'Retry',
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

    // The filter/search strip is now in the headerSliverBuilder so it scrolls
    // away along with the app bar. Only the pills that make sense per mode
    // are shown.
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 260),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      child: _calendarMode
          ? _CalendarModeView(
              key: const ValueKey('calendar'),
              events: _calendarEvents(_filteredEvents),
              selectedDate: _selectedCalendarDate,
              jumpNonce: _calendarJumpNonce,
              onDateSelected: (date) {
                setState(() => _selectedCalendarDate = date);
              },
              onEventTap: _openCalendarEvent,
            )
          : _EventsListModeView(
              key: const ValueKey('events'),
              grouped: _grouped,
            ),
    );
  }

  /// The horizontal filter/search strip shared by both view modes. In calendar
  /// mode the sort pill is omitted because the calendar orders by date itself.
  Widget _buildFilterStrip() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.df,
        AppSpacing.sm,
        AppSpacing.df,
        AppSpacing.sm,
      ),
      child: AnimatedCrossFade(
        duration: const Duration(milliseconds: 220),
        sizeCurve: Curves.easeInOut,
        firstCurve: Curves.easeOut,
        secondCurve: Curves.easeIn,
        crossFadeState: _searchOpen
            ? CrossFadeState.showSecond
            : CrossFadeState.showFirst,
        firstChild: SizedBox(
          height: 40,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.zero,
            children: [
              Tooltip(
                message: AppLocalizations.get('search'),
                child: _EventFilterPill(
                  icon: AppIcons.search,
                  onTap: () => setState(() => _searchOpen = true),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              if (!_calendarMode) ...[
                Tooltip(
                  message: AppLocalizations.get('sorting'),
                  child: _EventFilterPill(
                    icon: AppIcons.sort,
                    highlighted: _sortActive,
                    onTap: _pickSort,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
              ],
              _EventFilterPill(
                label: _relevanceLabel,
                highlighted: _relevanceActive,
                onTap: _pickRelevance,
              ),
              const SizedBox(width: AppSpacing.sm),
              _EventFilterPill(
                label: _multiLabel('Categories', _selectedCategories),
                highlighted: _selectedCategories.isNotEmpty,
                onTap: _pickCategories,
              ),
              const SizedBox(width: AppSpacing.sm),
              _EventFilterPill(
                label: _multiLabel('Organizers', _selectedOrganizers),
                highlighted: _selectedOrganizers.isNotEmpty,
                onTap: _pickOrganizers,
              ),
              const SizedBox(width: AppSpacing.sm),
              _EventFilterPill(
                label: _multiLabel('Locations', _selectedLocations),
                highlighted: _selectedLocations.isNotEmpty,
                onTap: _pickLocations,
              ),
              if (_anyFilterActive) ...[
                const SizedBox(width: AppSpacing.sm),
                _EventFilterPill(
                  icon: AppIcons.close,
                  label: 'Clear All',
                  highlighted: true,
                  onTap: _clearAllFilters,
                ),
              ],
            ],
          ),
        ),
        secondChild: _SearchBar(
          controller: _searchController,
          onChanged: (value) => setState(() {
            _search = value;
            _applyFilters();
            if (_calendarMode) _jumpCalendarToFirstMatch();
          }),
          onClose: () => setState(() {
            _searchOpen = false;
            _search = '';
            _searchController.clear();
            _applyFilters();
          }),
          autoFocus: _searchOpen,
        ),
      ),
    );
  }
}

// ── Sub-widgets ───────────────────────────────────────────────────────────────

class _EventsListModeView extends StatelessWidget {
  const _EventsListModeView({super.key, required this.grouped});

  final List<({String label, List<EventModel> events})> grouped;

  @override
  Widget build(BuildContext context) {
    final listSliver = grouped.isEmpty
        ? SliverFillRemaining(
            hasScrollBody: false,
            child: Center(
              child: Text(
                'Nothing found',
                style: Theme.of(
                  context,
                ).textTheme.bodyLarge?.copyWith(color: AppColors.grey),
              ),
            ),
          )
        : SliverPadding(
            padding: const EdgeInsets.only(
              left: AppSpacing.df,
              right: AppSpacing.df,
              bottom: 108.0,
            ),
            sliver: SliverList(
              delegate: SliverChildBuilderDelegate(
                (context, index) {
                  int remaining = index;
                  for (final group in grouped) {
                    if (remaining == 0) {
                      return _DateHeader(label: group.label, first: index == 0);
                    }
                    remaining--;
                    if (remaining < group.events.length) {
                      final event = group.events[remaining];
                      return Padding(
                        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                        child: EventCard(
                          event: event,
                          mutedPending: event.isPending,
                          showCategory: false,
                          statusLabelOverride:
                              !AuthStore.isAdmin && event.isNeedsChanges
                              ? AppLocalizations.get('pendingLabel')
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
                childCount: grouped.fold<int>(
                  0,
                  (sum, group) => sum + 1 + group.events.length,
                ),
              ),
            ),
          );

    return CustomScrollView(slivers: [listSliver]);
  }
}

class _CalendarModeView extends StatelessWidget {
  const _CalendarModeView({
    super.key,
    required this.events,
    required this.selectedDate,
    required this.jumpNonce,
    required this.onDateSelected,
    required this.onEventTap,
  });

  final List<AppCalendarEvent> events;
  final DateTime selectedDate;

  /// Incremented by the parent when a search should reposition the calendar.
  /// Used as the [AppCalendar] key so it remounts onto [selectedDate].
  final int jumpNonce;
  final ValueChanged<DateTime> onDateSelected;
  final ValueChanged<AppCalendarEvent> onEventTap;

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.df,
            AppSpacing.df,
            AppSpacing.df,
            AppSpacing.sm,
          ),
          sliver: SliverToBoxAdapter(
            child: AppCalendar(
              key: ValueKey(jumpNonce),
              events: events,
              initialDate: selectedDate,
              showEventList: true,
              showTodayButton: true,
              todayLabel: AppLocalizations.get('today'),
              todayButtonLabel: AppLocalizations.get('today'),
              onDateSelected: onDateSelected,
              onEventTap: onEventTap,
              accentColor: AppColors.primary,
              emptyStateTitle: AppLocalizations.get('noEventsForDay'),
            ),
          ),
        ),
      ],
    );
  }
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
        ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _EventFilterPill extends StatelessWidget {
  const _EventFilterPill({
    this.icon,
    this.label,
    required this.onTap,
    this.highlighted = false,
  });

  final AppIconData? icon;
  final String? label;
  final VoidCallback onTap;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final fg = highlighted ? AppColors.primary : AppColors.textPrimary;
    final radius = AppSpacing.borderRadiusRound;
    return Material(
      color: highlighted ? AppColors.primaryLight : AppColors.surface,
      borderRadius: radius,
      child: InkWell(
        onTap: onTap,
        borderRadius: radius,
        child: label == null && icon != null
            ? SizedBox(
                width: 40,
                height: 40,
                child: Center(child: AppIcon(icon!, size: 18, color: fg)),
              )
            : Container(
                constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (icon != null) ...[
                      AppIcon(icon!, size: 18, color: fg),
                      if (label != null) const SizedBox(width: AppSpacing.sm),
                    ],
                    if (label != null)
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 140),
                        child: Text(
                          label!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: AppTextStyles.bodySmall.copyWith(
                            color: fg,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
      ),
    );
  }
}

class _SearchBar extends StatefulWidget {
  const _SearchBar({
    required this.controller,
    required this.onChanged,
    required this.onClose,
    required this.autoFocus,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onClose;
  final bool autoFocus;

  @override
  State<_SearchBar> createState() => _SearchBarState();
}

class _SearchBarState extends State<_SearchBar>
    with SingleTickerProviderStateMixin {
  late final FocusNode _focus;
  late final AnimationController _animCtrl;
  late final Animation<double> _slideAnim;
  late final Animation<double> _fadeAnim;

  @override
  void initState() {
    super.initState();
    _focus = FocusNode();
    _focus.addListener(_onFocusChange);
    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 260),
    );
    _slideAnim = Tween<double>(
      begin: -14,
      end: 0,
    ).animate(CurvedAnimation(parent: _animCtrl, curve: Curves.easeOutCubic));
    _fadeAnim = CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut);
    if (widget.autoFocus) _open();
  }

  @override
  void didUpdateWidget(_SearchBar old) {
    super.didUpdateWidget(old);
    if (widget.autoFocus && !old.autoFocus) _open();
  }

  void _open() {
    _animCtrl.forward(from: 0);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _focus.requestFocus();
    });
  }

  void _onFocusChange() {
    if (mounted) {
      if (!_focus.hasFocus) {
        final trimmed = widget.controller.text.trim();
        if (widget.controller.text != trimmed) {
          widget.controller.text = trimmed;
          widget.onChanged(trimmed);
        }
      }
      setState(() {});
    }
  }

  @override
  void dispose() {
    _focus.removeListener(_onFocusChange);
    _focus.dispose();
    _animCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final borderColor = isLight ? AppColors.borderGrey : AppColors.borderDark;
    final bg = isLight
        ? AppColors.surface.withValues(alpha: 0.92)
        : AppColors.surfaceDark.withValues(alpha: 0.92);
    return AnimatedBuilder(
      animation: _animCtrl,
      builder: (context, child) => FadeTransition(
        opacity: _fadeAnim,
        child: Transform.translate(
          offset: Offset(_slideAnim.value, 0),
          child: child,
        ),
      ),
      child: SizedBox(
        height: 40,
        child: Row(
          children: [
            Expanded(
              child: GestureDetector(
                onTap: () => _focus.requestFocus(),
                child: Container(
                  height: 40,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: AppSpacing.borderRadiusDf,
                    border: Border.all(color: borderColor, width: 1),
                    boxShadow: null,
                  ),
                  child: Row(
                    children: [
                      AppIcon(
                        AppIcons.search,
                        size: 18,
                        color: AppColors.textSecondary,
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: TextField(
                          controller: widget.controller,
                          focusNode: _focus,
                          maxLength: 100,
                          scrollPadding: EdgeInsets.zero,
                          inputFormatters: [SanitizingFormatter()],
                          onChanged: widget.onChanged,
                          style: AppTextStyles.bodyMedium.copyWith(
                            fontWeight: FontWeight.w600,
                            color: isLight
                                ? AppColors.textPrimary
                                : AppColors.textPrimaryDark,
                          ),
                          decoration: InputDecoration(
                            filled: false,
                            hintText: 'Search events…',
                            hintStyle: AppTextStyles.bodyMedium.copyWith(
                              fontWeight: FontWeight.w500,
                              color: AppColors.textSecondary,
                            ),
                            border: InputBorder.none,
                            isDense: true,
                            contentPadding: EdgeInsets.zero,
                            counterText: '',
                          ),
                          textInputAction: TextInputAction.search,
                        ),
                      ),
                      ValueListenableBuilder<TextEditingValue>(
                        valueListenable: widget.controller,
                        builder: (ctx, value, child) => GestureDetector(
                          onTap: () {
                            if (value.text.isNotEmpty) {
                              widget.controller.clear();
                              widget.onChanged('');
                              _focus.requestFocus();
                            } else {
                              _focus.unfocus();
                              widget.onClose();
                            }
                          },
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 4.0,
                            ),
                            child: AppIcon(
                              AppIcons.close,
                              size: 18,
                              color: AppColors.textSecondary,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
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
    final textPrimary = isLight
        ? AppColors.textPrimary
        : AppColors.textPrimaryDark;
    final divider = isLight ? AppColors.borderGrey : AppColors.borderDark;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final group in _sortGroups) ...[
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
    final pressedColor = AppColors.primaryLight.withValues(alpha: 0.5);

    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 80),
        color: _pressed ? pressedColor : AppColors.transparent,
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.md,
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                widget.label,
                style: AppTextStyles.bodyLarge.copyWith(
                  fontWeight: widget.selected
                      ? FontWeight.w600
                      : FontWeight.w500,
                  color: widget.textColor,
                ),
              ),
            ),
            if (widget.selected)
              AppIcon(AppIcons.check, size: 18, color: AppColors.primary),
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
    _focusNode.addListener(
      () => setState(() => _focused = _focusNode.hasFocus),
    );
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
    final surface = isLight ? AppColors.surface : AppColors.surfaceDark;
    final textPrimary = isLight
        ? AppColors.textPrimary
        : AppColors.textPrimaryDark;

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
          borderRadius: AppSpacing.borderRadiusTopSheet,
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
                          ? AppColors.borderGrey
                          : AppColors.borderDark,
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
                  style: AppTextStyles.titleMedium.copyWith(color: textPrimary),
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
                                ? AppColors.fieldBackground
                                : AppColors.surfaceDark,
                            borderRadius: AppSpacing.borderRadiusMd,
                            border: Border.all(
                              color: _focused
                                  ? AppColors.primary.withValues(alpha: 0.6)
                                  : AppColors.transparent,
                              width: 1.5,
                            ),
                          ),
                          child: TextField(
                            focusNode: _focusNode,
                            maxLength: 50,
                            inputFormatters: [SanitizingFormatter()],
                            onChanged: (v) => setState(
                              () => _query = _sanitizeSearchInput(
                                v,
                              ).toLowerCase(),
                            ),
                            decoration: InputDecoration(
                              hintText: 'Search',
                              counterText: '',
                              prefixIcon: AppIcon(
                                AppIcons.search,
                                size: 18,
                                color: _focused
                                    ? AppColors.primary
                                    : AppColors.grey,
                              ),
                              border: InputBorder.none,
                              contentPadding: const EdgeInsets.symmetric(
                                vertical: 10,
                              ),
                            ),
                            style: AppTextStyles.bodyLarge,
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
                                          ? AppColors.fieldBackground
                                          : AppColors.surfaceDark),
                                borderRadius: AppSpacing.borderRadiusRound,
                              ),
                              child: Text(
                                option,
                                style: AppTextStyles.labelLarge.copyWith(
                                  color: active
                                      ? AppColors.white
                                      : (isLight
                                            ? AppColors.textPrimary
                                            : AppColors.textPrimaryDark),
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
              SizedBox(height: mq.padding.bottom + 8),
            ],
          ),
        ),
      ),
    );
  }
}
