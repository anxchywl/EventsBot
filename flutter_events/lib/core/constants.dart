import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';

/// Base URL for the FastAPI backend. This is the single source of truth —
/// every API call builds its URI from this constant.
///
/// Production/release builds MUST inject the real HTTPS endpoint at build time:
///
///   flutter build apk --dart-define=API_BASE_URL=https://events.nu.edu.kz
///
/// The plain-HTTP LAN addresses below are development-only fallbacks. Shipping
/// them in a release build would send bearer tokens over cleartext to a LAN IP
/// that does not exist in production, so a release build without the override
/// fails fast instead of leaking tokens on the network.
const String _kApiBaseUrlOverride = String.fromEnvironment('API_BASE_URL');

final String kBaseUrl = _resolveBaseUrl();

String _resolveBaseUrl() {
  if (_kApiBaseUrlOverride.isNotEmpty) {
    return _kApiBaseUrlOverride;
  }
  if (kReleaseMode) {
    throw StateError(
      'API_BASE_URL is not set. Release builds must pass '
      '--dart-define=API_BASE_URL=https://your-production-host',
    );
  }
  // Development fallback (debug): point at the LOCAL backend running in dev mode
  // (LOG_LEVEL=DEBUG + FLUTTER_NATIVE_AUTH_ENABLED=true), which the standalone
  // dev sign-in needs. Port 8001 because 8000 is taken locally by another app.
  // Android emulators reach the host via 10.0.2.2; iOS sim / macOS use localhost.
  // Override any time with --dart-define=API_BASE_URL=https://events.anxchywl.dev
  const localPort = 8001;
  if (!kIsWeb && Platform.isAndroid) return 'http://10.0.2.2:$localPort';
  return 'http://127.0.0.1:$localPort';
}
