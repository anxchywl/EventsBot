import 'package:shared_preferences/shared_preferences.dart';

/// Persistent store for the authenticated Flutter session, backed by
/// SharedPreferences. Loaded once at startup via [init].
class AuthStore {
  AuthStore._();

  static const String _kToken = 'auth_token';
  static const String _kRole = 'auth_role';
  static const String _kFirstName = 'auth_first_name';
  static const String _kUserId = 'auth_user_id';

  static late SharedPreferences _prefs;

  static Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
  }

  static bool get isLoggedIn => (_prefs.getString(_kToken) ?? '').isNotEmpty;

  static bool get isModerator {
    final r = role;
    return r == 'admin' || r == 'moderator';
  }

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
    await _prefs.setString(_kToken, token);
    await _prefs.setString(_kRole, role);
    await _prefs.setInt(_kUserId, userId);
    if (firstName == null) {
      await _prefs.remove(_kFirstName);
    } else {
      await _prefs.setString(_kFirstName, firstName);
    }
  }

  static Future<void> clear() async {
    await _prefs.remove(_kToken);
    await _prefs.remove(_kRole);
    await _prefs.remove(_kFirstName);
    await _prefs.remove(_kUserId);
  }
}
