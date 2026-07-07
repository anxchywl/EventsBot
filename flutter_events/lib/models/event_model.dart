import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../core/constants.dart';
import '../core/localization.dart';

/// Mirrors the backend FlutterEventItem schema.
class EventModel {
  final int id;
  final String publicToken;
  final String title;
  final String description;
  final String eventDate;
  final String eventTime;
  final String? eventEndTime;
  final String location;
  final String category;
  final String organizerName;
  final String status;
  final String? coverUrl;
  final String? itEquipment;
  final String? materials;
  final String? registrationUrl;
  final String? moderationNote;
  final String? submittedAt;

  const EventModel({
    required this.id,
    required this.publicToken,
    required this.title,
    required this.description,
    required this.eventDate,
    required this.eventTime,
    this.eventEndTime,
    required this.location,
    required this.category,
    required this.organizerName,
    required this.status,
    this.coverUrl,
    this.itEquipment,
    this.materials,
    this.registrationUrl,
    this.moderationNote,
    this.submittedAt,
  });

  factory EventModel.fromJson(Map<String, dynamic> json) {
    return EventModel(
      id: json['id'] as int,
      publicToken: json['public_token'] as String,
      title: json['title'] as String,
      description: json['description'] as String,
      eventDate: json['event_date'] as String,
      eventTime: json['event_time'] as String,
      eventEndTime: json['event_end_time'] as String?,
      location: json['location'] as String,
      category: json['category'] as String,
      organizerName: json['organizer_name'] as String,
      status: json['status'] as String,
      coverUrl: _resolveUrl(json['cover_url'] as String?),
      itEquipment: json['it_equipment'] as String?,
      materials: json['materials'] as String?,
      registrationUrl: json['registration_url'] as String?,
      moderationNote: json['moderation_note'] as String?,
      submittedAt: json['submitted_at'] as String?,
    );
  }

  /// Serialises back to the same JSON shape [fromJson] consumes, so a cached
  /// event round-trips through SharedPreferences. [coverUrl] is stored already
  /// resolved to an absolute URL; [_resolveUrl] leaves `http…` values untouched
  /// on the way back in, so the round-trip is stable.
  Map<String, dynamic> toJson() => {
        'id': id,
        'public_token': publicToken,
        'title': title,
        'description': description,
        'event_date': eventDate,
        'event_time': eventTime,
        'event_end_time': eventEndTime,
        'location': location,
        'category': category,
        'organizer_name': organizerName,
        'status': status,
        'cover_url': coverUrl,
        'it_equipment': itEquipment,
        'materials': materials,
        'registration_url': registrationUrl,
        'moderation_note': moderationNote,
        'submitted_at': submittedAt,
      };

  bool get isApproved => status == 'approved';

  bool get isPending => status == 'pending';

  bool get isNeedsChanges => status == 'needs_changes';

  bool get isResubmitted => status == 'resubmitted';

  String get statusLabel {
    switch (status) {
      case 'approved':
        return AppLocalizations.get('approvedLabel');
      case 'pending':
        return AppLocalizations.get('pendingLabel');
      case 'needs_changes':
        return AppLocalizations.get('needsChangesLabel');
      case 'resubmitted':
        return AppLocalizations.get('resubmitted');
      case 'rejected':
        return AppLocalizations.get('rejectedLabel');
      case 'cancelled':
        return AppLocalizations.get('cancelledLabel');
      case 'archived':
        return AppLocalizations.get('archivedLabel');
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
        return AppColors.grey;
      case 'needs_changes':
        return AppColors.warning;
      case 'resubmitted':
        return AppColors.primary;
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
