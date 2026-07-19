import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class EventDraft {
  const EventDraft({
    required this.userId,
    required this.clientRequestId,
    required this.updatedAt,
    required this.currentStep,
    required this.title,
    required this.description,
    required this.organizer,
    required this.location,
    required this.registrationUrl,
    required this.itEquipment,
    required this.materials,
    this.eventDate,
    this.startTime,
    this.endTime,
    this.categoryId,
    this.categoryName,
  });

  final int userId;
  final String clientRequestId;
  final DateTime updatedAt;
  final int currentStep;
  final String title;
  final String description;
  final String organizer;
  final String location;
  final String registrationUrl;
  final String itEquipment;
  final String materials;
  final String? eventDate;
  final String? startTime;
  final String? endTime;
  final int? categoryId;
  final String? categoryName;

  Map<String, dynamic> toJson() => {
    'user_id': userId,
    'client_request_id': clientRequestId,
    'updated_at': updatedAt.toUtc().toIso8601String(),
    'current_step': currentStep,
    'title': title,
    'description': description,
    'organizer': organizer,
    'location': location,
    'registration_url': registrationUrl,
    'it_equipment': itEquipment,
    'materials': materials,
    'event_date': eventDate,
    'start_time': startTime,
    'end_time': endTime,
    'category_id': categoryId,
    'category_name': categoryName,
  };

  static EventDraft? fromJson(Map<String, dynamic> json) {
    final userId = json['user_id'];
    final requestId = json['client_request_id'];
    final updatedAt = DateTime.tryParse(json['updated_at'] as String? ?? '');
    if (userId is! int || requestId is! String || updatedAt == null) {
      return null;
    }

    return EventDraft(
      userId: userId,
      clientRequestId: requestId,
      updatedAt: updatedAt,
      currentStep: (json['current_step'] as int? ?? 0).clamp(0, 2),
      title: json['title'] as String? ?? '',
      description: json['description'] as String? ?? '',
      organizer: json['organizer'] as String? ?? '',
      location: json['location'] as String? ?? '',
      registrationUrl: json['registration_url'] as String? ?? '',
      itEquipment: json['it_equipment'] as String? ?? '',
      materials: json['materials'] as String? ?? '',
      eventDate: json['event_date'] as String?,
      startTime: json['start_time'] as String?,
      endTime: json['end_time'] as String?,
      categoryId: json['category_id'] as int?,
      categoryName: json['category_name'] as String?,
    );
  }
}

class EventDraftStore {
  EventDraftStore._();

  static const Duration retention = Duration(days: 7);
  static const String _prefix = 'event_create_draft_';

  static Future<EventDraft?> load(int userId, {DateTime? now}) async {
    final prefs = await SharedPreferences.getInstance();
    final key = _key(userId);
    final raw = prefs.getString(key);
    if (raw == null) return null;

    try {
      final draft = EventDraft.fromJson(
        jsonDecode(raw) as Map<String, dynamic>,
      );
      final expired =
          draft == null ||
          draft.userId != userId ||
          (now ?? DateTime.now()).difference(draft.updatedAt) > retention;
      if (expired) {
        await prefs.remove(key);
        return null;
      }
      return draft;
    } on FormatException {
      await prefs.remove(key);
      return null;
    } on TypeError {
      await prefs.remove(key);
      return null;
    }
  }

  static Future<void> save(EventDraft draft) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key(draft.userId), jsonEncode(draft.toJson()));
  }

  static Future<void> clear(int userId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key(userId));
  }

  static String _key(int userId) => '$_prefix$userId';
}
