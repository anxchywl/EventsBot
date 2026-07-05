import 'dart:io';

/// Base URL for the FastAPI backend. This is the single source of truth —
/// every API call builds its URI from this constant.
final String kBaseUrl = Platform.isAndroid ? 'http://192.168.0.154:8000' : 'http://127.0.0.1:8000';
