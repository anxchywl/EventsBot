import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../icons/app_icon.dart';
import '../icons/app_icons.dart';
import '../tokens/app_colors.dart';
import 'app_calendar_event.dart';

/// A premium, feature-agnostic monthly calendar widget.
///
/// Handles month navigation, date selection, event indicators, and an
/// animated event list. Features inject data through [events] and
/// customize rendering through [eventBuilder] and [emptyStateBuilder].
///
/// ## Minimal usage
///
/// ```dart
/// AppCalendar(
///   events: myEvents,
///   accentColor: Colors.green,
///   headerLabel: 'FITNESS CALENDAR',
///   onCreateEvent: (date) => showCreateSheet(date),
/// )
/// ```
///
/// ## Custom event rendering
///
/// ```dart
/// AppCalendar(
///   events: events,
///   eventBuilder: (context, event) => MyEventRow(event: event),
/// )
/// ```
class AppCalendar extends StatefulWidget {
  const AppCalendar({
    super.key,
    this.events = const [],
    this.initialDate,
    this.accentColor,
    this.headerLabel,
    this.headerAction,
    this.showEventList = true,
    this.allowDateSelection = true,
    this.showTodayButton = false,
    this.todayLabel,
    this.todayButtonLabel,
    this.emptyStateTitle,
    this.emptyStateSubtitle,
    this.createEventLabel,
    this.onDateSelected,
    this.onCreateEvent,
    this.onEventTap,
    this.eventBuilder,
    this.emptyStateBuilder,
    this.onMonthChanged,
  });

  /// All calendar events across all dates.
  final List<AppCalendarEvent> events;

  /// Initially selected date. Defaults to today.
  final DateTime? initialDate;

  /// Primary accent color: selected-day background, today border,
  /// dot default, header label, and auto-generated + button.
  /// Defaults to [AppColors.primary].
  final Color? accentColor;

  /// Small label displayed above the month/year title (e.g., "FITNESS CALENDAR").
  final String? headerLabel;

  /// Custom widget rendered in the header's trailing area, before the nav buttons.
  /// When null and [onCreateEvent] is set, AppCalendar auto-renders a + button
  /// styled with [accentColor].
  final Widget? headerAction;

  /// Whether to render the event list section below the grid.
  final bool showEventList;

  /// Whether tapping a grid cell selects it.
  final bool allowDateSelection;

  /// Whether to show a "Today" button in the calendar header (after nav arrows).
  final bool showTodayButton;

  /// Localized "Today" string shown as the date label when the selected day is today.
  final String? todayLabel;

  /// Label for the Today header button. Falls back to "Today" when null.
  final String? todayButtonLabel;

  /// Title for the built-in empty state (e.g., "No activity planned").
  final String? emptyStateTitle;

  /// Subtitle for the built-in empty state (e.g., "Want to add something?").
  final String? emptyStateSubtitle;

  /// Label for the built-in create-event button (e.g., "+ Create event").
  final String? createEventLabel;

  /// Called when the user selects a date.
  final ValueChanged<DateTime>? onDateSelected;

  /// Called when the user triggers event creation. Receives the currently
  /// selected date so the create sheet can pre-fill it.
  final void Function(DateTime selectedDate)? onCreateEvent;

  /// Called when the user taps an event in the default renderer.
  final ValueChanged<AppCalendarEvent>? onEventTap;

  /// Custom renderer for individual events.
  /// When null, a default row (icon + title + subtitle + time) is used.
  final Widget Function(BuildContext context, AppCalendarEvent event)?
  eventBuilder;

  /// Custom empty state for dates with no events.
  /// Receives the selected date and an optional create-event callback.
  /// When null, the built-in empty state with [emptyStateTitle] etc. is used.
  final Widget Function(
    BuildContext context,
    DateTime selectedDate,
    VoidCallback? onCreateEvent,
  )?
  emptyStateBuilder;

  /// Called when the user navigates to a different month (prev/next/today).
  final ValueChanged<DateTime>? onMonthChanged;

  @override
  State<AppCalendar> createState() => _AppCalendarState();
}

class _AppCalendarState extends State<AppCalendar> {
  static const _monthRange = 12;
  static const _monthSectionExtent = 400.0;

  late DateTime _month;
  late DateTime _selected;
  late final PageController _pageController;
  int _slideDir = 1;

  static DateTime _dateOnly(DateTime dt) => DateTime(dt.year, dt.month, dt.day);

  int _pageIndexFor(DateTime month) {
    final today = DateTime.now();
    final offset = (month.year - today.year) * 12 + (month.month - today.month);
    final index = _monthRange + offset;
    return index.clamp(0, _monthRange * 2);
  }

  void _syncPageController(DateTime month) {
    final targetPage = _pageIndexFor(month);
    if (_pageController.hasClients && _pageController.page?.round() != targetPage) {
      _pageController.animateToPage(
        targetPage,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    }
  }

  @override
  void initState() {
    super.initState();
    final initial = widget.initialDate != null
        ? _dateOnly(widget.initialDate!)
        : _dateOnly(DateTime.now());
    _selected = initial;
    _month = DateTime(initial.year, initial.month, 1);
    _pageController = PageController(
      initialPage: _pageIndexFor(_month),
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _prevMonth() {
    HapticFeedback.selectionClick();
    final newMonth = DateTime(_month.year, _month.month - 1, 1);
    setState(() {
      _slideDir = -1;
      _month = newMonth;
    });
    _syncPageController(newMonth);
    widget.onMonthChanged?.call(_month);
  }

  void _nextMonth() {
    HapticFeedback.selectionClick();
    final newMonth = DateTime(_month.year, _month.month + 1, 1);
    setState(() {
      _slideDir = 1;
      _month = newMonth;
    });
    _syncPageController(newMonth);
    widget.onMonthChanged?.call(_month);
  }

  void _selectDate(DateTime date) {
    if (!widget.allowDateSelection) return;
    HapticFeedback.selectionClick();
    final dayEvents = _eventsOn(date);
    final newMonth = DateTime(date.year, date.month, 1);
    setState(() {
      _selected = date;
      _month = newMonth;
    });
    _syncPageController(newMonth);
    widget.onDateSelected?.call(date);
    if (widget.showEventList) {
      _showDayPreview(date, dayEvents);
    }
  }

  void _goToToday() {
    HapticFeedback.selectionClick();
    final today = _dateOnly(DateTime.now());
    final todayMonth = DateTime(today.year, today.month, 1);
    setState(() {
      _slideDir = _month.isBefore(todayMonth) ? 1 : -1;
      _month = todayMonth;
      _selected = today;
    });
    _syncPageController(todayMonth);
    widget.onMonthChanged?.call(_month);
    widget.onDateSelected?.call(today);
  }

  // Builds a map of date → up to 3 unique indicator colors.
  Map<DateTime, List<Color>> _buildIndicatorMap() {
    final map = <DateTime, List<Color>>{};
    for (final event in widget.events) {
      final date = _dateOnly(event.date);
      final color = event.color ?? AppColors.primary;
      final colors = map.putIfAbsent(date, () => <Color>[]);
      if (colors.length < 3 &&
          !colors.any((c) => c.toARGB32() == color.toARGB32())) {
        colors.add(color);
      }
    }
    return map;
  }

  Map<DateTime, int> _buildEventCountMap() {
    final map = <DateTime, int>{};
    for (final event in widget.events) {
      final date = _dateOnly(event.date);
      map[date] = (map[date] ?? 0) + 1;
    }
    return map;
  }

  List<AppCalendarEvent> _eventsOn(DateTime date) {
    final list = widget.events.where((e) => _dateOnly(e.date) == date).toList();
    list.sort((a, b) {
      final ta = a.time;
      final tb = b.time;
      if (ta == null && tb == null) return 0;
      if (ta == null) return 1;
      if (tb == null) return -1;
      return (ta.hour * 60 + ta.minute).compareTo(tb.hour * 60 + tb.minute);
    });
    return list;
  }

  void _showDayPreview(DateTime date, List<AppCalendarEvent> events) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      useSafeArea: false,
      builder: (context) {
        return _CalDayPreviewSheet(
          dateLabel: MaterialLocalizations.of(context).formatMediumDate(date),
          events: events,
          accentColor: widget.accentColor ?? AppColors.primary,
          emptyStateTitle: widget.emptyStateTitle,
          emptyStateSubtitle: widget.emptyStateSubtitle,
          eventBuilder: widget.eventBuilder,
          onEventTap: widget.onEventTap,
          onCreateEvent: widget.onCreateEvent != null
              ? () => widget.onCreateEvent!(date)
              : null,
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final accent = widget.accentColor ?? AppColors.primary;
    final mloc = MaterialLocalizations.of(context);

    final surface = isLight ? Colors.white : const Color(0xFF17171A);
    final today = _dateOnly(DateTime.now());
    final indicatorMap = _buildIndicatorMap();
    final eventCountMap = _buildEventCountMap();

    return Align(
      alignment: Alignment.topCenter,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: Container(
          height: _monthSectionExtent,
          decoration: BoxDecoration(
            color: surface,
            borderRadius: BorderRadius.circular(24),
            border: Border.all(
              color: isLight
                  ? const Color(0xFFE8E6F2)
                  : const Color(0xFF2A2A32),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: isLight ? 0.06 : 0.20),
                blurRadius: 18,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: PageView.builder(
            scrollDirection: Axis.vertical,
            controller: _pageController,
            onPageChanged: (pageIndex) {
              final offset = pageIndex - _monthRange;
              final newMonth = DateTime(today.year, today.month + offset, 1);
              setState(() => _month = newMonth);
              widget.onMonthChanged?.call(newMonth);
            },
            itemCount: _monthRange * 2 + 1,
            itemBuilder: (context, index) {
              final offset = index - _monthRange;
              final targetMonth = DateTime(today.year, today.month + offset, 1);
              return _CalMonthSection(
                month: targetMonth,
                monthLabel: mloc.formatMonthYear(targetMonth),
                selected: _selected,
                today: today,
                indicatorMap: indicatorMap,
                eventCountMap: eventCountMap,
                accentColor: accent,
                isLight: isLight,
                onSelect: _selectDate,
              );
            },
          ),
        ),
      ),
    );
  }
}

// ─── Navigation Button ────────────────────────────────────────────────────────

class _CalNavButton extends StatelessWidget {
  const _CalNavButton({
    required this.icon,
    required this.onTap,
    required this.isLight,
  });

  final AppIconData icon;
  final VoidCallback onTap;
  final bool isLight;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: isLight ? const Color(0xFFF7F8FA) : const Color(0xFF222228),
          borderRadius: BorderRadius.circular(12),
        ),
        child: AppIcon(icon, size: 22, color: const Color(0xFF8E8EA3)),
      ),
    );
  }
}

// ─── Today Button ─────────────────────────────────────────────────────────────

class _CalTodayButton extends StatelessWidget {
  const _CalTodayButton({
    required this.label,
    required this.onTap,
    required this.accent,
    required this.isLight,
  });

  final String label;
  final VoidCallback onTap;
  final Color accent;
  final bool isLight;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        height: 36,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(12),
        ),
        alignment: Alignment.center,
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: Theme.of(context).colorScheme.onSurface,
            letterSpacing: -0.1,
          ),
        ),
      ),
    );
  }
}

class _CalMonthSection extends StatelessWidget {
  const _CalMonthSection({
    required this.month,
    required this.monthLabel,
    required this.selected,
    required this.today,
    required this.indicatorMap,
    required this.eventCountMap,
    required this.accentColor,
    required this.isLight,
    required this.onSelect,
  });

  final DateTime month;
  final String monthLabel;
  final DateTime selected;
  final DateTime today;
  final Map<DateTime, List<Color>> indicatorMap;
  final Map<DateTime, int> eventCountMap;
  final Color accentColor;
  final bool isLight;
  final ValueChanged<DateTime> onSelect;

  @override
  Widget build(BuildContext context) {
    final surface = isLight ? Colors.white : const Color(0xFF17171A);
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
      child: Column(
        children: [
          Center(
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 14,
                vertical: 5,
              ),
              decoration: BoxDecoration(
                color: surface.withValues(alpha: 0.94),
                borderRadius: BorderRadius.circular(999),
                border: Border.all(
                  color: isLight
                      ? const Color(0xFFE8E6F2)
                      : const Color(0xFF2A2A32),
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(
                      alpha: isLight ? 0.05 : 0.16,
                    ),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Text(
                monthLabel,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  color: Theme.of(context).colorScheme.onSurface,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          const _CalWeekdayRow(),
          const SizedBox(height: 8),
          Expanded(
            child: ClipRect(
              child: _CalMonthGrid(
                month: month,
                selected: selected,
                today: today,
                indicatorMap: indicatorMap,
                eventCountMap: eventCountMap,
                accentColor: accentColor,
                isLight: isLight,
                onSelect: onSelect,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Weekday Row ──────────────────────────────────────────────────────────────

class _CalWeekdayRow extends StatelessWidget {
  const _CalWeekdayRow();

  // Monday-first narrow weekday labels (ISO week order).
  static const _labels = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

  @override
  Widget build(BuildContext context) {
    return Row(
      children: _labels.map((label) {
        return Expanded(
          child: Center(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: Color(0xFF8E8EA3),
                letterSpacing: 0.6,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

// ─── Month Grid ───────────────────────────────────────────────────────────────

class _CalMonthGrid extends StatelessWidget {
  const _CalMonthGrid({
    super.key,
    required this.month,
    required this.selected,
    required this.today,
    required this.indicatorMap,
    required this.eventCountMap,
    required this.accentColor,
    required this.isLight,
    required this.onSelect,
  });

  final DateTime month;
  final DateTime selected;
  final DateTime today;
  final Map<DateTime, List<Color>> indicatorMap;
  final Map<DateTime, int> eventCountMap;
  final Color accentColor;
  final bool isLight;
  final ValueChanged<DateTime> onSelect;

  static int _daysInMonth(DateTime m) => DateTime(m.year, m.month + 1, 0).day;

  @override
  Widget build(BuildContext context) {
    final startOffset = month.weekday - 1; // ISO weekday: Mon=1 → offset 0
    final daysInMonth = _daysInMonth(month);
    final totalRows = (startOffset + daysInMonth + 6) ~/ 7;

    final rows = <Widget>[];
    for (int row = 0; row < totalRows; row++) {
      final cells = <Widget>[];
      for (int col = 0; col < 7; col++) {
        final i = row * 7 + col;
        final dayNum = i - startOffset + 1;

        if (dayNum < 1 || dayNum > daysInMonth) {
          cells.add(const Expanded(child: SizedBox(height: 42)));
        } else {
          final date = DateTime(month.year, month.month, dayNum);
          final dots = indicatorMap[date] ?? const [];
          final eventCount = eventCountMap[date] ?? 0;

          cells.add(
            Expanded(
              child: GestureDetector(
                onTap: () => onSelect(date),
                behavior: HitTestBehavior.opaque,
                child: _CalDayCell(
                  day: dayNum,
                  isToday: date == today,
                  isSelected: date == selected,
                  isFuture: date.isAfter(today),
                  dots: dots,
                  eventCount: eventCount,
                  accentColor: accentColor,
                  isLight: isLight,
                ),
              ),
            ),
          );
        }
      }
      rows.add(Expanded(child: Row(children: cells)));
      if (row < totalRows - 1) rows.add(const SizedBox(height: 2));
    }

    return Column(children: rows);
  }
}

// ─── Day Cell ─────────────────────────────────────────────────────────────────

class _CalDayCell extends StatelessWidget {
  const _CalDayCell({
    required this.day,
    required this.isToday,
    required this.isSelected,
    required this.isFuture,
    required this.dots,
    required this.eventCount,
    required this.accentColor,
    required this.isLight,
  });

  final int day;
  final bool isToday;
  final bool isSelected;
  final bool isFuture;
  final List<Color> dots;
  final int eventCount;
  final Color accentColor;
  final bool isLight;

  @override
  Widget build(BuildContext context) {
    final hasEvents = eventCount > 0;
    final allMuted =
        hasEvents &&
        dots.isNotEmpty &&
        dots.every((color) => color.toARGB32() == AppColors.grey.toARGB32());

    final Color bg;
    if (isSelected) {
      bg = accentColor;
    } else if (isToday) {
      bg = accentColor.withValues(alpha: 0.12);
    } else if (allMuted) {
      bg = AppColors.grey.withValues(alpha: 0.12);
    } else if (eventCount >= 5) {
      bg = accentColor.withValues(alpha: 0.65);
    } else if (eventCount >= 3) {
      bg = accentColor.withValues(alpha: 0.38);
    } else if (hasEvents) {
      bg = accentColor.withValues(alpha: 0.15);
    } else {
      bg = Colors.transparent;
    }

    final Color numColor;
    if (isSelected) {
      numColor = Colors.white;
    } else if (eventCount >= 3 && !allMuted) {
      numColor = Colors.white;
    } else if (isFuture) {
      numColor = isLight ? const Color(0xFF8E8EA3) : const Color(0xFFB0B0C4);
    } else {
      numColor = isLight ? const Color(0xFF1A1A2E) : Colors.white;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeInOut,
      height: 42,
      margin: const EdgeInsets.symmetric(horizontal: 2.5, vertical: 2.5),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: isToday || (hasEvents && !isSelected)
            ? Border.all(
                color: isToday
                    ? accentColor.withValues(alpha: 0.50)
                    : (allMuted
                          ? AppColors.grey.withValues(alpha: 0.22)
                          : accentColor.withValues(alpha: 0.22)),
                width: isToday ? 1.5 : 1,
              )
            : null,
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            '$day',
            style: TextStyle(
              fontSize: 15,
              fontWeight: (isSelected || isToday)
                  ? FontWeight.w700
                  : FontWeight.w500,
              color: numColor,
              letterSpacing: -0.2,
              height: 1.0,
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Dot ──────────────────────────────────────────────────────────────────────

class _CalDayPreviewSheet extends StatelessWidget {
  const _CalDayPreviewSheet({
    required this.dateLabel,
    required this.events,
    required this.accentColor,
    this.emptyStateTitle,
    this.emptyStateSubtitle,
    this.eventBuilder,
    this.onEventTap,
    this.onCreateEvent,
  });

  final String dateLabel;
  final List<AppCalendarEvent> events;
  final Color accentColor;
  final String? emptyStateTitle;
  final String? emptyStateSubtitle;
  final Widget Function(BuildContext, AppCalendarEvent)? eventBuilder;
  final ValueChanged<AppCalendarEvent>? onEventTap;
  final VoidCallback? onCreateEvent;

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final surface = isLight ? Colors.white : const Color(0xFF1C1C1E);
    final textPrimary = isLight ? AppColors.textPrimary : AppColors.white;

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.82,
      ),
      decoration: BoxDecoration(
        color: surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: 8),
          Container(
            width: 36,
            height: 4,
            decoration: BoxDecoration(
              color: AppColors.grey.withValues(alpha: 0.35),
              borderRadius: BorderRadius.circular(999),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 8),
            child: Text(
              dateLabel,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                color: textPrimary,
              ),
            ),
          ),
          if (events.isEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
              alignment: Alignment.center,
              child: Text(
                emptyStateTitle ?? 'Available',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: AppColors.grey,
                ),
              ),
            )
          else
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 18),
                child: Column(
                  children: [
                        for (final event in events)
                          eventBuilder != null
                              ? eventBuilder!(context, event)
                              : _CalPopupEventItem(
                                  event: event,
                                  accentColor: accentColor,
                                  textPrimary: textPrimary,
                                  onTap: onEventTap == null
                                      ? null
                                      : () {
                                          Navigator.of(context).pop();
                                          onEventTap!(event);
                                        },
                                ),
                      ],
                    ),
                  ),
          ),
          SizedBox(height: MediaQuery.of(context).padding.bottom + 12),
        ],
      ),
    );
  }
}

class _CalPopupEventItem extends StatelessWidget {
  const _CalPopupEventItem({
    required this.event,
    required this.accentColor,
    required this.textPrimary,
    this.onTap,
  });

  final AppCalendarEvent event;
  final Color accentColor;
  final Color textPrimary;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final isPending = event.color == AppColors.grey;
    final accent = isPending ? AppColors.grey : AppColors.success;
    
    final title = event.subtitle ?? '';
    final location = event.title;
    
    final startStr = event.time != null
        ? '${event.time!.hour.toString().padLeft(2, '0')}:${event.time!.minute.toString().padLeft(2, '0')}'
        : '--:--';
    final endStr = event.endTime != null
        ? '${event.endTime!.hour.toString().padLeft(2, '0')}:${event.endTime!.minute.toString().padLeft(2, '0')}'
        : null;
    final timeStr = endStr != null ? '$startStr\n$endStr' : startStr;

    final isLight = Theme.of(context).brightness == Brightness.light;

    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 52,
              child: Text(
                timeStr,
                style: const TextStyle(
                  fontSize: 12,
                  color: Color(0xFF8E8EA3),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            Column(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  margin: const EdgeInsets.only(top: 5),
                  decoration: BoxDecoration(
                    color: accent,
                    shape: BoxShape.circle,
                  ),
                ),
                Container(
                  width: 2,
                  height: 64,
                  margin: const EdgeInsets.symmetric(vertical: 2),
                  color: isLight ? const Color(0xFFF2F2F7) : const Color(0xFF2C2C2E),
                ),
              ],
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isPending
                      ? (isLight ? const Color(0xFFF2F2F7) : const Color(0xFF2C2C2E))
                      : accent.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: accent.withValues(alpha: isPending ? 0.20 : 0.28),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: textPrimary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      location,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFF8E8EA3),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Event List Section ───────────────────────────────────────────────────────

class _CalEventListSection extends StatelessWidget {
  const _CalEventListSection({
    super.key,
    required this.dateLabel,
    required this.events,
    required this.selectedDate,
    required this.accentColor,
    required this.isLight,
    required this.textPrimary,
    this.emptyStateTitle,
    this.emptyStateSubtitle,
    this.createEventLabel,
    this.onCreateEvent,
    this.eventBuilder,
    this.emptyStateBuilder,
    this.onEventTap,
  });

  final String dateLabel;
  final List<AppCalendarEvent> events;
  final DateTime selectedDate;
  final Color accentColor;
  final bool isLight;
  final Color textPrimary;
  final String? emptyStateTitle;
  final String? emptyStateSubtitle;
  final String? createEventLabel;
  final VoidCallback? onCreateEvent;
  final Widget Function(BuildContext, AppCalendarEvent)? eventBuilder;
  final Widget Function(BuildContext, DateTime, VoidCallback?)?
  emptyStateBuilder;
  final ValueChanged<AppCalendarEvent>? onEventTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            dateLabel,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: textPrimary,
              letterSpacing: -0.1,
            ),
          ),
          const SizedBox(height: 10),
          if (events.isEmpty)
            _buildEmptyState(context)
          else
            ...events.map(
              (e) => eventBuilder != null
                  ? eventBuilder!(context, e)
                  : _buildDefaultEventItem(e),
            ),
        ],
      ),
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    if (emptyStateBuilder != null) {
      return emptyStateBuilder!(context, selectedDate, onCreateEvent);
    }
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () {
        Navigator.pop(context);
        onCreateEvent?.call();
      },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 16),
        alignment: Alignment.center,
        child: Text(
          'Available',
          style: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            color: accentColor,
          ),
        ),
      ),
    );
  }

  Widget _buildDefaultEventItem(AppCalendarEvent event) {
    final color = event.color ?? accentColor;
    final timeStr = event.time != null
        ? '${event.time!.hour.toString().padLeft(2, '0')}:'
              '${event.time!.minute.toString().padLeft(2, '0')}'
        : null;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: GestureDetector(
        onTap: onEventTap != null ? () => onEventTap!(event) : null,
        behavior: HitTestBehavior.opaque,
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(11),
              ),
              child: AppIcon(
                event.icon ?? AppIcons.event,
                size: 18,
                color: color,
              ),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    event.title,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: textPrimary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (event.subtitle != null)
                    Text(
                      event.subtitle!,
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF8E8EA3),
                      ),
                    ),
                ],
              ),
            ),
            if (timeStr != null)
              Text(
                timeStr,
                style: const TextStyle(
                  fontSize: 12,
                  color: Color(0xFF8E8EA3),
                  fontWeight: FontWeight.w500,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
