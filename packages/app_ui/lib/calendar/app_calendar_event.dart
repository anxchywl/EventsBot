import 'package:flutter/material.dart';

import '../icons/app_icon_data.dart';

/// A universal, feature-agnostic calendar event.
///
/// Pass a list of these to [AppCalendar]. The [color] drives the dot
/// indicator shown on calendar grid cells. The [metadata] field carries
/// feature-specific data so custom [AppCalendar.eventBuilder]s can cast
/// it back to the original domain type.
@immutable
class AppCalendarEvent {
  const AppCalendarEvent({
    required this.id,
    required this.title,
    required this.date,
    this.subtitle,
    this.time,
    this.color,
    this.icon,
    this.type,
    this.metadata,
  });

  /// Unique event identifier.
  final String id;

  /// Primary display title.
  final String title;

  /// Optional secondary description line.
  final String? subtitle;

  /// The calendar date this event belongs to. The time component is ignored;
  /// use [time] for intra-day ordering.
  final DateTime date;

  /// Optional time of day used for sorting events within a day.
  final TimeOfDay? time;

  /// Color of the dot indicator shown on the calendar cell.
  /// Defaults to [AppColors.primary] when not provided.
  final Color? color;

  /// Icon shown in the default event list renderer.
  final AppIconData? icon;

  /// Feature-defined category string (e.g., "workout", "class", "meal").
  /// Used by [AppCalendar.eventBuilder] to dispatch to the right renderer.
  final String? type;

  /// Arbitrary feature-specific payload accessible in [AppCalendar.eventBuilder].
  /// Cast to the appropriate domain type inside the builder.
  final Object? metadata;
}
