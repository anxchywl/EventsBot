import 'dart:async';

import 'package:events_feature/core/cache_store.dart';
import 'package:flutter_test/flutter_test.dart';

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

    test('reuses a fresh cached value without calling the loader again',
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
    });

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
}
