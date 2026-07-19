import 'dart:math';

import 'package:events_feature/features/submit/event_form_validation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('event request IDs are valid opaque 128-bit values', () {
    final requestId = createEventRequestId(random: Random(1));
    expect(requestId, hasLength(32));
    expect(requestId, matches(RegExp(r'^[a-f0-9]{32}$')));
  });

  group('event text validation', () {
    test('rejects blank and control-only required values', () {
      expect(
        validateRequiredEventText(
          '   ',
          maxLength: 100,
          emptyMessage: 'required',
          fieldName: 'Title',
        ),
        'required',
      );
      expect(
        validateRequiredEventText(
          'Valid\u0000Title',
          maxLength: 100,
          emptyMessage: 'required',
          fieldName: 'Title',
        ),
        contains('unsupported'),
      );
    });

    test('accepts emojis and counts Unicode code points', () {
      expect(
        validateRequiredEventText(
          List.filled(100, '🎓').join(),
          maxLength: 100,
          emptyMessage: 'required',
          fieldName: 'Title',
        ),
        isNull,
      );
      expect(
        validateRequiredEventText(
          List.filled(101, '🎓').join(),
          maxLength: 100,
          emptyMessage: 'required',
          fieldName: 'Title',
        ),
        contains('100'),
      );
    });

    test('allows line breaks only in multiline fields', () {
      expect(
        validateRequiredEventText(
          'Line one\nLine two',
          maxLength: 100,
          emptyMessage: 'required',
          fieldName: 'Description',
          allowLineBreaks: true,
        ),
        isNull,
      );
      expect(
        validateRequiredEventText(
          'Room\nTwo',
          maxLength: 100,
          emptyMessage: 'required',
          fieldName: 'Location',
        ),
        isNotNull,
      );
    });
  });

  group('event schedule validation', () {
    final now = DateTime(2026, 7, 19, 14, 30);

    test('rejects past dates', () {
      expect(
        validateEventDate(
          DateTime(2026, 7, 18),
          now: now,
          missingMessage: 'missing',
        ),
        contains('past'),
      );
      expect(
        validateEventDate(
          DateTime(2026, 7, 19),
          now: now,
          missingMessage: 'missing',
        ),
        isNull,
      );
    });

    test('requires a later start minute for events today', () {
      expect(
        validateEventStartTime(
          date: now,
          startTime: const TimeOfDay(hour: 14, minute: 30),
          now: now,
          missingMessage: 'missing',
        ),
        isNotNull,
      );
      expect(
        validateEventStartTime(
          date: now,
          startTime: const TimeOfDay(hour: 14, minute: 31),
          now: now,
          missingMessage: 'missing',
        ),
        isNull,
      );
    });

    test('requires end time to be strictly after start time', () {
      expect(
        validateEventEndTime(
          startTime: const TimeOfDay(hour: 18, minute: 0),
          endTime: const TimeOfDay(hour: 18, minute: 0),
          missingMessage: 'missing',
        ),
        isNotNull,
      );
      expect(
        validateEventEndTime(
          startTime: const TimeOfDay(hour: 18, minute: 0),
          endTime: const TimeOfDay(hour: 19, minute: 0),
          missingMessage: 'missing',
        ),
        isNull,
      );
    });

    test('clamps stale edit dates into the picker range', () {
      final first = DateTime(2026, 7, 19);
      final last = DateTime(2027, 7, 19);
      expect(
        clampEventPickerDate(
          DateTime(2025, 1, 1),
          firstDate: first,
          lastDate: last,
        ),
        first,
      );
      expect(
        clampEventPickerDate(
          DateTime(2028, 1, 1),
          firstDate: first,
          lastDate: last,
        ),
        last,
      );
    });
  });

  group('registration URL validation', () {
    test('accepts explicit http and https links', () {
      expect(
        validateEventRegistrationUrl('https://events.example.edu/a'),
        isNull,
      );
      expect(validateEventRegistrationUrl('http://127.0.0.1:8080/a'), isNull);
    });

    test('rejects unsafe, relative, and whitespace-containing links', () {
      expect(validateEventRegistrationUrl('javascript:alert(1)'), isNotNull);
      expect(validateEventRegistrationUrl('/register'), isNotNull);
      expect(
        validateEventRegistrationUrl('https://events.example.edu/a b'),
        isNotNull,
      );
    });
  });
}
