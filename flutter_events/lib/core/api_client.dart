import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart' show MediaType;

import '../models/analytics_model.dart';
import '../models/category_model.dart';
import '../models/event_model.dart';
import 'auth_store.dart';
import 'constants.dart';
import 'exceptions.dart';

import 'localization.dart';

/// Result of a successful login or registration.
class AuthResult {
  final String token;
  final String role;
  final String? firstName;
  final int userId;
  final bool isVerified;

  const AuthResult({
    required this.token,
    required this.role,
    required this.firstName,
    required this.userId,
    required this.isVerified,
  });

  factory AuthResult.fromJson(Map<String, dynamic> json) {
    return AuthResult(
      token: json['token'] as String,
      role: json['role'] as String,
      firstName: json['first_name'] as String?,
      userId: json['user_id'] as int,
      isVerified: json['is_verified'] as bool,
    );
  }
}

class SessionProfile {
  const SessionProfile({
    required this.role,
    required this.firstName,
    required this.userId,
    required this.isVerified,
  });

  final String role;
  final String? firstName;
  final int userId;
  final bool isVerified;

  factory SessionProfile.fromJson(Map<String, dynamic> json) {
    return SessionProfile(
      role: json['role'] as String,
      firstName: json['first_name'] as String?,
      userId: json['user_id'] as int,
      isVerified: json['is_verified'] as bool,
    );
  }
}

Uri _uri(String path, [Map<String, String>? query]) {
  final base = Uri.parse('$kBaseUrl$path');
  if (query == null || query.isEmpty) return base;
  return base.replace(queryParameters: query);
}

Map<String, String> _headers({bool auth = false}) {
  final headers = {'Content-Type': 'application/json'};
  if (auth) {
    final token = AuthStore.token;
    if (token != null) headers['Authorization'] = 'Bearer $token';
  }
  return headers;
}

http.Client _client = http.Client();
final Expando<String> _requestTokens = Expando<String>();
const _kTimeout = Duration(seconds: 10);

@visibleForTesting
void setApiClientForTesting(http.Client client) {
  _client.close();
  _client = client;
}

Future<http.Response> _get(Uri uri, {Map<String, String>? headers}) =>
    _request(() => _client.get(uri, headers: headers), headers);

Future<http.Response> _post(
  Uri uri, {
  Map<String, String>? headers,
  Object? body,
}) => _request(() => _client.post(uri, headers: headers, body: body), headers);

Future<http.Response> _patch(
  Uri uri, {
  Map<String, String>? headers,
  Object? body,
}) => _request(() => _client.patch(uri, headers: headers, body: body), headers);

Future<http.Response> _delete(Uri uri, {Map<String, String>? headers}) =>
    _request(() => _client.delete(uri, headers: headers), headers);

Future<http.Response> _request(
  Future<http.Response> Function() send,
  Map<String, String>? headers,
) async {
  try {
    final response = await send().timeout(_kTimeout);
    _rememberRequestToken(response, headers);
    return response;
  } on TimeoutException {
    throw NetworkException(AppLocalizations.get('networkUnavailable'));
  } on SocketException {
    throw NetworkException(AppLocalizations.get('networkUnavailable'));
  } on http.ClientException {
    throw NetworkException(AppLocalizations.get('networkUnavailable'));
  }
}

void _rememberRequestToken(
  http.Response response,
  Map<String, String>? headers,
) {
  final authorization = headers?['Authorization'];
  if (authorization == null || !authorization.startsWith('Bearer ')) return;
  final token = authorization.substring(7).trim();
  if (token.isNotEmpty) _requestTokens[response] = token;
}

bool _isOk(int code) => code >= 200 && code < 300;

Never _throwFor(http.Response response) {
  String message;
  try {
    final body = jsonDecode(response.body);
    final detail = body is Map ? body['detail'] : null;
    if (detail is String) {
      message = detail;
    } else if (detail is Map && detail['detail'] is String) {
      message = detail['detail'] as String;
    } else if (detail is List && detail.isNotEmpty) {
      final first = detail.first;
      message = first is Map && first['msg'] != null
          ? first['msg'].toString()
          : detail.toString();
    } else {
      message = AppLocalizations.get('somethingWentWrong');
    }
  } catch (_) {
    message = AppLocalizations.get('somethingWentWrong');
  }

  switch (response.statusCode) {
    case 401:
      final requestToken = _requestTokens[response];
      if (requestToken != null) {
        unawaited(AuthStore.expireIfCurrent(requestToken));
      }
      throw UnauthorizedException(message);
    case 403:
      throw ForbiddenException(message);
    case 409:
      throw ConflictException(message);
    default:
      throw ApiException(response.statusCode, message);
  }
}

Future<SessionProfile> bootstrapSession(String token) async {
  final response = await _get(
    _uri('/api/flutter/auth/session'),
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    },
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return SessionProfile.fromJson(
    jsonDecode(response.body) as Map<String, dynamic>,
  );
}

Future<AuthResult> login(String email, String password) async {
  final response = await _post(
    _uri('/api/flutter/auth/login'),
    headers: _headers(),
    body: jsonEncode({'email': email, 'password': password}),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return AuthResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<AuthResult> register(
  String email,
  String password,
  String firstName,
) async {
  final response = await _post(
    _uri('/api/flutter/auth/register'),
    headers: _headers(),
    body: jsonEncode({
      'email': email,
      'password': password,
      'first_name': firstName,
    }),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return AuthResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<List<EventModel>> fetchApprovedEvents({
  String? search,
  String? categorySlug,
}) async {
  final query = <String, String>{};
  if (search != null && search.isNotEmpty) query['search'] = search;
  if (categorySlug != null && categorySlug.isNotEmpty) {
    query['category_slug'] = categorySlug;
  }
  final response = await _get(
    _uri('/api/flutter/events', query),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return _decodeEventList(response.body);
}

Future<List<EventModel>> fetchMyEvents() async {
  final response = await _get(
    _uri('/api/flutter/events/my'),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return _decodeEventList(response.body);
}

Future<Map<String, dynamic>> fetchOwnerEventAnalytics(int eventId) async {
  final response = await _get(
    _uri('/api/flutter/events/$eventId/analytics', null),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  final data = jsonDecode(response.body) as Map<String, dynamic>;
  final moderation = await fetchEventModerationDetail(eventId);
  data['moderation'] = {
    'total_review_seconds': moderation.totalReviewSeconds,
    'review_iterations': moderation.reviewIterations,
    'needs_changes_count': moderation.needsChangesCount,
    'resubmission_count': moderation.resubmissionCount,
    'history': moderation.history
        .map(
          (entry) => {
            'action': entry.action,
            'actor_name': entry.actorName,
            'comment': entry.comment,
            'created_at': entry.createdAt,
          },
        )
        .toList(),
  };
  return data;
}

Future<List<EventModel>> fetchPendingEvents({
  bool includeRejected = false,
}) async {
  final response = await _get(
    _uri(
      '/api/flutter/events/pending',
      includeRejected ? {'include_rejected': 'true'} : null,
    ),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return _decodeEventList(response.body);
}

Future<List<CategoryModel>> fetchCategories() async {
  final response = await _get(
    _uri('/api/flutter/events/categories'),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  final list = jsonDecode(response.body) as List<dynamic>;
  return list
      .map((e) => CategoryModel.fromJson(e as Map<String, dynamic>))
      .toList();
}

Future<EventModel> fetchEvent(int id) async {
  final response = await _get(
    _uri('/api/flutter/events/$id'),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<String> uploadCover({
  required List<int> bytes,
  required String filename,
  String? contentType,
}) async {
  final request = http.MultipartRequest(
    'POST',
    _uri('/api/flutter/events/cover'),
  );
  final token = AuthStore.token;
  if (token != null) request.headers['Authorization'] = 'Bearer $token';
  request.files.add(
    http.MultipartFile.fromBytes(
      'file',
      bytes,
      filename: filename,
      contentType: contentType != null ? MediaType.parse(contentType) : null,
    ),
  );
  http.StreamedResponse streamed;
  try {
    streamed = await _client.send(request).timeout(const Duration(seconds: 60));
  } on TimeoutException {
    throw NetworkException(AppLocalizations.get('networkUnavailable'));
  } on SocketException {
    throw NetworkException(AppLocalizations.get('networkUnavailable'));
  } on http.ClientException {
    throw NetworkException(AppLocalizations.get('networkUnavailable'));
  }
  final response = await http.Response.fromStream(streamed);
  _rememberRequestToken(response, request.headers);
  if (!_isOk(response.statusCode)) _throwFor(response);
  final body = jsonDecode(response.body) as Map<String, dynamic>;
  final ref = body['cover_ref'];
  if (ref is! String || ref.isEmpty) {
    throw ApiException(
      response.statusCode,
      AppLocalizations.get('somethingWentWrong'),
    );
  }
  return ref;
}

Future<EventModel> submitEvent(Map<String, dynamic> body) async {
  final response = await _post(
    _uri('/api/flutter/events'),
    headers: _headers(auth: true),
    body: jsonEncode(body),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<EventModel> resubmitEvent(int id, Map<String, dynamic> fields) async {
  // POST /api/flutter/events/{id}/resubmit
  final response = await _post(
    _uri('/api/flutter/events/$id/resubmit'),
    headers: _headers(auth: true),
    body: jsonEncode(fields),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<EventModel> updateEventStatus(
  int id,
  String status,
  String? comment,
) async {
  final response = await _patch(
    _uri('/api/flutter/events/$id/status'),
    headers: _headers(auth: true),
    body: jsonEncode({'status': status, 'comment': comment}),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<EventModel> cancelEvent(int id, {String? comment}) async {
  final response = await _post(
    _uri('/api/flutter/events/$id/cancel'),
    headers: _headers(auth: true),
    body: jsonEncode({'comment': comment}),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<void> deleteEvent(int id) async {
  final response = await _delete(
    _uri('/api/flutter/events/$id'),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
}

Future<EventModel> patchEvent(int id, {String? endTime}) async {
  final response = await _patch(
    _uri('/api/flutter/events/$id'),
    headers: _headers(auth: true),
    body: jsonEncode({'event_end_time': endTime}),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

List<EventModel> _decodeEventList(String body) {
  final list = jsonDecode(body) as List<dynamic>;
  return list
      .map((e) => EventModel.fromJson(e as Map<String, dynamic>))
      .toList();
}

// ── Coordinator analytics ────────────────────────────────────────────────────

/// Composable analytics filter set, mirrored 1:1 by the backend query params so
/// every panel loads against the same filtered event set.
class AnalyticsFilters {
  final String? dateFrom; // YYYY-MM-DD
  final String? dateTo; // YYYY-MM-DD
  final int? categoryId;
  final String? organizer;
  final String? status;
  final int? eventId;

  const AnalyticsFilters({
    this.dateFrom,
    this.dateTo,
    this.categoryId,
    this.organizer,
    this.status,
    this.eventId,
  });

  Map<String, String> toQuery() {
    final q = <String, String>{};
    if (dateFrom != null) q['date_from'] = dateFrom!;
    if (dateTo != null) q['date_to'] = dateTo!;
    if (categoryId != null) q['category_id'] = '$categoryId';
    if (organizer != null && organizer!.isNotEmpty) q['organizer'] = organizer!;
    if (status != null && status!.isNotEmpty) q['status'] = status!;
    if (eventId != null) q['event_id'] = '$eventId';
    return q;
  }
}

Future<Map<String, dynamic>> _getJson(
  String path,
  Map<String, String> query,
) async {
  final response = await _get(
    _uri(path, query.isEmpty ? null : query),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return jsonDecode(response.body) as Map<String, dynamic>;
}

Future<AnalyticsSummary> fetchAnalyticsSummary(AnalyticsFilters filters) async {
  final json = await _getJson(
    '/api/flutter/analytics/summary',
    filters.toQuery(),
  );
  return AnalyticsSummary.fromJson(json);
}

Future<AnalyticsModeration> fetchAnalyticsModeration(
  AnalyticsFilters filters, {
  List<int> thresholds = const [24, 48],
}) async {
  final query = filters.toQuery();
  final response = await _get(
    _uri('/api/flutter/analytics/moderation', query).replace(
      queryParameters: {
        ...query,
        'thresholds': thresholds.map((h) => '$h').toList(),
      },
    ),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return AnalyticsModeration.fromJson(
    jsonDecode(response.body) as Map<String, dynamic>,
  );
}

Future<AnalyticsEngagement> fetchAnalyticsEngagement(
  AnalyticsFilters filters, {
  int trendDays = 30,
}) async {
  final json = await _getJson('/api/flutter/analytics/engagement', {
    ...filters.toQuery(),
    'trend_days': '$trendDays',
  });
  return AnalyticsEngagement.fromJson(json);
}

Future<List<RankedEvent>> fetchAnalyticsTop(
  AnalyticsFilters filters, {
  String metric = 'views',
  int limit = 10,
  int offset = 0,
}) async {
  final response = await _get(
    _uri('/api/flutter/analytics/engagement/top', {
      ...filters.toQuery(),
      'metric': metric,
      'limit': '$limit',
      'offset': '$offset',
    }),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  final list = jsonDecode(response.body) as List<dynamic>;
  return list
      .map((e) => RankedEvent.fromJson(e as Map<String, dynamic>))
      .toList();
}

Future<AnalyticsRatings> fetchAnalyticsRatings(
  AnalyticsFilters filters, {
  int topLimit = 5,
}) async {
  final json = await _getJson('/api/flutter/analytics/ratings', {
    ...filters.toQuery(),
    'top_limit': '$topLimit',
  });
  return AnalyticsRatings.fromJson(json);
}

Future<List<AnalyticsCategory>> fetchAnalyticsCategories(
  AnalyticsFilters filters,
) async {
  final response = await _get(
    _uri('/api/flutter/analytics/categories', filters.toQuery()),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  final list = jsonDecode(response.body) as List<dynamic>;
  return list
      .map((e) => AnalyticsCategory.fromJson(e as Map<String, dynamic>))
      .toList();
}

Future<List<AnalyticsOrganizer>> fetchAnalyticsOrganizers(
  AnalyticsFilters filters, {
  int limit = 10,
  int offset = 0,
}) async {
  final response = await _get(
    _uri('/api/flutter/analytics/organizers', {
      ...filters.toQuery(),
      'limit': '$limit',
      'offset': '$offset',
    }),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  final list = jsonDecode(response.body) as List<dynamic>;
  return list
      .map((e) => AnalyticsOrganizer.fromJson(e as Map<String, dynamic>))
      .toList();
}

Future<EventModerationDetail> fetchEventModerationDetail(int eventId) async {
  final json = await _getJson('/api/flutter/analytics/moderation/event', {
    'event_id': '$eventId',
  });
  return EventModerationDetail.fromJson(json);
}

Future<List<EventReview>> fetchEventReviews(
  int eventId, {
  int limit = 20,
  int offset = 0,
}) async {
  final response = await _get(
    _uri('/api/flutter/analytics/ratings/reviews', {
      'event_id': '$eventId',
      'limit': '$limit',
      'offset': '$offset',
    }),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  final list = jsonDecode(response.body) as List<dynamic>;
  return list
      .map((e) => EventReview.fromJson(e as Map<String, dynamic>))
      .toList();
}

/// Paginated, searchable event list for the analytics event-picker.
Future<List<AnalyticsEventOption>> fetchAnalyticsEvents({
  String? search,
  int limit = 20,
  int offset = 0,
}) async {
  final query = <String, String>{'limit': '$limit', 'offset': '$offset'};
  if (search != null && search.trim().isNotEmpty) {
    query['search'] = search.trim();
  }
  final response = await _get(
    _uri('/api/flutter/analytics/events', query),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  final list = jsonDecode(response.body) as List<dynamic>;
  return list
      .map((e) => AnalyticsEventOption.fromJson(e as Map<String, dynamic>))
      .toList();
}
