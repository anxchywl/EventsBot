import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/category_model.dart';
import '../models/event_model.dart';
import 'api_client.dart';
import 'realtime_updates.dart';

/// Named cache lifetimes. Every per-endpoint policy is expressed here so the
/// caching strategy is auditable in one place and no TTL magic-number leaks
/// into a screen.
///
///  - [pending]  is deliberately shorter than the 20 s coordinator poll so a
///    tick that lands after it always hits the network (the queue is
///    time-critical).
///  - [approved] / [myEvents] follow stale-while-revalidate: rendered instantly
///    from disk, revalidated in the background.
///  - [categories] change rarely, so a long session-scoped TTL is plenty.
///  - [analytics] matches the 30 s analytics poll so a tick reuses the last
///    response instead of recomputing it server-side.
class CacheTtl {
  const CacheTtl._();

  static const Duration pending = Duration(seconds: 15);
  static const Duration approved = Duration(seconds: 45);
  static const Duration myEvents = Duration(seconds: 45);
  static const Duration categories = Duration(hours: 6);
  static const Duration analytics = Duration(seconds: 35);

  /// Cached data older than this is surfaced with a non-intrusive staleness
  /// hint when a background refresh cannot complete (offline).
  static const Duration stalenessThreshold = Duration(minutes: 10);
}

/// Bumped whenever the persisted cache layout changes in a way that would make
/// old entries undeserialisable. On mismatch the whole cache is discarded.
const int _kSchemaVersion = 1;

/// Owns the shared [SharedPreferences] handle, the cache schema version and the
/// global generation counter. A single store initialised in `main()` alongside
/// [AuthStore] backs both [EventCache] and [AnalyticsCache].
class CacheStore {
  CacheStore._();

  static const String _kSchemaKey = 'cache_schema_version';
  static const String _kPrefix = 'cache_';

  static late SharedPreferences _prefs;

  /// Incremented on every [clearAll]. A fetch captures the generation when it
  /// starts and refuses to write its result if the generation moved on — this
  /// is how a request that was in flight during logout is discarded instead of
  /// leaking into the next user's cache.
  static int _generation = 0;
  static int get generation => _generation;

  static Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
    final stored = _prefs.getInt(_kSchemaKey);
    if (stored != _kSchemaVersion) {
      await _clearPrefs();
      await _prefs.setInt(_kSchemaKey, _kSchemaVersion);
    }
    EventCache.instance.restore();
  }

  /// Wipe everything on logout / user switch and bump the generation so any
  /// in-flight fetch started under the previous user is discarded on arrival.
  static Future<void> clearAll() async {
    _generation++;
    await RealtimeUpdates.instance.disconnect();
    EventCache.instance.clearForLogout();
    AnalyticsCache.instance.clear();
    await _clearPrefs();
    await _prefs.setInt(_kSchemaKey, _kSchemaVersion);
  }

  static Future<void> _clearPrefs() async {
    for (final key in _prefs.getKeys().toList()) {
      if (key.startsWith(_kPrefix)) await _prefs.remove(key);
    }
  }

  /// Best-effort async write. A failed / interrupted write must never crash the
  /// app — the in-memory cache stays authoritative until the next successful
  /// persist.
  static void write(String key, Object json) {
    () async {
      try {
        await _prefs.setString(key, jsonEncode(json));
      } catch (_) {
        // Swallow: persistence is a nice-to-have, not a correctness guarantee.
      }
    }();
  }

  static void reconnectRealtime() {
    RealtimeUpdates.instance.ensureConnected();
  }

  /// Reads and decodes a JSON map. Any corruption / schema drift discards the
  /// entry rather than throwing.
  static Map<String, dynamic>? readMap(String key) {
    try {
      final raw = _prefs.getString(key);
      if (raw == null) return null;
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      _prefs.remove(key);
      return null;
    }
  }
}

/// One cached event list: the ordered ids (events themselves live in the shared
/// [EventCache] map) plus when it was last fetched.
class _ListState {
  _ListState(this.ids, this.fetchedAt);

  List<int> ids;
  DateTime fetchedAt;

  bool isFresh(Duration ttl) => DateTime.now().difference(fetchedAt) < ttl;

  Map<String, dynamic> toJson() => {
    'ids': ids,
    'ts': fetchedAt.millisecondsSinceEpoch,
  };

  static _ListState? fromJson(Map<String, dynamic> json) {
    try {
      final ids = (json['ids'] as List).map((e) => e as int).toList();
      final ts = DateTime.fromMillisecondsSinceEpoch(json['ts'] as int);
      return _ListState(ids, ts);
    } catch (_) {
      return null;
    }
  }
}

/// The one place event data is cached. A single [EventModel] never lives in more
/// than one collection: the canonical objects sit in [_events] keyed by id and
/// every list ([_lists]) and the detail screen reference them by id. A status
/// change patched into the map is therefore instantly visible everywhere.
///
/// Extends [ChangeNotifier] so screens can subscribe once and re-render the
/// affected rows whenever the cache mutates (from a mutation, a poll or an SSE
/// event) — no caching logic lives in the widgets themselves.
class EventCache extends ChangeNotifier {
  EventCache._();

  static final EventCache instance = EventCache._();

  final Map<int, EventModel> _events = {};
  final Map<String, _ListState> _lists = {};

  // In-flight de-duplication: a second request for the same key returns the
  // Future already running instead of firing another network call.
  final Map<String, Future<List<EventModel>>> _listInFlight = {};
  final Map<int, Future<EventModel>> _eventInFlight = {};

  List<CategoryModel>? _categories;
  DateTime? _categoriesAt;
  Future<List<CategoryModel>>? _categoriesInFlight;

  StreamSubscription<RealtimeUpdate>? _sseSub;

  // Only default (unfiltered) lists survive an app restart. Filtered/searched
  // variants stay in memory only.
  static const String _kApproved = 'approved:';
  static const String _kMy = 'my';
  static const String _kPendingOpen = 'pending:false';
  static const String _kPendingRejected = 'pending:true';
  static const Set<String> _persistedLists = {
    _kApproved,
    _kMy,
    _kPendingOpen,
    _kPendingRejected,
  };

  String _approvedKey(String query) => 'approved:$query';
  String _pendingKey(bool includeRejected) => 'pending:$includeRejected';

  /// A pending event is still awaiting a coordinator decision. Anything else has
  /// left the default review queue.
  bool _isQueueStatus(String status) =>
      status == 'pending' ||
      status == 'needs_changes' ||
      status == 'resubmitted';

  // ── Realtime (SSE) ─────────────────────────────────────────────────────────

  /// Subscribe to the realtime stream once, from a post-login surface (AppShell).
  /// Handling SSE centrally means one `event_status_changed` patches the shared
  /// map a single time instead of every screen re-fetching independently.
  void attachRealtime() {
    _sseSub ??= RealtimeUpdates.instance.stream.listen(_onRealtimeUpdate);
  }

  void _onRealtimeUpdate(RealtimeUpdate update) {
    if (update.type == 'event_deleted') {
      final id = update.data['event_id'];
      if (id is int) {
        _removeEvent(id);
        _persistAll();
        notifyListeners();
      }
      return;
    }
    if (update.type != 'event_status_changed') return;
    final id = update.data['event_id'];
    if (id is! int) {
      // No id to target: fall back to marking the queues stale so the next poll
      // reconciles. We never blindly refetch a whole list from an SSE event.
      _markStale(_kPendingOpen);
      _markStale(_kPendingRejected);
      _markStale(_kApproved);
      notifyListeners();
      return;
    }
    final status = update.data['status'];
    unawaited(_patchFromRealtime(id, status is String ? status : null));
  }

  Future<void> _patchFromRealtime(int id, String? status) async {
    try {
      // Fetch only the affected event (de-duplicated) and patch it into the map;
      // every list containing it updates through the shared reference.
      await event(id, force: true);
    } catch (_) {
      // Offline / transient: leave the last known copy in place.
    }
    // Membership can shift (an approved event leaves the queue); drop it
    // optimistically and mark the lists stale so the next tick reconciles the
    // authoritative ordering without blanking anything now.
    if (status != null && !_isQueueStatus(status)) {
      _removeFromList(_kPendingOpen, id);
    }
    if (status != null && status != 'approved') {
      _removeFromApprovedLists(id);
    }
    _markStale(_kPendingOpen);
    _markStale(_kPendingRejected);
    _markStale(_kApproved);
    _persistAll();
    notifyListeners();
  }

  // ── Reads (synchronous peek) ─────────────────────────────────────────────

  List<EventModel>? peekApproved({String query = ''}) =>
      _peekList(_approvedKey(query));
  List<EventModel>? peekMy() => _peekList(_kMy);
  List<EventModel>? peekPending({bool includeRejected = false}) =>
      _peekList(_pendingKey(includeRejected));
  EventModel? peekEvent(int id) => _events[id];
  List<CategoryModel>? peekCategories() => _categories;

  List<EventModel>? _peekList(String key) {
    final state = _lists[key];
    if (state == null) return null;
    return [
      for (final id in state.ids)
        if (_events[id] != null) _events[id]!,
    ];
  }

  DateTime? fetchedAtApproved({String query = ''}) =>
      _lists[_approvedKey(query)]?.fetchedAt;
  DateTime? fetchedAtMy() => _lists[_kMy]?.fetchedAt;
  DateTime? fetchedAtPending({bool includeRejected = false}) =>
      _lists[_pendingKey(includeRejected)]?.fetchedAt;

  // ── Reads (stale-while-revalidate) ─────────────────────────────────────────

  /// Returns cached data untouched when it is still fresh (this is what lets a
  /// polling tick skip the network); otherwise fetches, patches the map and
  /// notifies. Throws only when there is nothing cached *and* the fetch fails.
  Future<List<EventModel>> approved({String query = '', bool force = false}) {
    final key = _approvedKey(query);
    if (!force && (_lists[key]?.isFresh(CacheTtl.approved) ?? false)) {
      return Future.value(_peekList(key)!);
    }
    return _refreshList(
      key,
      () => fetchApprovedEvents(search: query.isEmpty ? null : query),
    );
  }

  Future<List<EventModel>> my({bool force = false}) {
    if (!force && (_lists[_kMy]?.isFresh(CacheTtl.myEvents) ?? false)) {
      return Future.value(_peekList(_kMy)!);
    }
    return _refreshList(_kMy, fetchMyEvents);
  }

  Future<List<EventModel>> pending({
    bool includeRejected = false,
    bool force = false,
  }) {
    final key = _pendingKey(includeRejected);
    if (!force && (_lists[key]?.isFresh(CacheTtl.pending) ?? false)) {
      return Future.value(_peekList(key)!);
    }
    return _refreshList(
      key,
      () => fetchPendingEvents(includeRejected: includeRejected),
    );
  }

  Future<List<EventModel>> _refreshList(
    String key,
    Future<List<EventModel>> Function() fetch,
  ) {
    final existing = _listInFlight[key];
    if (existing != null) return existing;

    final generation = CacheStore.generation;
    final future = () async {
      try {
        final events = await fetch();
        if (generation != CacheStore.generation) {
          // User switched mid-flight: discard, don't pollute the new cache.
          return _peekList(key) ?? const <EventModel>[];
        }
        _absorb(events);
        _lists[key] = _ListState(
          events.map((e) => e.id).toList(),
          DateTime.now(),
        );
        _persistList(key);
        notifyListeners();
        return _peekList(key)!;
      } finally {
        _listInFlight.remove(key);
      }
    }();
    _listInFlight[key] = future;
    return future;
  }

  /// Cache-first single event. The detail screen renders from the map instantly
  /// and only forces a network read on an incoming SSE / mutation for its id.
  Future<EventModel> event(int id, {bool force = false}) {
    if (!force) {
      final cached = _events[id];
      if (cached != null) return Future.value(cached);
    }
    final existing = _eventInFlight[id];
    if (existing != null) return existing;

    final generation = CacheStore.generation;
    final future = () async {
      try {
        final fetched = await fetchEvent(id);
        if (generation == CacheStore.generation) {
          _events[id] = fetched;
          _persistEvents();
          notifyListeners();
        }
        return fetched;
      } finally {
        _eventInFlight.remove(id);
      }
    }();
    _eventInFlight[id] = future;
    return future;
  }

  /// Seed the map from an event handed in by a caller (e.g. the list row that
  /// opened the detail screen) so the detail view shares the canonical object.
  void seed(EventModel event) {
    _events.putIfAbsent(event.id, () => event);
  }

  Future<List<CategoryModel>> categories({bool force = false}) {
    final fresh =
        _categories != null &&
        _categoriesAt != null &&
        DateTime.now().difference(_categoriesAt!) < CacheTtl.categories;
    if (!force && fresh) return Future.value(_categories!);
    if (_categoriesInFlight != null) return _categoriesInFlight!;

    final generation = CacheStore.generation;
    final future = () async {
      try {
        final result = await fetchCategories();
        if (generation == CacheStore.generation) {
          _categories = result;
          _categoriesAt = DateTime.now();
          CacheStore.write('cache_categories', {
            'ts': _categoriesAt!.millisecondsSinceEpoch,
            'items': [
              for (final c in result)
                {'id': c.id, 'name': c.name, 'slug': c.slug},
            ],
          });
        }
        return result;
      } finally {
        _categoriesInFlight = null;
      }
    }();
    _categoriesInFlight = future;
    return future;
  }

  // ── Mutations (wrap api_client, invalidate exactly what changed) ────────────

  Future<EventModel> submit(Map<String, dynamic> body) async {
    final created = await submitEvent(body);
    _events[created.id] = created;
    // A new pending request affects the submitter's list and the review queues.
    _prependToList(_kMy, created.id);
    _markStale(_kMy);
    _markStale(_kPendingOpen);
    _persistAll();
    notifyListeners();
    return created;
  }

  Future<EventModel> resubmit(int id, Map<String, dynamic> fields) async {
    final updated = await resubmitEvent(id, fields);
    _events[updated.id] = updated;
    if (updated.id != id) {
      _prependToList(_kMy, updated.id);
    }
    _markStale(_kMy);
    _markStale(_kPendingOpen);
    _markStale(_kPendingRejected);
    AnalyticsCache.instance.clear();
    _persistAll();
    notifyListeners();
    return updated;
  }

  Future<EventModel> updateStatus(
    int id,
    String status,
    String? comment,
  ) async {
    final updated = await updateEventStatus(id, status, comment);
    if (updated.id != id) _removeEvent(id);
    _events[updated.id] = updated;
    if (!_isQueueStatus(updated.status)) {
      _removeFromList(_kPendingOpen, id);
    }
    if (updated.status != 'approved') {
      _removeFromApprovedLists(id);
    }
    _markStale(_kPendingOpen);
    _markStale(_kPendingRejected);
    _markStale(_kApproved);
    // Any status change moves the moderation / engagement / ratings counts.
    AnalyticsCache.instance.clear();
    _persistAll();
    notifyListeners();
    return updated;
  }

  Future<EventModel> cancel(int id, {String? comment}) async {
    final updated = await cancelEvent(id, comment: comment);
    _events[id] = updated;
    _removeFromList(_kPendingOpen, id);
    _removeFromApprovedLists(id);
    _markStale(_kMy);
    _markStale(_kPendingRejected);
    _markStale(_kApproved);
    AnalyticsCache.instance.clear();
    _persistAll();
    notifyListeners();
    return updated;
  }

  Future<void> delete(int id) async {
    await deleteEvent(id);
    _removeEvent(id);
    _markStale(_kMy);
    _markStale(_kPendingOpen);
    _markStale(_kPendingRejected);
    _markStale(_kApproved);
    AnalyticsCache.instance.clear();
    _persistAll();
    notifyListeners();
  }

  Future<EventModel> patch(int id, {String? endTime}) async {
    final updated = await patchEvent(id, endTime: endTime);
    _events[id] = updated;
    for (final key in _persistedLists) {
      if (_lists[key]?.ids.contains(id) ?? false) _markStale(key);
    }
    _persistAll();
    notifyListeners();
    return updated;
  }

  // ── Internal helpers ────────────────────────────────────────────────────

  void _absorb(Iterable<EventModel> events) {
    for (final e in events) {
      _events[e.id] = e;
    }
  }

  void _markStale(String key) {
    final state = _lists[key];
    if (state != null) {
      state.fetchedAt = DateTime.fromMillisecondsSinceEpoch(0);
    }
  }

  void _prependToList(String key, int id) {
    final state = _lists[key];
    if (state != null && !state.ids.contains(id)) state.ids.insert(0, id);
  }

  void _removeFromList(String key, int id) => _lists[key]?.ids.remove(id);

  void _removeFromApprovedLists(int id) {
    for (final entry in _lists.entries) {
      if (entry.key.startsWith('approved:')) entry.value.ids.remove(id);
    }
  }

  void _removeEvent(int id) {
    _events.remove(id);
    for (final state in _lists.values) {
      state.ids.remove(id);
    }
  }

  // ── Persistence ───────────────────────────────────────────────────────────

  void _persistList(String key) {
    if (!_persistedLists.contains(key)) return;
    final state = _lists[key];
    if (state != null) CacheStore.write('cache_list_$key', state.toJson());
    _persistEvents();
  }

  void _persistAll() {
    _persistEvents();
    for (final key in _persistedLists) {
      final state = _lists[key];
      if (state != null) CacheStore.write('cache_list_$key', state.toJson());
    }
  }

  void _persistEvents() {
    CacheStore.write('cache_events', {
      for (final e in _events.values) '${e.id}': e.toJson(),
    });
  }

  /// Rehydrate from disk at startup. Every entry is decoded defensively: a model
  /// field added or renamed since the entry was written makes [EventModel.fromJson]
  /// throw, and that single entry is dropped rather than crashing the app.
  void restore() {
    final eventsJson = CacheStore.readMap('cache_events');
    if (eventsJson != null) {
      eventsJson.forEach((_, value) {
        try {
          final event = EventModel.fromJson(value as Map<String, dynamic>);
          _events[event.id] = event;
        } catch (_) {
          // Discard the stale/undeserialisable entry; it will be refetched.
        }
      });
    }

    for (final key in _persistedLists) {
      final json = CacheStore.readMap('cache_list_$key');
      if (json == null) continue;
      final state = _ListState.fromJson(json);
      if (state == null) continue;
      // Drop ids whose event failed to deserialise so peeks stay consistent.
      state.ids = state.ids.where(_events.containsKey).toList();
      _lists[key] = state;
    }

    final categoriesJson = CacheStore.readMap('cache_categories');
    if (categoriesJson != null) {
      try {
        final items = (categoriesJson['items'] as List)
            .map((e) => CategoryModel.fromJson(e as Map<String, dynamic>))
            .toList();
        _categories = items;
        _categoriesAt = DateTime.fromMillisecondsSinceEpoch(
          categoriesJson['ts'] as int,
        );
      } catch (_) {
        _categories = null;
        _categoriesAt = null;
      }
    }
  }

  /// Drop everything from memory on logout. Persisted keys are wiped by
  /// [CacheStore.clearAll]; the generation bump (also there) neutralises any
  /// in-flight fetch.
  void clearForLogout() {
    _events.clear();
    _lists.clear();
    _listInFlight.clear();
    _eventInFlight.clear();
    _categories = null;
    _categoriesAt = null;
    _categoriesInFlight = null;
    notifyListeners();
  }
}

/// One cached analytics response with its fetch time.
class _AnalyticsEntry {
  _AnalyticsEntry(this.value, this.fetchedAt);

  final Object value;
  final DateTime fetchedAt;

  bool get isFresh => DateTime.now().difference(fetchedAt) < CacheTtl.analytics;
}

/// In-memory, coordinator-only cache for analytics panels. Not persisted: the
/// numbers are cheap to recompute and volatile. Keyed by the caller — the key
/// encodes the panel plus the stringified [AnalyticsFilters], so each filter
/// combination caches separately. Paginated / searched endpoints (the event
/// picker, ranking sheets, reviews) are never routed through here.
class AnalyticsCache {
  AnalyticsCache._();

  static final AnalyticsCache instance = AnalyticsCache._();

  final Map<String, _AnalyticsEntry> _entries = {};
  final Map<String, Future<dynamic>> _inFlight = {};

  /// Returns the cached value while fresh (so a poll tick reuses it), otherwise
  /// runs [loader] once — concurrent callers for the same key share the Future.
  Future<T> get<T>(String key, Future<T> Function() loader) {
    final entry = _entries[key];
    if (entry != null && entry.isFresh) {
      return Future.value(entry.value as T);
    }
    final existing = _inFlight[key];
    if (existing != null) return existing.then((v) => v as T);

    final generation = CacheStore.generation;
    final future = () async {
      try {
        final value = await loader();
        if (generation == CacheStore.generation) {
          _entries[key] = _AnalyticsEntry(value as Object, DateTime.now());
        }
        return value;
      } finally {
        _inFlight.remove(key);
      }
    }();
    _inFlight[key] = future;
    return future;
  }

  void clear() {
    _entries.clear();
    _inFlight.clear();
  }
}
