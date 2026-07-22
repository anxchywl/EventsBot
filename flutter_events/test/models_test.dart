import 'package:events_feature/models/analytics_model.dart';
import 'package:events_feature/models/category_model.dart';
import 'package:events_feature/models/event_model.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _eventJson({
  String? coverUrl,
  String status = 'approved',
  String? endTime = '20:00',
}) {
  return {
    'id': 42,
    'public_token': 'tok-42',
    'title': 'Robotics Night',
    'description': 'Come build robots',
    'event_date': '2026-05-01',
    'event_time': '18:00',
    'event_end_time': endTime,
    'location': 'Block C',
    'category': 'Tech',
    'organizer_name': 'Robotics Club',
    'status': status,
    'cover_url': coverUrl,
    'it_equipment': null,
    'materials': null,
    'registration_url': null,
    'moderation_note': null,
    'submitted_at': '2026-01-01T00:00:00+00:00',
  };
}

void main() {
  group('EventModel', () {
    test('parses core fields from backend json', () {
      final event = EventModel.fromJson(_eventJson());
      expect(event.id, 42);
      expect(event.publicToken, 'tok-42');
      expect(event.eventTime, '18:00');
      expect(event.eventEndTime, '20:00');
      expect(event.category, 'Tech');
    });

    test('null end time and cover stay null', () {
      final event = EventModel.fromJson(_eventJson(endTime: null));
      expect(event.eventEndTime, isNull);
      expect(event.coverUrl, isNull);
    });

    test('absolute cover url is left untouched and round-trips', () {
      const absolute = 'https://cdn.example.com/cover.jpg';
      final event = EventModel.fromJson(_eventJson(coverUrl: absolute));
      expect(event.coverUrl, absolute);
      // toJson -> fromJson must be stable so a cached event survives a restart
      final roundTripped = EventModel.fromJson(event.toJson());
      expect(roundTripped.coverUrl, absolute);
      expect(roundTripped.toJson(), event.toJson());
    });

    test('relative cover url is resolved to an absolute url', () {
      final event = EventModel.fromJson(
        _eventJson(coverUrl: '/api/events/tok-42/cover'),
      );
      expect(event.coverUrl, contains('/api/events/tok-42/cover'));
      // once resolved it begins with a scheme, so re-resolving on restore is a
      // no-op and the value does not get double-prefixed
      final roundTripped = EventModel.fromJson(event.toJson());
      expect(roundTripped.coverUrl, event.coverUrl);
    });

    test('versioned cover url preserves the ?v query and re-keys on change', () {
      // the ?v=<poster_file_id> version is what busts a stale image on a cover
      // replacement; it must survive resolution and the persistence round-trip
      final v1 = EventModel.fromJson(
        _eventJson(coverUrl: '/api/events/tok-42/cover?v=fid-old'),
      );
      expect(v1.coverUrl, contains('v=fid-old'));
      final restored = EventModel.fromJson(v1.toJson());
      expect(restored.coverUrl, v1.coverUrl);

      // a replaced cover arrives with a new file id -> a different URL string,
      // so Image.network treats it as a new image instead of reusing the cache
      final v2 = EventModel.fromJson(
        _eventJson(coverUrl: '/api/events/tok-42/cover?v=fid-new'),
      );
      expect(v2.coverUrl, isNot(v1.coverUrl));
    });

    test('removed cover leaves coverUrl null after a round-trip', () {
      final removed = EventModel.fromJson(_eventJson());
      expect(removed.coverUrl, isNull);
      expect(EventModel.fromJson(removed.toJson()).coverUrl, isNull);
    });

    test('status helpers reflect the raw status string', () {
      expect(
        EventModel.fromJson(_eventJson(status: 'approved')).isApproved,
        isTrue,
      );
      expect(
        EventModel.fromJson(_eventJson(status: 'pending')).isPending,
        isTrue,
      );
      expect(
        EventModel.fromJson(_eventJson(status: 'needs_changes')).isNeedsChanges,
        isTrue,
      );
      expect(
        EventModel.fromJson(_eventJson(status: 'resubmitted')).isResubmitted,
        isTrue,
      );
      expect(
        EventModel.fromJson(_eventJson(status: 'pending')).isApproved,
        isFalse,
      );
    });
  });

  group('CategoryModel', () {
    test('parses id, name and slug', () {
      final category = CategoryModel.fromJson({
        'id': 3,
        'name': 'Career',
        'slug': 'career',
      });
      expect(category.id, 3);
      expect(category.name, 'Career');
      expect(category.slug, 'career');
    });
  });

  group('Analytics models', () {
    test('AnalyticsSummary tolerates a missing metrics map', () {
      final summary = AnalyticsSummary.fromJson({});
      expect(summary.metrics, isEmpty);
      expect(summary['total_events'], isNull);
    });

    test('AnalyticsSummary exposes numeric metrics by key', () {
      final summary = AnalyticsSummary.fromJson({
        'metrics': {
          'total_events': 12,
          'average_event_rating': 4.5,
          'nullable': null,
        },
      });
      expect(summary['total_events'], 12);
      expect(summary['average_event_rating'], 4.5);
      expect(summary['nullable'], isNull);
    });

    test('RankedEvent coerces integer value to double', () {
      final ranked = RankedEvent.fromJson({
        'event_id': 7,
        'title': 'Gala',
        'value': 3,
        'count': 10,
      });
      expect(ranked.eventId, 7);
      expect(ranked.value, 3.0);
      expect(ranked.count, 10);
    });
  });
}
