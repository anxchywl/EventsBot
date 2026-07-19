import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/localization.dart';
import 'analytics_period.dart';

String _fmtDate(DateTime d) =>
    '${d.day.toString().padLeft(2, '0')}.'
    '${d.month.toString().padLeft(2, '0')}.'
    '${d.year}';

/// Opens the period picker as a bottom sheet.
/// Returns null if dismissed without a choice (preserving the current period).
Future<AnalyticsPeriod?> pickAnalyticsPeriod(
  BuildContext context, {
  required AnalyticsPeriod current,
}) {
  return AppBottomSheet.show<AnalyticsPeriod>(
    context: context,
    child: _PeriodPickerSheet(current: current),
  );
}

// ── Shell ─────────────────────────────────────────────────────────────────────

class _PeriodPickerSheet extends StatefulWidget {
  const _PeriodPickerSheet({required this.current});
  final AnalyticsPeriod current;

  @override
  State<_PeriodPickerSheet> createState() => _PeriodPickerSheetState();
}

class _PeriodPickerSheetState extends State<_PeriodPickerSheet> {
  static const _periodOrder = [
    PeriodType.last7,
    PeriodType.last30,
    PeriodType.last90,
    PeriodType.thisMonth,
    PeriodType.thisYear,
    PeriodType.allTime,
    PeriodType.custom,
  ];

  bool _showingCustom = false;
  DateTime? _start;
  DateTime? _end;
  bool _selectingStart = true;

  static DateTime get _today {
    final n = DateTime.now();
    return DateTime(n.year, n.month, n.day);
  }

  static DateTime get _firstAllowed => DateTime(_today.year - 5);

  @override
  void initState() {
    super.initState();
    if (widget.current.type == PeriodType.custom) {
      _start = widget.current.customStart;
      _end = widget.current.customEnd;
    }
  }

  void _selectPeriod(PeriodType type) {
    if (type == PeriodType.custom) {
      setState(() {
        _showingCustom = true;
        _selectingStart = _start == null;
      });
      return;
    }
    Navigator.of(context).pop(AnalyticsPeriod(type));
  }

  void _applyCustom() {
    if (_start == null || _end == null) return;
    Navigator.of(context).pop(
      AnalyticsPeriod(PeriodType.custom, customStart: _start, customEnd: _end),
    );
  }

  void _onCalendarDay(DateTime date) {
    setState(() {
      if (_selectingStart) {
        _start = date;
        // If existing end is now strictly before the new start, invalidate it.
        if (_end != null && _end!.isBefore(date)) _end = null;
        // Always advance so the user sees they need to pick To next.
        _selectingStart = false;
      } else {
        // Calendar constraints (firstDate = _start) prevent date < _start.
        _end = date;
        // Stay in To-mode so the user can re-pick without switching tabs.
      }
    });
  }

  /// Switching to To-mode is blocked if From has not been chosen yet;
  /// redirect back to From-mode in that case.
  void _onSwitchMode(bool wantsStart) {
    if (!wantsStart && _start == null) {
      setState(() => _selectingStart = true);
      return;
    }
    setState(() => _selectingStart = wantsStart);
  }

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: AnimatedSize(
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutCubic,
        alignment: Alignment.topCenter,
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 300),
          // Only the INCOMING child is a normal Stack child (drives layout
          // size). Exiting children are Positioned so they don't inflate the
          // Stack — AnimatedSize therefore sees the true target height and can
          // animate the sheet resize simultaneously with the slide.
          layoutBuilder: (currentChild, previousChildren) => Stack(
            clipBehavior: Clip.hardEdge,
            alignment: Alignment.topCenter,
            children: [
              for (final prev in previousChildren)
                Positioned(left: 0, right: 0, top: 0, child: prev),
              ?currentChild,
            ],
          ),
          transitionBuilder: (child, animation) {
            // custom conceptually lives to the RIGHT (+1),
            // list to the LEFT (-1). This holds for both directions:
            //   forward  → custom enters from right, list exits to left  ✓
            //   backward → list enters from left,  custom exits to right ✓
            final begin = child.key == const ValueKey('custom')
                ? const Offset(1, 0)
                : const Offset(-1, 0);
            return SlideTransition(
              position: Tween<Offset>(begin: begin, end: Offset.zero).animate(
                CurvedAnimation(parent: animation, curve: Curves.easeOutCubic),
              ),
              child: FadeTransition(opacity: animation, child: child),
            );
          },
          child: _showingCustom
              ? _CustomRangeView(
                  key: const ValueKey('custom'),
                  start: _start,
                  end: _end,
                  selectingStart: _selectingStart,
                  today: _today,
                  firstAllowed: _firstAllowed,
                  onSwitchMode: _onSwitchMode,
                  onCalendarDay: _onCalendarDay,
                  onBack: () => setState(() => _showingCustom = false),
                  onApply: _applyCustom,
                )
              : _PeriodListView(
                  key: const ValueKey('list'),
                  current: widget.current,
                  periodOrder: _periodOrder,
                  onSelect: _selectPeriod,
                ),
        ),
      ),
    );
  }
}

// ── Period list ───────────────────────────────────────────────────────────────

class _PeriodListView extends StatelessWidget {
  const _PeriodListView({
    super.key,
    required this.current,
    required this.periodOrder,
    required this.onSelect,
  });

  final AnalyticsPeriod current;
  final List<PeriodType> periodOrder;
  final ValueChanged<PeriodType> onSelect;

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final textPrimary = isLight
        ? AppColors.textPrimary
        : AppColors.textPrimaryDark;
    final divider = isLight
        ? AppColors.black.withValues(alpha: 0.06)
        : AppColors.white.withValues(alpha: 0.06);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 16),
          child: Text(
            AppLocalizations.get('period'),
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w600,
              letterSpacing: -0.3,
              color: textPrimary,
              height: 1.2,
            ),
          ),
        ),
        ...List.generate(periodOrder.length, (i) {
          final type = periodOrder[i];
          final isLast = i == periodOrder.length - 1;
          // For the Custom row, append the saved date range when it exists.
          final isCustomRow = type == PeriodType.custom;
          final hasRange =
              isCustomRow &&
              current.type == PeriodType.custom &&
              current.customStart != null &&
              current.customEnd != null;
          final label = hasRange
              ? '${AppLocalizations.get('customRange')} '
                    '(${_fmtDate(current.customStart!)} – ${_fmtDate(current.customEnd!)})'
              : AnalyticsPeriod(type).label;
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _PeriodTile(
                label: label,
                isSelected: type == current.type,
                isCustom: isCustomRow,
                textPrimary: textPrimary,
                onTap: () => onSelect(type),
              ),
              if (!isLast)
                Divider(height: 1, indent: 20, endIndent: 20, color: divider),
            ],
          );
        }),
        const SizedBox(height: 8),
      ],
    );
  }
}

class _PeriodTile extends StatefulWidget {
  const _PeriodTile({
    required this.label,
    required this.isSelected,
    required this.isCustom,
    required this.textPrimary,
    required this.onTap,
  });

  final String label;
  final bool isSelected;
  final bool isCustom;
  final Color textPrimary;
  final VoidCallback onTap;

  @override
  State<_PeriodTile> createState() => _PeriodTileState();
}

class _PeriodTileState extends State<_PeriodTile> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final pressed = isLight
        ? AppColors.black.withValues(alpha: 0.04)
        : AppColors.white.withValues(alpha: 0.04);

    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 80),
        color: _pressed ? pressed : AppColors.transparent,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 13),
        child: Row(
          children: [
            Expanded(
              child: Text(
                widget.label,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: widget.isSelected
                      ? FontWeight.w600
                      : FontWeight.w500,
                  color: widget.textPrimary,
                  height: 1.3,
                ),
              ),
            ),
            if (widget.isSelected)
              const Icon(Icons.check, size: 18, color: AppColors.primary)
            else if (widget.isCustom)
              const Icon(Icons.chevron_right, size: 18, color: AppColors.grey),
          ],
        ),
      ),
    );
  }
}

// ── Custom range view ─────────────────────────────────────────────────────────

class _CustomRangeView extends StatelessWidget {
  const _CustomRangeView({
    super.key,
    required this.start,
    required this.end,
    required this.selectingStart,
    required this.today,
    required this.firstAllowed,
    required this.onSwitchMode,
    required this.onCalendarDay,
    required this.onBack,
    required this.onApply,
  });

  final DateTime? start;
  final DateTime? end;
  final bool selectingStart;
  final DateTime today;
  final DateTime firstAllowed;
  final ValueChanged<bool> onSwitchMode;
  final ValueChanged<DateTime> onCalendarDay;
  final VoidCallback onBack;
  final VoidCallback onApply;

  // The calendar's effective date constraints depend on which tab is active.
  // To-mode: firstDate is clamped to `start` so dates before `start` are grey.
  DateTime get _calFirst =>
      selectingStart ? firstAllowed : (start ?? firstAllowed);
  DateTime get _calLast => today;

  // Clamp the displayed month into [_calFirst, _calLast] so CalendarDatePicker
  // never throws an assertion about initialDate being out of range.
  DateTime _calInitial() {
    final preferred = selectingStart ? (start ?? today) : (end ?? today);
    if (preferred.isBefore(_calFirst)) return _calFirst;
    if (preferred.isAfter(_calLast)) return _calLast;
    return preferred;
  }

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    final textPrimary = isLight
        ? AppColors.textPrimary
        : AppColors.textPrimaryDark;
    final textSub = AppColors.textSecondary;
    final surface = isLight ? AppColors.fieldBackground : AppColors.surfaceDark;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // ── Header ──────────────────────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
          child: Row(
            children: [
              IconButton(
                onPressed: onBack,
                icon: Icon(
                  Icons.arrow_back_ios_new,
                  size: 17,
                  color: textPrimary,
                ),
                visualDensity: VisualDensity.compact,
              ),
              Expanded(
                child: Text(
                  AppLocalizations.get('customRange'),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -0.3,
                    color: textPrimary,
                  ),
                ),
              ),
              const SizedBox(width: 44), // balance the back button
            ],
          ),
        ),

        // ── From / To tabs ───────────────────────────────────────────
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Row(
            children: [
              Expanded(
                child: _DateTab(
                  label: 'From',
                  date: start,
                  isActive: selectingStart,
                  textPrimary: textPrimary,
                  textSub: textSub,
                  surface: surface,
                  onTap: () => onSwitchMode(true),
                ),
              ),
              // Arrow between tabs
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Icon(
                  Icons.arrow_forward,
                  size: 16,
                  color: (start != null && end != null)
                      ? AppColors.primary
                      : textSub,
                ),
              ),
              Expanded(
                child: _DateTab(
                  label: 'To',
                  date: end,
                  // Dim the To-tab if From isn't picked yet
                  isActive: !selectingStart,
                  dimmed: start == null,
                  textPrimary: textPrimary,
                  textSub: textSub,
                  surface: surface,
                  onTap: () => onSwitchMode(false),
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 4),

        // ── Inline calendar ─────────────────────────────────────────
        // No key tied to selectingStart: the widget is kept alive across mode
        // switches so the displayed month never jumps. firstDate updates via
        // didUpdateWidget and greys out invalid days without a rebuild.
        Theme(
          data: Theme.of(context).copyWith(
            colorScheme: Theme.of(context).colorScheme.copyWith(
              primary: AppColors.primary,
              onPrimary: AppColors.white,
              onSurface: textPrimary,
              onSurfaceVariant: textSub,
            ),
          ),
          child: CalendarDatePicker(
            initialDate: _calInitial(),
            firstDate: _calFirst,
            lastDate: _calLast,
            onDateChanged: onCalendarDay,
          ),
        ),

        // ── Apply ────────────────────────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 16),
          child: AppPrimaryButton(
            text: AppLocalizations.get('apply'),
            onPressed: (start != null && end != null) ? onApply : null,
          ),
        ),
      ],
    );
  }
}

// ── Date tab ─────────────────────────────────────────────────────────────────

class _DateTab extends StatelessWidget {
  const _DateTab({
    required this.label,
    required this.date,
    required this.isActive,
    required this.textPrimary,
    required this.textSub,
    required this.surface,
    required this.onTap,
    this.dimmed = false,
  });

  final String label;
  final DateTime? date;
  final bool isActive;
  final bool dimmed;
  final Color textPrimary;
  final Color textSub;
  final Color surface;
  final VoidCallback onTap;

  // Fixed height keeps the row stable while the label floats.
  static const double _h = 56.0;
  // Vertical centre of the label text at t=0 (fontSize ≈ 16 → lineH ≈ 20).
  static const double _labelCentredTop = (_h - 20) / 2;
  // Top offset the label settles at once a date is chosen.
  static const double _labelFloatedTop = 7.0;

  static double _lerp(double a, double b, double t) => a + (b - a) * t;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.primary.withValues(alpha: 0.10);
    final labelActiveColor = dimmed
        ? textSub.withValues(alpha: 0.35)
        : isActive
        ? AppColors.primary
        : textSub;

    return GestureDetector(
      onTap: onTap,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0.0, end: date != null ? 1.0 : 0.0),
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
        builder: (context, t, _) {
          final labelSize = _lerp(15.0, 10.0, t);
          final labelTop = _lerp(_labelCentredTop, _labelFloatedTop, t);
          final labelWeight = t > 0.5 ? FontWeight.w700 : FontWeight.w500;
          final labelSpacing = _lerp(0.6, 0.4, t);

          return AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
            height: _h,
            decoration: BoxDecoration(
              color: isActive ? accent : surface,
              borderRadius: AppSpacing.borderRadiusMd,
              border: Border.all(
                color: isActive
                    ? AppColors.primary.withValues(alpha: 0.45)
                    : AppColors.transparent,
                width: 1.5,
              ),
            ),
            child: Stack(
              children: [
                // ── Floating label ───────────────────────────────
                Positioned(
                  top: labelTop,
                  left: 0,
                  right: 0,
                  child: Text(
                    label.toUpperCase(),
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: labelSize,
                      fontWeight: labelWeight,
                      letterSpacing: labelSpacing,
                      color: labelActiveColor,
                      height: 1.0,
                    ),
                  ),
                ),
                // ── Date value (fades + slides in from below) ────
                Positioned(
                  bottom: 7,
                  left: 0,
                  right: 0,
                  child: Opacity(
                    opacity: t.clamp(0.0, 1.0),
                    child: Transform.translate(
                      offset: Offset(0, _lerp(6, 0, t)),
                      child: Text(
                        date != null ? _fmtDate(date!) : '',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: dimmed
                              ? textPrimary.withValues(alpha: 0.35)
                              : textPrimary,
                          height: 1.2,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
