import 'dart:math';

import 'package:flutter/material.dart';

abstract final class EventFormLimits {
  static const title = 100;
  static const description = 1000;
  static const organizer = 100;
  static const location = 100;
  static const registrationUrl = 500;
  static const resource = 500;
}

final RegExp _disallowedControls = RegExp(
  r'[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]',
);

String createEventRequestId({Random? random}) {
  final generator = random ?? Random.secure();
  return List.generate(
    16,
    (_) => generator.nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
}

String? validateRequiredEventText(
  String? value, {
  required int maxLength,
  required String emptyMessage,
  required String fieldName,
  bool allowLineBreaks = false,
}) {
  final text = value?.trim() ?? '';
  if (text.isEmpty) return emptyMessage;
  if (text.runes.length > maxLength) {
    return '$fieldName must be $maxLength characters or fewer';
  }
  if (_disallowedControls.hasMatch(text) ||
      (!allowLineBreaks &&
          (text.contains('\n') ||
              text.contains('\r') ||
              text.contains('\t')))) {
    return '$fieldName contains unsupported characters';
  }
  return null;
}

String? validateOptionalEventText(
  String? value, {
  required int maxLength,
  required String fieldName,
  bool allowLineBreaks = false,
}) {
  if (value == null || value.trim().isEmpty) return null;
  return validateRequiredEventText(
    value,
    maxLength: maxLength,
    emptyMessage: '',
    fieldName: fieldName,
    allowLineBreaks: allowLineBreaks,
  );
}

String? validateEventDate(
  DateTime? value, {
  required DateTime now,
  required String missingMessage,
}) {
  if (value == null) return missingMessage;
  final selected = DateUtils.dateOnly(value);
  if (selected.isBefore(DateUtils.dateOnly(now))) {
    return 'Event date cannot be in the past';
  }
  return null;
}

String? validateEventStartTime({
  required DateTime? date,
  required TimeOfDay? startTime,
  required DateTime now,
  required String missingMessage,
}) {
  if (startTime == null) return missingMessage;
  if (date == null || !DateUtils.isSameDay(date, now)) return null;
  final selectedMinutes = startTime.hour * 60 + startTime.minute;
  final currentMinutes = now.hour * 60 + now.minute;
  if (selectedMinutes <= currentMinutes) {
    return 'Start time must be later than the current time';
  }
  return null;
}

String? validateEventEndTime({
  required TimeOfDay? startTime,
  required TimeOfDay? endTime,
  required String missingMessage,
}) {
  if (endTime == null) return missingMessage;
  if (startTime == null) return null;
  final startMinutes = startTime.hour * 60 + startTime.minute;
  final endMinutes = endTime.hour * 60 + endTime.minute;
  if (endMinutes <= startMinutes) {
    return 'End time must be after start time';
  }
  return null;
}

String? validateEventRegistrationUrl(String? value) {
  if (value == null || value.trim().isEmpty) return null;
  final text = value.trim();
  if (text.runes.length > EventFormLimits.registrationUrl ||
      _disallowedControls.hasMatch(text) ||
      RegExp(r'\s').hasMatch(text)) {
    return 'Please enter a valid URL';
  }
  final uri = Uri.tryParse(text);
  if (uri == null ||
      (uri.scheme != 'http' && uri.scheme != 'https') ||
      uri.host.isEmpty) {
    return 'Please enter a valid URL';
  }
  return null;
}

DateTime clampEventPickerDate(
  DateTime value, {
  required DateTime firstDate,
  required DateTime lastDate,
}) {
  final selected = DateUtils.dateOnly(value);
  if (selected.isBefore(firstDate)) return firstDate;
  if (selected.isAfter(lastDate)) return lastDate;
  return selected;
}
