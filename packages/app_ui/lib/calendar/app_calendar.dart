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
  final Widget Function(BuildContext context, AppCalendarEvent event)? eventBuilder;

  /// Custom empty state for dates with no events.
  /// Receives the selected date and an optional create-event callback.
  /// When null, the built-in empty state with [emptyStateTitle] etc. is used.
  final Widget Function(
    BuildContext context,
    DateTime selectedDate,
    VoidCallback? onCreateEvent,
  )? emptyStateBuilder;

  /// Called when the user navigates to a different month (prev/next/today).
  final ValueChanged<DateTime>? onMonthChanged;

  @override
  State<AppCalendar> createState() => _AppCalendarState();
}

class _AppCalendarState extends State<AppCalendar> {
  late DateTime _month;
  late DateTime _selected;
  int _slideDir = 1;

  static DateTime _dateOnly(DateTime dt) => DateTime(dt.year, dt.month, dt.day);

  @override
  void initState() {
    super.initState();
    final initial = widget.initialDate != null
        ? _dateOnly(widget.initialDate!)
        : _dateOnly(DateTime.now());
    _selected = initial;
    _month = DateTime(initial.year, initial.month, 1);
  }

  void _prevMonth() {
    HapticFeedback.selectionClick();
    setState(() {
      _slideDir = -1;
      _month = DateTime(_month.year, _month.month - 1, 1);
    });
    widget.onMonthChanged?.call(_month);
  }

  void _nextMonth() {
    HapticFeedback.selectionClick();
    setState(() {
      _slideDir = 1;
      _month = DateTime(_month.year, _month.month + 1, 1);
    });
    widget.onMonthChanged?.call(_month);
  }

  void _selectDate(DateTime date) {
    if (!widget.allowDateSelection) return;
    HapticFeedback.selectionClick();
    setState(() => _selected = date);
    widget.onDateSelected?.call(date);
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
      if (colors.length < 3 && !colors.any((c) => c.toARGB32() == color.toARGB32())) {
        colors.add(color);
      }
    }
    return map;
  }

  List<AppCalendarEvent> _eventsOn(DateTime date) {
    final list = widget.events
        .where((e) => _dateOnly(e.date) == date)
        .toList();
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

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final accent = widget.accentColor ?? AppColors.primary;
    final mloc = MaterialLocalizations.of(context);

    final surface = isLight ? Colors.white : const Color(0xFF17171A);
    final textPrimary = Theme.of(context).colorScheme.onSurface;
    final today = _dateOnly(DateTime.now());
    final isToday = _selected == today;
    final dateLabel = isToday && widget.todayLabel != null
        ? widget.todayLabel!
        : mloc.formatMediumDate(_selected);

    final indicatorMap = _buildIndicatorMap();
    final selectedEvents = _eventsOn(_selected);
    final showAutoCreateButton =
        widget.onCreateEvent != null && widget.headerAction == null;

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header ──────────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 18, 14, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (widget.headerLabel != null) ...[
                  Text(
                    widget.headerLabel!,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: accent,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 6),
                ],
                Row(
                  children: [
                    // ── Month Year (left) ──────────────────────────────────
                    Expanded(
                      child: AnimatedSwitcher(
                        duration: const Duration(milliseconds: 220),
                        transitionBuilder: (child, anim) =>
                            FadeTransition(opacity: anim, child: child),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            mloc.formatMonthYear(_month),
                            key: ValueKey(_month),
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: textPrimary,
                              letterSpacing: -0.3,
                              height: 1.1,
                            ),
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                          ),
                        ),
                      ),
                    ),
                    // ── Center: Today button (optional) ───────────────────
                    if (widget.showTodayButton) ...[
                      const SizedBox(width: 8),
                      _CalTodayButton(
                        label: widget.todayButtonLabel ?? 'Today',
                        onTap: _goToToday,
                        accent: accent,
                        isLight: isLight,
                      ),
                    ],
                    // ── Center: custom action or auto + button ─────────────
                    if (widget.headerAction != null) ...[
                      const SizedBox(width: 8),
                      widget.headerAction!,
                    ] else if (showAutoCreateButton) ...[
                      const SizedBox(width: 8),
                      GestureDetector(
                        onTap: () => widget.onCreateEvent!(_selected),
                        child: Container(
                          width: 32,
                          height: 32,
                          decoration: BoxDecoration(
                            color: accent.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: AppIcon(AppIcons.add, size: 18, color: accent),
                        ),
                      ),
                    ],
                    // ── Right: nav arrows ─────────────────────────────────
                    const SizedBox(width: 8),
                    _CalNavButton(
                      icon: AppIcons.chevronLeft,
                      onTap: _prevMonth,
                      isLight: isLight,
                    ),
                    const SizedBox(width: 4),
                    _CalNavButton(
                      icon: AppIcons.chevronRight,
                      onTap: _nextMonth,
                      isLight: isLight,
                    ),
                  ],
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // ── Weekday Labels ─────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: _CalWeekdayRow(),
          ),

          const SizedBox(height: 4),

          // ── Month Grid ─────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 220),
              switchInCurve: Curves.easeOut,
              switchOutCurve: Curves.easeIn,
              transitionBuilder: (child, animation) {
                final slide = _slideDir == 1
                    ? const Offset(0.06, 0)
                    : const Offset(-0.06, 0);
                return SlideTransition(
                  position: Tween(begin: slide, end: Offset.zero)
                      .animate(animation),
                  child: FadeTransition(opacity: animation, child: child),
                );
              },
              child: _CalMonthGrid(
                key: ValueKey(_month),
                month: _month,
                selected: _selected,
                today: today,
                indicatorMap: indicatorMap,
                accentColor: accent,
                isLight: isLight,
                onSelect: _selectDate,
              ),
            ),
          ),

          const SizedBox(height: 4),

          if (widget.showEventList) ...[
            // ── Divider ────────────────────────────────────────────────
            Container(
              height: 0.5,
              margin: const EdgeInsets.symmetric(horizontal: 16),
              color: isLight
                  ? const Color(0xFFEEEEF4)
                  : const Color(0xFF2A2A32),
            ),

            // ── Event List ─────────────────────────────────────────────
            AnimatedSize(
              duration: const Duration(milliseconds: 280),
              curve: Curves.easeInOut,
              child: _CalEventListSection(
                key: ValueKey(_selected),
                dateLabel: dateLabel,
                events: selectedEvents,
                selectedDate: _selected,
                accentColor: accent,
                emptyStateTitle: widget.emptyStateTitle,
                emptyStateSubtitle: widget.emptyStateSubtitle,
                createEventLabel: widget.createEventLabel,
                onCreateEvent: widget.onCreateEvent != null
                    ? () => widget.onCreateEvent!(_selected)
                    : null,
                eventBuilder: widget.eventBuilder,
                emptyStateBuilder: widget.emptyStateBuilder,
                onEventTap: widget.onEventTap,
                isLight: isLight,
                textPrimary: textPrimary,
              ),
            ),
          ],
        ],
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
          color: isLight
              ? const Color(0xFFF7F8FA)
              : const Color(0xFF222228),
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
    required this.accentColor,
    required this.isLight,
    required this.onSelect,
  });

  final DateTime month;
  final DateTime selected;
  final DateTime today;
  final Map<DateTime, List<Color>> indicatorMap;
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
          cells.add(const Expanded(child: SizedBox(height: 50)));
        } else {
          final date = DateTime(month.year, month.month, dayNum);
          final dots = indicatorMap[date] ?? const [];

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
                  accentColor: accentColor,
                  isLight: isLight,
                ),
              ),
            ),
          );
        }
      }
      rows.add(Row(children: cells));
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
    required this.accentColor,
    required this.isLight,
  });

  final int day;
  final bool isToday;
  final bool isSelected;
  final bool isFuture;
  final List<Color> dots;
  final Color accentColor;
  final bool isLight;

  @override
  Widget build(BuildContext context) {
    final Color bg;
    if (isSelected) {
      bg = accentColor;
    } else if (isToday) {
      bg = accentColor.withValues(alpha: 0.12);
    } else {
      bg = Colors.transparent;
    }

    final Color numColor;
    if (isSelected) {
      numColor = Colors.white;
    } else if (isFuture) {
      numColor = isLight ? const Color(0xFF8E8EA3) : const Color(0xFFB0B0C4);
    } else {
      numColor = isLight ? const Color(0xFF1A1A2E) : Colors.white;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeInOut,
      height: 50,
      margin: const EdgeInsets.symmetric(horizontal: 1, vertical: 1),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: isToday && !isSelected
            ? Border.all(
                color: accentColor.withValues(alpha: 0.35),
                width: 1.5,
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
              fontWeight:
                  (isSelected || isToday) ? FontWeight.w700 : FontWeight.w500,
              color: numColor,
              letterSpacing: -0.2,
              height: 1.0,
            ),
          ),
          const SizedBox(height: 4),
          if (dots.isNotEmpty)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                for (int i = 0; i < dots.length; i++) ...[
                  if (i > 0) const SizedBox(width: 3),
                  _CalDot(
                    color: isSelected
                        ? Colors.white.withValues(alpha: 0.85)
                        : dots[i],
                  ),
                ],
              ],
            )
          else
            const SizedBox(height: 5),
        ],
      ),
    );
  }
}

// ─── Dot ──────────────────────────────────────────────────────────────────────

class _CalDot extends StatelessWidget {
  const _CalDot({required this.color});
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 4,
      height: 4,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color),
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
  final Widget Function(BuildContext, DateTime, VoidCallback?)? emptyStateBuilder;
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
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: const Color(0xFF8E8EA3).withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(10),
          ),
          child: AppIcon(
            AppIcons.sun,
            size: 18,
            color: const Color(0xFF8E8EA3).withValues(alpha: 0.55),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (emptyStateTitle != null)
                Text(
                  emptyStateTitle!,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: textPrimary,
                  ),
                ),
              if (emptyStateSubtitle != null)
                Text(
                  emptyStateSubtitle!,
                  style: const TextStyle(
                    fontSize: 11,
                    color: Color(0xFF8E8EA3),
                  ),
                ),
            ],
          ),
        ),
        if (onCreateEvent != null && createEventLabel != null)
          GestureDetector(
            onTap: onCreateEvent,
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: accentColor.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: accentColor.withValues(alpha: 0.25),
                  width: 0.8,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  AppIcon(AppIcons.add, size: 13, color: accentColor),
                  const SizedBox(width: 4),
                  Text(
                    createEventLabel!,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: accentColor,
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
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
