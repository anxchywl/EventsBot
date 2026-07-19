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
  static final ValueNotifier<int> _expiryRevision = ValueNotifier<int>(0);

  static String? _token;
  static String? _role;
  static String? _firstName;
  static int? _userId;

  static ValueListenable<int> get sessionChanges => _sessionRevision;
  static ValueListenable<int> get sessionExpiryChanges => _expiryRevision;

  static Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
    _token = _prefs.getString(_kToken);
    _role = _prefs.getString(_kRole);
    _firstName = _prefs.getString(_kFirstName);
    _userId = _prefs.getInt(_kUserId);
  }

  static bool get isLoggedIn => (_token ?? '').isNotEmpty;

  static bool get isAdmin => role == 'admin';

  static String? get token => _token;

  static String? get role => _role;

  static String? get firstName => _firstName;

  static int? get userId => _userId;

  static Future<void> save({
    required String token,
    required String role,
    String? firstName,
    required int userId,
    bool persist = true,
  }) async {
    final normalizedRole = role == 'admin' ? 'admin' : 'user';
    final accessChanged = _userId != userId || _role != normalizedRole;
    if (accessChanged) {
      _clearMemory();
      await Future.wait([_clearPersistedSession(), CacheStore.clearAll()]);
    }

    _token = token;
    _role = normalizedRole;
    _firstName = firstName;
    _userId = userId;
    if (persist) {
      await Future.wait([
        _prefs.setString(_kToken, token),
        _prefs.setString(_kRole, normalizedRole),
        _prefs.setInt(_kUserId, userId),
      ]);
      if (firstName == null) {
        await _prefs.remove(_kFirstName);
      } else {
        await _prefs.setString(_kFirstName, firstName);
      }
    } else {
      await _clearPersistedSession();
    }
    CacheStore.reconnectRealtime();
    _sessionRevision.value++;
  }

  static Future<bool> expireIfCurrent(String expiredToken) async {
    if (_token != expiredToken) return false;
    _clearMemory();
    _sessionRevision.value++;
    _expiryRevision.value++;
    await Future.wait([_clearPersistedSession(), CacheStore.clearAll()]);
    return true;
  }

  static Future<void> clear() async {
    _clearMemory();
    _sessionRevision.value++;
    await Future.wait([_clearPersistedSession(), CacheStore.clearAll()]);
  }

  static void _clearMemory() {
    _token = null;
    _role = null;
    _firstName = null;
    _userId = null;
  }

  static Future<void> _clearPersistedSession() async {
    await Future.wait([
      _prefs.remove(_kToken),
      _prefs.remove(_kRole),
      _prefs.remove(_kFirstName),
      _prefs.remove(_kUserId),
    ]);
  }
}
