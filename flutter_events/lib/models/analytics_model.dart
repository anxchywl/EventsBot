/// Typed mirrors of the backend coordinator-analytics response schemas.
///
/// The Flutter layer only renders numbers the backend computed — these models
/// never aggregate raw rows. `AnalyticsSummary` intentionally keeps a keyed map
/// so a new backend card can be added without a model change here.
library;

import '../core/constants.dart';

/// Resolves a possibly-relative avatar/media path (e.g. the backend avatar
/// proxy `/api/events/avatar/...`) to an absolute URL. Absolute `http…` values
/// (Telegram CDN photos) pass through untouched.
String? _resolveMediaUrl(String? url) {
  if (url == null || url.isEmpty) return null;
  if (url.startsWith('http')) return url;
  return '$kBaseUrl$url';
}

/// Keyed summary-card metrics (`/api/flutter/analytics/summary`).
class AnalyticsSummary {
  final Map<String, num?> metrics;

  const AnalyticsSummary(this.metrics);

  factory AnalyticsSummary.fromJson(Map<String, dynamic> json) {
    final raw = (json['metrics'] as Map<String, dynamic>?) ?? const {};
    return AnalyticsSummary(
      raw.map((key, value) => MapEntry(key, value as num?)),
    );
  }

  num? operator [](String key) => metrics[key];
}

class RankedEvent {
  final int eventId;
  final String title;
  final double value;
  final int? count;

  const RankedEvent({
    required this.eventId,
    required this.title,
    required this.value,
    this.count,
  });

  factory RankedEvent.fromJson(Map<String, dynamic> json) {
    return RankedEvent(
      eventId: json['event_id'] as int,
      title: json['title'] as String,
      value: (json['value'] as num).toDouble(),
      count: json['count'] as int?,
    );
  }
}

class LongestPending {
  final int eventId;
  final String title;
  final double waitingSeconds;

  const LongestPending({
    required this.eventId,
    required this.title,
    required this.waitingSeconds,
  });

  factory LongestPending.fromJson(Map<String, dynamic> json) {
    return LongestPending(
      eventId: json['event_id'] as int,
      title: json['title'] as String,
      waitingSeconds: (json['waiting_seconds'] as num).toDouble(),
    );
  }
}

class ThresholdBucket {
  final int thresholdHours;
  final int count;

  const ThresholdBucket({required this.thresholdHours, required this.count});

  factory ThresholdBucket.fromJson(Map<String, dynamic> json) {
    return ThresholdBucket(
      thresholdHours: json['threshold_hours'] as int,
      count: json['count'] as int,
    );
  }
}

class AnalyticsModeration {
  final double approvalRate;
  final double rejectionRate;
  final double needsChangesRate;
  final double? avgTimeToFirstDecisionSeconds;
  final double? avgTotalReviewSeconds;
  final double? avgReviewIterations;
  final int queueSize;
  final LongestPending? longestPending;
  final List<ThresholdBucket> thresholdBuckets;

  const AnalyticsModeration({
    required this.approvalRate,
    required this.rejectionRate,
    required this.needsChangesRate,
    required this.avgTimeToFirstDecisionSeconds,
    required this.avgTotalReviewSeconds,
    required this.avgReviewIterations,
    required this.queueSize,
    required this.longestPending,
    required this.thresholdBuckets,
  });

  factory AnalyticsModeration.fromJson(Map<String, dynamic> json) {
    return AnalyticsModeration(
      approvalRate: (json['approval_rate'] as num).toDouble(),
      rejectionRate: (json['rejection_rate'] as num).toDouble(),
      needsChangesRate: (json['needs_changes_rate'] as num).toDouble(),
      avgTimeToFirstDecisionSeconds:
          (json['avg_time_to_first_decision_seconds'] as num?)?.toDouble(),
      avgTotalReviewSeconds:
          (json['avg_total_review_seconds'] as num?)?.toDouble(),
      avgReviewIterations: (json['avg_review_iterations'] as num?)?.toDouble(),
      queueSize: json['queue_size'] as int,
      longestPending: json['longest_pending'] == null
          ? null
          : LongestPending.fromJson(
              json['longest_pending'] as Map<String, dynamic>),
      thresholdBuckets: ((json['threshold_buckets'] as List<dynamic>?) ?? [])
          .map((e) => ThresholdBucket.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class EngagementTotals {
  final int views;
  final int registerClicks;
  final int shareClicks;
  final int reminderCreates;
  final int favoritesAdded;
  final int favoritesRemoved;

  const EngagementTotals({
    required this.views,
    required this.registerClicks,
    required this.shareClicks,
    required this.reminderCreates,
    required this.favoritesAdded,
    required this.favoritesRemoved,
  });

  factory EngagementTotals.fromJson(Map<String, dynamic> json) {
    return EngagementTotals(
      views: json['views'] as int,
      registerClicks: json['register_clicks'] as int,
      shareClicks: json['share_clicks'] as int,
      reminderCreates: json['reminder_creates'] as int,
      favoritesAdded: json['favorites_added'] as int,
      favoritesRemoved: json['favorites_removed'] as int,
    );
  }
}

class TrendPoint {
  final String date;
  final int count;

  const TrendPoint({required this.date, required this.count});

  factory TrendPoint.fromJson(Map<String, dynamic> json) {
    return TrendPoint(
      date: json['date'] as String,
      count: json['count'] as int,
    );
  }
}

class AnalyticsEngagement {
  final EngagementTotals totals;
  final List<TrendPoint> viewsOverTime;

  const AnalyticsEngagement({required this.totals, required this.viewsOverTime});

  factory AnalyticsEngagement.fromJson(Map<String, dynamic> json) {
    return AnalyticsEngagement(
      totals: EngagementTotals.fromJson(json['totals'] as Map<String, dynamic>),
      viewsOverTime: ((json['views_over_time'] as List<dynamic>?) ?? [])
          .map((e) => TrendPoint.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class AnalyticsRatings {
  final double? average;
  final Map<String, int> distribution;
  final int totalReviews;
  final int eventsWithZeroReviews;
  final List<RankedEvent> topRated;
  final List<RankedEvent> lowestRated;

  const AnalyticsRatings({
    required this.average,
    required this.distribution,
    required this.totalReviews,
    required this.eventsWithZeroReviews,
    required this.topRated,
    required this.lowestRated,
  });

  factory AnalyticsRatings.fromJson(Map<String, dynamic> json) {
    final dist = (json['distribution'] as Map<String, dynamic>?) ?? const {};
    return AnalyticsRatings(
      average: (json['average'] as num?)?.toDouble(),
      distribution: dist.map((k, v) => MapEntry(k, v as int)),
      totalReviews: json['total_reviews'] as int,
      eventsWithZeroReviews: json['events_with_zero_reviews'] as int,
      topRated: _rankedList(json['top_rated']),
      lowestRated: _rankedList(json['lowest_rated']),
    );
  }
}

List<RankedEvent> _rankedList(dynamic raw) {
  return ((raw as List<dynamic>?) ?? [])
      .map((e) => RankedEvent.fromJson(e as Map<String, dynamic>))
      .toList();
}

class AnalyticsCategory {
  final int categoryId;
  final String category;
  final int eventCount;
  final int views;
  final int registrationClicks;
  final double? averageRating;
  final double approvalRate;

  const AnalyticsCategory({
    required this.categoryId,
    required this.category,
    required this.eventCount,
    required this.views,
    required this.registrationClicks,
    required this.averageRating,
    required this.approvalRate,
  });

  factory AnalyticsCategory.fromJson(Map<String, dynamic> json) {
    return AnalyticsCategory(
      categoryId: json['category_id'] as int,
      category: json['category'] as String,
      eventCount: json['event_count'] as int,
      views: json['views'] as int,
      registrationClicks: json['registration_clicks'] as int,
      averageRating: (json['average_rating'] as num?)?.toDouble(),
      approvalRate: (json['approval_rate'] as num).toDouble(),
    );
  }
}

class AnalyticsOrganizer {
  final String organizer;
  final int eventsCreated;
  final double approvalRate;
  final double rejectionRate;
  final double? averageRating;
  final int views;
  final int registrationClicks;
  final int favorites;

  const AnalyticsOrganizer({
    required this.organizer,
    required this.eventsCreated,
    required this.approvalRate,
    required this.rejectionRate,
    required this.averageRating,
    required this.views,
    required this.registrationClicks,
    required this.favorites,
  });

  factory AnalyticsOrganizer.fromJson(Map<String, dynamic> json) {
    return AnalyticsOrganizer(
      organizer: json['organizer'] as String,
      eventsCreated: json['events_created'] as int,
      approvalRate: (json['approval_rate'] as num).toDouble(),
      rejectionRate: (json['rejection_rate'] as num).toDouble(),
      averageRating: (json['average_rating'] as num?)?.toDouble(),
      views: json['views'] as int,
      registrationClicks: json['registration_clicks'] as int,
      favorites: json['favorites'] as int,
    );
  }
}

/// One entry in the moderation log for a single event.
class ModerationLogEntry {
  final String action;
  final String? actorName;
  final String? comment;
  final String createdAt;

  const ModerationLogEntry({
    required this.action,
    this.actorName,
    this.comment,
    required this.createdAt,
  });

  factory ModerationLogEntry.fromJson(Map<String, dynamic> json) {
    return ModerationLogEntry(
      action: json['action'] as String,
      actorName: json['actor_name'] as String?,
      comment: json['comment'] as String?,
      createdAt: json['created_at'] as String,
    );
  }
}

/// Exact moderation timeline for a single event (`/api/flutter/analytics/moderation/event`).
class EventModerationDetail {
  final String currentStatus;
  final String? submittedAt;
  final String? firstReviewedAt;
  final String? approvedAt;
  final String? rejectedAt;
  final double? totalReviewSeconds;
  final int reviewIterations;
  final int needsChangesCount;
  final int resubmissionCount;
  final String? latestModerator;
  final String? latestComment;
  final String? lastStatusUpdate;
  final bool creatorResubmitted;

  final List<ModerationLogEntry> history;

  const EventModerationDetail({
    required this.currentStatus,
    this.submittedAt,
    this.firstReviewedAt,
    this.approvedAt,
    this.rejectedAt,
    this.totalReviewSeconds,
    required this.reviewIterations,
    required this.needsChangesCount,
    required this.resubmissionCount,
    this.latestModerator,
    this.latestComment,
    this.lastStatusUpdate,
    required this.creatorResubmitted,
    required this.history,
  });

  factory EventModerationDetail.fromJson(Map<String, dynamic> json) {
    return EventModerationDetail(
      currentStatus: json['current_status'] as String,
      submittedAt: json['submitted_at'] as String?,
      firstReviewedAt: json['first_reviewed_at'] as String?,
      approvedAt: json['approved_at'] as String?,
      rejectedAt: json['rejected_at'] as String?,
      totalReviewSeconds: (json['total_review_seconds'] as num?)?.toDouble(),
      reviewIterations: json['review_iterations'] as int,
      needsChangesCount: json['needs_changes_count'] as int,
      resubmissionCount: json['resubmission_count'] as int,
      latestModerator: json['latest_moderator'] as String?,
      latestComment: json['latest_comment'] as String?,
      lastStatusUpdate: json['last_status_update'] as String?,
      creatorResubmitted: json['creator_resubmitted'] as bool,
      history: ((json['history'] as List<dynamic>?) ?? [])
          .map((e) => ModerationLogEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// One review (rating + optional text) for the per-event reviews sheet.
class EventReview {
  final int ratingId;
  final int userId;
  final String displayName;
  final String? username;
  final String? photoUrl;
  final int score;
  final String? content;
  final String createdAt;

  const EventReview({
    required this.ratingId,
    required this.userId,
    required this.displayName,
    this.username,
    this.photoUrl,
    required this.score,
    this.content,
    required this.createdAt,
  });

  factory EventReview.fromJson(Map<String, dynamic> json) {
    return EventReview(
      ratingId: json['rating_id'] as int,
      userId: json['user_id'] as int,
      displayName: json['display_name'] as String,
      username: json['username'] as String?,
      photoUrl: _resolveMediaUrl(json['photo_url'] as String?),
      score: json['score'] as int,
      content: json['content'] as String?,
      createdAt: json['created_at'] as String,
    );
  }
}

/// One row in the analytics event-picker (`/api/flutter/analytics/events`).
class AnalyticsEventOption {
  final int id;
  final String title;
  final String category;
  final String eventDate; // YYYY-MM-DD
  final String status;

  const AnalyticsEventOption({
    required this.id,
    required this.title,
    required this.category,
    required this.eventDate,
    required this.status,
  });

  factory AnalyticsEventOption.fromJson(Map<String, dynamic> json) {
    return AnalyticsEventOption(
      id: json['id'] as int,
      title: json['title'] as String,
      category: json['category'] as String,
      eventDate: json['event_date'] as String,
      status: json['status'] as String,
    );
  }
}
