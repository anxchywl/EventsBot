import 'dart:io';

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
  // Development fallback only (never reached in release builds).
  return Platform.isAndroid
      ? 'http://192.168.0.154:8000'
      : 'http://127.0.0.1:8000';
}
