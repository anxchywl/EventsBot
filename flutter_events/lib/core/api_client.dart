import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/category_model.dart';
import '../models/event_model.dart';
import 'auth_store.dart';
import 'constants.dart';
import 'exceptions.dart';

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

bool _isOk(int code) => code >= 200 && code < 300;

Never _throwFor(http.Response response) {
  String message;
  try {
    final body = jsonDecode(response.body);
    final detail = body is Map ? body['detail'] : null;
    if (detail is String) {
      message = detail;
    } else if (detail is List && detail.isNotEmpty) {
      final first = detail.first;
      message = first is Map && first['msg'] != null
          ? first['msg'].toString()
          : detail.toString();
    } else {
      message = 'Что-то пошло не так';
    }
  } catch (_) {
    message = 'Что-то пошло не так';
  }

  switch (response.statusCode) {
    case 401:
      throw UnauthorizedException(message);
    case 403:
      throw ForbiddenException(message);
    case 409:
      throw ConflictException(message);
    default:
      throw ApiException(response.statusCode, message);
  }
}

Future<AuthResult> login(String email, String password) async {
  final response = await http.post(
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
  final response = await http.post(
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
  final response = await http.get(
    _uri('/api/flutter/events', query),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return _decodeEventList(response.body);
}

Future<List<EventModel>> fetchMyEvents() async {
  final response = await http.get(
    _uri('/api/flutter/events/my'),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return _decodeEventList(response.body);
}

Future<List<EventModel>> fetchPendingEvents() async {
  final response = await http.get(
    _uri('/api/flutter/events/pending'),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return _decodeEventList(response.body);
}

Future<List<CategoryModel>> fetchCategories() async {
  final response = await http.get(
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
  final response = await http.get(
    _uri('/api/flutter/events/$id'),
    headers: _headers(auth: true),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<EventModel> submitEvent(Map<String, dynamic> body) async {
  final response = await http.post(
    _uri('/api/flutter/events'),
    headers: _headers(auth: true),
    body: jsonEncode(body),
  );
  if (!_isOk(response.statusCode)) _throwFor(response);
  return EventModel.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<EventModel> updateEventStatus(
  int id,
  String status,
  String? comment,
) async {
  final response = await http.patch(
    _uri('/api/flutter/events/$id/status'),
    headers: _headers(auth: true),
    body: jsonEncode({'status': status, 'comment': comment}),
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
