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
const bool _releaseDevAccessRequested = bool.fromEnvironment(
  'ALLOW_RELEASE_DEV_ACCESS',
  defaultValue: false,
);

class DevSessionConfig {
  const DevSessionConfig._();

  static bool get isEnabled => developmentAccessAllowed(
    isDebugMode: kDebugMode,
    requested:
        _standaloneDevAccessRequested &&
        (kDebugMode || _releaseDevAccessRequested),
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
  final targetRole = AuthStore.isAdmin ? 'user' : 'admin';
  try {
    await _activate(await _obtainSession(targetRole));
  } catch (_) {
    // A failed role login must not discard the currently valid session.
    if (!AuthStore.isLoggedIn) await ensureDevSession();
    rethrow;
  }
}

/// Returns a session for [role], reusing a cached token or logging in once.
Future<AuthResult> _obtainSession(String role) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.remove(_cacheKey(role));

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
