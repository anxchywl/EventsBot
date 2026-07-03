import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../core/constants.dart';

/// Mirrors the backend FlutterEventItem schema.
class EventModel {
  final int id;
  final String publicToken;
  final String title;
  final String description;
  final String eventDate;
  final String eventTime;
  final String location;
  final String category;
  final String organizerName;
  final String status;
  final String? coverUrl;
  final String? itEquipment;
  final String? materials;
  final String? registrationUrl;
  final String? moderationNote;

  const EventModel({
    required this.id,
    required this.publicToken,
    required this.title,
    required this.description,
    required this.eventDate,
    required this.eventTime,
    required this.location,
    required this.category,
    required this.organizerName,
    required this.status,
    this.coverUrl,
    this.itEquipment,
    this.materials,
    this.registrationUrl,
    this.moderationNote,
  });

  factory EventModel.fromJson(Map<String, dynamic> json) {
    return EventModel(
      id: json['id'] as int,
      publicToken: json['public_token'] as String,
      title: json['title'] as String,
      description: json['description'] as String,
      eventDate: json['event_date'] as String,
      eventTime: json['event_time'] as String,
      location: json['location'] as String,
      category: json['category'] as String,
      organizerName: json['organizer_name'] as String,
      status: json['status'] as String,
      coverUrl: _resolveUrl(json['cover_url'] as String?),
      itEquipment: json['it_equipment'] as String?,
      materials: json['materials'] as String?,
      registrationUrl: json['registration_url'] as String?,
      moderationNote: json['moderation_note'] as String?,
    );
  }

  bool get isApproved => status == 'approved';

  bool get isPending => status == 'pending';

  String get statusLabel {
    switch (status) {
      case 'approved':
        return 'Одобрено';
      case 'pending':
        return 'На модерации';
      case 'needs_changes':
        return 'Требуются правки';
      case 'rejected':
        return 'Отклонено';
      case 'cancelled':
        return 'Отменено';
      case 'archived':
        return 'В архиве';
      default:
        return status;
    }
  }

  static String? _resolveUrl(String? url) {
    if (url == null) return null;
    if (url.startsWith('http')) return url;
    return '$kBaseUrl$url';
  }

  Color get statusColor {
    switch (status) {
      case 'approved':
        return AppColors.success;
      case 'pending':
        return AppColors.orange;
      case 'needs_changes':
        return AppColors.warning;
      case 'rejected':
        return AppColors.error;
      case 'cancelled':
      case 'archived':
        return AppColors.grey;
      default:
        return AppColors.grey;
    }
  }
}
