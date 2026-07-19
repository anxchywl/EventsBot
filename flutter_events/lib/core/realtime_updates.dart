import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'auth_store.dart';
import 'constants.dart';

class RealtimeUpdate {
  const RealtimeUpdate({required this.type, required this.data});

  final String type;
  final Map<String, dynamic> data;
}

class RealtimeUpdates {
  RealtimeUpdates._();

  static final instance = RealtimeUpdates._();

  final _controller = StreamController<RealtimeUpdate>.broadcast();
  HttpClient? _client;
  StreamSubscription<String>? _linesSub;
  Timer? _reconnectTimer;
  bool _connecting = false;
  bool _closed = false;

  // Capped exponential backoff so a persistent failure (server down, or a 401
  // from a stale token) does not reconnect in a tight 3 s loop. Reset to 0 once
  // a connection is established.
  int _reconnectAttempts = 0;
  static const Duration _baseBackoff = Duration(seconds: 3);
  static const Duration _maxBackoff = Duration(seconds: 60);

  Stream<RealtimeUpdate> get stream {
    ensureConnected();
    return _controller.stream;
  }

  void ensureConnected() {
    if (!_connecting &&
        _linesSub == null &&
        !(_reconnectTimer?.isActive ?? false)) {
      unawaited(_connect());
    }
  }

  Future<void> _connect() async {
    final token = AuthStore.token;
    if (token == null || token.isEmpty || _closed) return;
    _connecting = true;

    try {
      _client = HttpClient();
      final uri = Uri.parse('$kBaseUrl/api/flutter/events/updates');
      final request = await _client!.getUrl(uri);
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      final response = await request.close();
      if (response.statusCode == HttpStatus.unauthorized) {
        await response.drain<void>();
        await AuthStore.expireIfCurrent(token);
        return;
      }
      if (response.statusCode != HttpStatus.ok) {
        _scheduleReconnect();
        return;
      }

      // Connected: clear the backoff so the next drop retries promptly.
      _reconnectAttempts = 0;

      String? eventType;
      _linesSub = response
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen(
            (line) {
              if (line.startsWith('event:')) {
                eventType = line.substring(6).trim();
                return;
              }
              if (!line.startsWith('data:') || eventType == null) return;

              final decoded = jsonDecode(line.substring(5).trim());
              if (decoded is Map<String, dynamic>) {
                _controller.add(
                  RealtimeUpdate(type: eventType!, data: decoded),
                );
              }
            },
            onDone: _scheduleReconnect,
            onError: (_) => _scheduleReconnect(),
            cancelOnError: true,
          );
    } catch (_) {
      _scheduleReconnect();
    } finally {
      _connecting = false;
    }
  }

  void _scheduleReconnect() {
    _linesSub?.cancel();
    _linesSub = null;
    _client?.close(force: true);
    _client = null;
    if (_closed || (_reconnectTimer?.isActive ?? false)) return;

    final backoffMs = (_baseBackoff.inMilliseconds * (1 << _reconnectAttempts))
        .clamp(_baseBackoff.inMilliseconds, _maxBackoff.inMilliseconds);
    if (_reconnectAttempts < 8) _reconnectAttempts++;

    _reconnectTimer = Timer(Duration(milliseconds: backoffMs), () {
      _reconnectTimer = null;
      if (_closed || _linesSub != null || _connecting) return;
      unawaited(_connect());
    });
  }

  Future<void> disconnect() async {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _linesSub?.cancel();
    _linesSub = null;
    _client?.close(force: true);
    _client = null;
    _reconnectAttempts = 0;
  }

  Future<void> close() async {
    _closed = true;
    await disconnect();
    await _controller.close();
  }
}
