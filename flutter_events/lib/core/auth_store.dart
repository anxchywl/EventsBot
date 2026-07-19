import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'cache_store.dart';

/// Persistent store for the authenticated Flutter session, backed by
/// SharedPreferences. Loaded once at startup via [init].
class AuthStore {
  AuthStore._();

  static const String _kToken = 'auth_token';
  static const String _kRole = 'auth_role';
  static const String _kFirstName = 'auth_first_name';
  static const String _kUserId = 'auth_user_id';

  static late SharedPreferences _prefs;
  static final ValueNotifier<int> _sessionRevision = ValueNotifier<int>(0);

  static ValueListenable<int> get sessionChanges => _sessionRevision;

  static Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
  }

  static bool get isLoggedIn => (_prefs.getString(_kToken) ?? '').isNotEmpty;

  static bool get isAdmin => role == 'admin';

  static String? get token => _prefs.getString(_kToken);

  static String? get role => _prefs.getString(_kRole);

  static String? get firstName => _prefs.getString(_kFirstName);

  static int? get userId => _prefs.getInt(_kUserId);

  static Future<void> save({
    required String token,
    required String role,
    String? firstName,
    required int userId,
  }) async {
    // A different user signing in must never inherit the previous user's cached
    // events (e.g. if the last session was never explicitly logged out).
    if (_prefs.getInt(_kUserId) != userId) {
      await _prefs.remove(_kToken);
      await CacheStore.clearAll();
    }
    await _prefs.setString(_kToken, token);
    await _prefs.setString(_kRole, role == 'admin' ? 'admin' : 'user');
    await _prefs.setInt(_kUserId, userId);
    if (firstName == null) {
      await _prefs.remove(_kFirstName);
    } else {
      await _prefs.setString(_kFirstName, firstName);
    }
    CacheStore.reconnectRealtime();
    _sessionRevision.value++;
  }

  static Future<void> setRole(String role) async {
    final normalized = role == 'admin' ? 'admin' : 'user';
    // Coordinator (admin) and club-head (user) see disjoint datasets; drop the
    // cache so a role switch never shows the wrong shell's data.
    if (_prefs.getString(_kRole) != normalized) {
      await CacheStore.clearAll();
    }
    await _prefs.setString(_kRole, normalized);
    _sessionRevision.value++;
  }

  static Future<String> cycleTestRole() async {
    final nextRole = switch (role) {
      'admin' => 'user',
      _ => 'admin',
    };
    await setRole(nextRole);
    return nextRole;
  }

  static Future<void> clear() async {
    await _prefs.remove(_kToken);
    await CacheStore.clearAll();
    await _prefs.remove(_kRole);
    await _prefs.remove(_kFirstName);
    await _prefs.remove(_kUserId);
    _sessionRevision.value++;
  }
}
