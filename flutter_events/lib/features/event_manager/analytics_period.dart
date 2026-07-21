import '../../core/localization.dart';

/// Dashboard period options for the analytics period selector.
enum PeriodType { last7, last30, last90, thisMonth, thisYear, allTime, custom }

/// An immutable analytics period. Resolves to the `date_from`/`date_to` the
/// backend expects (inclusive day bounds, formatted `YYYY-MM-DD`) and the
/// `trend_days` window for the views-over-time sparkline. All-time leaves both
/// date bounds null so every event is included.
class AnalyticsPeriod {
  final PeriodType type;
  final DateTime? customStart;
  final DateTime? customEnd;

  const AnalyticsPeriod(this.type, {this.customStart, this.customEnd});

  static const AnalyticsPeriod defaultPeriod = AnalyticsPeriod(
    PeriodType.last30,
  );

  static String _fmt(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  static DateTime _today() {
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day);
  }

  DateTime? get _startDate {
    final today = _today();
    switch (type) {
      case PeriodType.last7:
        return today.subtract(const Duration(days: 6));
      case PeriodType.last30:
        return today.subtract(const Duration(days: 29));
      case PeriodType.last90:
        return today.subtract(const Duration(days: 89));
      case PeriodType.thisMonth:
        return DateTime(today.year, today.month, 1);
      case PeriodType.thisYear:
        return DateTime(today.year, 1, 1);
      case PeriodType.allTime:
        return null;
      case PeriodType.custom:
        return customStart;
    }
  }

  DateTime? get _endDate {
    switch (type) {
      case PeriodType.allTime:
        return null;
      case PeriodType.custom:
        return customEnd ?? _today();
      default:
        return _today();
    }
  }

  String? get dateFrom {
    final s = _startDate;
    return s == null ? null : _fmt(s);
  }

  String? get dateTo {
    final e = _endDate;
    return e == null ? null : _fmt(e);
  }

  /// Sparkline window in days, always within the backend's 1–366 bounds.
  int get trendDays {
    final start = _startDate;
    final end = _endDate ?? _today();
    if (start == null) return 90; // all time: a sensible recent window
    final span = end.difference(start).inDays + 1;
    return span.clamp(1, 366);
  }

  String get label {
    switch (type) {
      case PeriodType.last7:
        return AppLocalizations.get('last7Days');
      case PeriodType.last30:
        return AppLocalizations.get('last30Days');
      case PeriodType.last90:
        return AppLocalizations.get('last90Days');
      case PeriodType.thisMonth:
        return AppLocalizations.get('thisMonth');
      case PeriodType.thisYear:
        return AppLocalizations.get('thisYear');
      case PeriodType.allTime:
        return AppLocalizations.get('allTime');
      case PeriodType.custom:
        final s = customStart, e = customEnd;
        if (s == null || e == null) return AppLocalizations.get('customRange');
        return '${_fmt(s)} → ${_fmt(e)}';
    }
  }

  @override
  bool operator ==(Object other) =>
      other is AnalyticsPeriod &&
      other.type == type &&
      other.customStart == customStart &&
      other.customEnd == customEnd;

  @override
  int get hashCode => Object.hash(type, customStart, customEnd);
}
