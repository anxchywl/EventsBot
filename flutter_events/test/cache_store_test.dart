import 'dart:async';
import 'dart:convert';

import 'package:events_feature/core/auth_store.dart';
import 'package:events_feature/core/cache_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('CacheTtl policy invariants', () {
    test('pending TTL is shorter than the approved/my SWR windows', () {
      // the review queue is time-critical: a poll tick must reach the network
      // sooner for pending than for the stale-while-revalidate feeds
      expect(CacheTtl.pending, lessThan(CacheTtl.approved));
      expect(CacheTtl.pending, lessThan(CacheTtl.myEvents));
    });

    test('categories are cached far longer than volatile feeds', () {
      expect(CacheTtl.categories, greaterThan(CacheTtl.approved));
      expect(CacheTtl.categories, greaterThan(CacheTtl.analytics));
    });
  });

  group('AnalyticsCache', () {
    setUp(AnalyticsCache.instance.clear);

    test(
      'reuses a fresh cached value without calling the loader again',
      () async {
        var calls = 0;
        Future<int> loader() async {
          calls++;
          return 100;
        }

        final first = await AnalyticsCache.instance.get('summary', loader);
        final second = await AnalyticsCache.instance.get('summary', loader);

        expect(first, 100);
        expect(second, 100);
        // second read is served from cache
        expect(calls, 1);
      },
    );

    test(
      'fresh values can be read synchronously for cache-aware loading',
      () async {
        expect(AnalyticsCache.instance.peekFresh<int>('summary'), isNull);

        await AnalyticsCache.instance.get('summary', () async => 100);

        expect(AnalyticsCache.instance.peekFresh<int>('summary'), 100);
        AnalyticsCache.instance.clear();
        expect(AnalyticsCache.instance.peekFresh<int>('summary'), isNull);
      },
    );

    test('deduplicates concurrent loads for the same key', () async {
      var calls = 0;
      final completer = Completer<int>();
      Future<int> loader() {
        calls++;
        return completer.future;
      }

      final a = AnalyticsCache.instance.get('k', loader);
      final b = AnalyticsCache.instance.get('k', loader);
      completer.complete(7);

      expect(await a, 7);
      expect(await b, 7);
      // both callers shared one in-flight future
      expect(calls, 1);
    });

    test('clear forces the next read to reload', () async {
      var calls = 0;
      Future<int> loader() async {
        calls++;
        return calls;
      }

      expect(await AnalyticsCache.instance.get('k', loader), 1);
      AnalyticsCache.instance.clear();
      expect(await AnalyticsCache.instance.get('k', loader), 2);
      expect(calls, 2);
    });

    test('distinct keys cache independently', () async {
      final a = await AnalyticsCache.instance.get('a', () async => 1);
      final b = await AnalyticsCache.instance.get('b', () async => 2);
      expect(a, 1);
      expect(b, 2);
    });
  });

  group('AnalyticsCache revalidate + targeted invalidation', () {
    setUp(AnalyticsCache.instance.clear);

    test(
      'revalidate bypasses freshness so a scheduled poll can obtain newer data',
      () async {
        var calls = 0;
        Future<int> loader() async => ++calls;

        expect(
          await AnalyticsCache.instance.get(
            'summary|k',
            loader,
            tag: AnalyticsTags.summary,
          ),
          1,
        );
        // a still-fresh get reuses the cache — this is the poll-⊂-ttl trap the
        // old design fell into and skipped the network
        expect(
          await AnalyticsCache.instance.get(
            'summary|k',
            loader,
            tag: AnalyticsTags.summary,
          ),
          1,
        );
        expect(calls, 1);

        // revalidate ignores freshness and actually fetches again
        expect(
          await AnalyticsCache.instance.revalidate(
            'summary|k',
            loader,
            tag: AnalyticsTags.summary,
          ),
          2,
        );
        expect(calls, 2);
      },
    );

    test(
      'bumpTag stales only its own entries and wakes only its listeners',
      () async {
        await AnalyticsCache.instance.get(
          'summary|k',
          () async => 1,
          tag: AnalyticsTags.summary,
        );
        await AnalyticsCache.instance.get(
          'ratings|k',
          () async => 2,
          tag: AnalyticsTags.ratings,
        );

        var summaryTicks = 0;
        var ratingsTicks = 0;
        void onSummary() => summaryTicks++;
        void onRatings() => ratingsTicks++;
        AnalyticsCache.instance
            .tagListenable(AnalyticsTags.summary)
            .addListener(onSummary);
        AnalyticsCache.instance
            .tagListenable(AnalyticsTags.ratings)
            .addListener(onRatings);
        addTearDown(() {
          AnalyticsCache.instance
              .tagListenable(AnalyticsTags.summary)
              .removeListener(onSummary);
          AnalyticsCache.instance
              .tagListenable(AnalyticsTags.ratings)
              .removeListener(onRatings);
        });

        AnalyticsCache.instance.bumpTag(AnalyticsTags.summary);

        // only the summary panel is woken
        expect(summaryTicks, 1);
        expect(ratingsTicks, 0);
        // summary went stale, ratings stayed fresh
        expect(AnalyticsCache.instance.peekFresh<int>('summary|k'), isNull);
        expect(AnalyticsCache.instance.peekFresh<int>('ratings|k'), 2);
        // the last summary value is still peekable for an offline paint
        expect(AnalyticsCache.instance.peek<int>('summary|k'), 1);
      },
    );

    test('metric→tag map routes a view away from ratings/moderation', () {
      final view = AnalyticsTags.forMetric('open');
      expect(view, contains(AnalyticsTags.engagement));
      expect(view, contains(AnalyticsTags.summary));
      expect(view, isNot(contains(AnalyticsTags.ratings)));
      expect(view, isNot(contains(AnalyticsTags.moderation)));

      final rating = AnalyticsTags.forMetric('rating');
      expect(rating, contains(AnalyticsTags.ratings));
      expect(rating, isNot(contains(AnalyticsTags.moderation)));

      final status = AnalyticsTags.forMetric('status');
      expect(status, contains(AnalyticsTags.moderation));
      expect(status, contains(AnalyticsTags.picker));
    });
  });

  group('AnalyticsCache offline snapshot + session isolation', () {
    setUp(() {
      TestWidgetsFlutterBinding.ensureInitialized();
    });

    test(
      'persists a default-view snapshot and restores it after a cold start',
      () async {
        SharedPreferences.setMockInitialValues({
          'cache_schema_version': 1,
          'auth_user_id': 7,
        });
        await AuthStore.init();
        await CacheStore.init();
        AnalyticsCache.instance.clear();

        AnalyticsCache.instance.writeSnapshot('summary', {
          'metrics': {'total_events': 5},
        });
        // let the fire-and-forget persist reach the store, then simulate a cold
        // start by dropping in-memory state
        await Future<void>.delayed(const Duration(milliseconds: 30));
        AnalyticsCache.instance.clear();

        final raw = AnalyticsCache.instance.readSnapshot('summary');
        expect(raw, isNotNull);
        expect((raw as Map)['metrics']['total_events'], 5);
      },
    );

    test("never surfaces another account's snapshot", () async {
      final foreign = jsonEncode({
        'user_id': 7,
        'panels': {
          'summary': {
            'ts': 1,
            'data': {
              'metrics': {'total_events': 5},
            },
          },
        },
      });
      // a different account (8) signs in on the same device, disk still holds 7
      SharedPreferences.setMockInitialValues({
        'cache_schema_version': 1,
        'auth_user_id': 8,
        'cache_analytics_snapshot': foreign,
      });
      await AuthStore.init();
      await CacheStore.init();
      AnalyticsCache.instance.clear();

      expect(AnalyticsCache.instance.readSnapshot('summary'), isNull);
    });

    test(
      'a load in flight when the session is cleared never lands in the new cache',
      () async {
        SharedPreferences.setMockInitialValues({'cache_schema_version': 1});
        await CacheStore.init();
        AnalyticsCache.instance.clear();

        final completer = Completer<int>();
        final inflight = AnalyticsCache.instance.get(
          'k',
          () => completer.future,
          tag: AnalyticsTags.summary,
        );
        await CacheStore.clearAll(); // account switch: bumps the generation
        completer.complete(42);

        expect(await inflight, 42); // the caller still receives its own result
        // but it must not pollute the next user's cache
        expect(AnalyticsCache.instance.peek<int>('k'), isNull);
      },
    );
  });
}
