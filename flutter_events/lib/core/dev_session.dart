import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'auth_store.dart';
import 'exceptions.dart';

const bool _standaloneDevAccessRequested = bool.fromEnvironment(
  'ENABLE_STANDALONE_DEV_ACCESS',
  defaultValue: true,
);

class DevSessionConfig {
  const DevSessionConfig._();

  static bool get isEnabled => developmentAccessAllowed(
    isDebugMode: kDebugMode,
    requested: _standaloneDevAccessRequested,
  );
}

@visibleForTesting
bool developmentAccessAllowed({
  required bool isDebugMode,
  required bool requested,
}) => isDebugMode && requested;

/// No-login test flow. The app ships without a login/registration screen; it
/// silently signs into a shared test account on first launch, and the 5-tap
/// gesture on the Events tab swaps between the user and admin test accounts so
/// both shells can be exercised with real, role-correct backend tokens.
///
/// Each account is logged in AT MOST ONCE — the resulting JWT is cached and
/// reused. Switching roles just re-activates the cached token, so rapid
/// toggling never hammers the rate-limited /auth/login endpoint.
///
/// Credentials can be overridden at build time, e.g.
///   flutter build apk --dart-define=TEST_USER_EMAIL=... --dart-define=...
const String _userEmail = String.fromEnvironment(
  'TEST_USER_EMAIL',
  defaultValue: 'user@events.dev',
);
const String _userPassword = String.fromEnvironment(
  'TEST_USER_PASSWORD',
  defaultValue: 'UserPass123',
);
const String _adminEmail = String.fromEnvironment(
  'TEST_ADMIN_EMAIL',
  defaultValue: 'admin@events.dev',
);
const String _adminPassword = String.fromEnvironment(
  'TEST_ADMIN_PASSWORD',
  defaultValue: 'AdminPass123',
);

String _cacheKey(String role) => 'dev_session_$role';

/// Ensures a session exists. Activates a cached user session, or signs into the
/// user test account once. Best-effort: failures (offline / server down) are
/// swallowed so the app still opens; screens surface their own load errors.
Future<void> ensureDevSession() async {
  if (!DevSessionConfig.isEnabled) return;
  try {
    if (AuthStore.isLoggedIn) {
      final token = AuthStore.token!;
      try {
        final profile = await bootstrapSession(token);
        await AuthStore.save(
          token: token,
          role: profile.role,
          firstName: profile.firstName,
          userId: profile.userId,
        );
        return;
      } on UnauthorizedException {
        await AuthStore.clear();
      } on ForbiddenException {
        await AuthStore.clear();
      } on NetworkException {
        return;
      }
    }
    await _activate(await _obtainSession('user'));
  } catch (_) {
    // ignore — open the app anyway
  }
}

/// Swaps between the user and admin test accounts (5-tap role switch). Uses the
/// cached token for the target role when available, so it does not re-login on
/// every switch.
Future<void> cycleDevRole() async {
  if (!DevSessionConfig.isEnabled) {
    throw StateError('Development role switching is disabled');
  }
  final targetRole = AuthStore.isAdmin ? 'user' : 'admin';
  await _activate(await _obtainSession(targetRole));
}

/// Returns a session for [role], reusing a cached token or logging in once.
Future<AuthResult> _obtainSession(String role) async {
  final prefs = await SharedPreferences.getInstance();
  final cached = prefs.getString(_cacheKey(role));
  if (cached != null) {
    try {
      final map = jsonDecode(cached) as Map<String, dynamic>;
      final token = map['token'] as String;
      try {
        final profile = await bootstrapSession(token);
        return AuthResult(
          token: token,
          role: profile.role,
          firstName: profile.firstName,
          userId: profile.userId,
          isVerified: profile.isVerified,
        );
      } on UnauthorizedException {
        await prefs.remove(_cacheKey(role));
      } on ForbiddenException {
        await prefs.remove(_cacheKey(role));
      } on NetworkException {
        return AuthResult(
          token: token,
          role: map['role'] as String,
          firstName: map['first_name'] as String?,
          userId: map['user_id'] as int,
          isVerified: (map['is_verified'] as bool?) ?? false,
        );
      }
    } catch (_) {
      // fall through to a fresh login if the cache is corrupt
    }
  }

  final (email, password) = role == 'admin'
      ? (_adminEmail, _adminPassword)
      : (_userEmail, _userPassword);
  final result = await login(email, password);
  await prefs.setString(
    _cacheKey(result.role),
    jsonEncode({
      'token': result.token,
      'role': result.role,
      'first_name': result.firstName,
      'user_id': result.userId,
      'is_verified': result.isVerified,
    }),
  );
  return result;
}

Future<void> _activate(AuthResult result) async {
  await AuthStore.save(
    token: result.token,
    role: result.role,
    firstName: result.firstName,
    userId: result.userId,
  );
}
