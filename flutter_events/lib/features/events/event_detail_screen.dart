import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/auth_store.dart';
import '../../core/api_client.dart';
import '../../core/cache_store.dart';
import '../../core/exceptions.dart';
import '../../core/localization.dart';
import '../../models/event_model.dart';
import '../shared/app_feedback.dart';
import '../submit/submit_screen.dart';

class EventDetailScreen extends StatefulWidget {
  const EventDetailScreen({
    super.key,
    required this.event,
    this.showStatus = false,
  });

  final EventModel event;
  final bool showStatus;

  @override
  State<EventDetailScreen> createState() => _EventDetailScreenState();
}

class _EventDetailScreenState extends State<EventDetailScreen> {
  late EventModel _event = widget.event;
  Future<Map<String, dynamic>>? _ownerAnalyticsFuture;
  Map<String, dynamic>? _ownerAnalyticsInitialData;
  bool _ownerAnalyticsWasCached = false;
  bool _moderating = false;
  bool _lifecycleMutating = false;

  // Only coordinators (admins) moderate. The backend
  // (PATCH /api/flutter/events/{id}/status via require_flutter_admin) is the
  // authority; this gate just keeps the moderation bar out of an event
  // submitter's view of their own request.
  //
  // Admins retain full control from every reviewable state, including after an
  // event is approved or rejected — the available buttons adapt to the current
  // status (see [_moderationSection]).
  bool get _canModerate =>
      AuthStore.isAdmin &&
      (_event.status == 'pending' ||
          _event.status == 'needs_changes' ||
          _event.status == 'resubmitted' ||
          _event.status == 'approved' ||
          _event.status == 'rejected');

  // creator edits to published events are reviewed as drafts by the backend
  bool get _canResubmit =>
      !AuthStore.isAdmin &&
      widget.showStatus &&
      (_event.isNeedsChanges || _event.status == 'approved');

  bool get _canCancel =>
      !AuthStore.isAdmin && widget.showStatus && _event.canCreatorCancel;

  bool get _canDelete =>
      !AuthStore.isAdmin && widget.showStatus && _event.canCreatorDelete;

  @override
  void initState() {
    super.initState();
    // Share the canonical cached object so a status change patched by an SSE
    // event or a mutation elsewhere is reflected here without a manual refresh.
    EventCache.instance.seed(_event);
    EventCache.instance.addListener(_onCacheChanged);
    _prepareOwnerAnalytics();
    // Opened from a list; pull the freshest copy in the background (cache-first
    // for instant render, revalidated silently).
    unawaited(_refreshEvent());
  }

  @override
  void didUpdateWidget(covariant EventDetailScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.event.id != widget.event.id ||
        oldWidget.showStatus != widget.showStatus) {
      _event = widget.event;
      _prepareOwnerAnalytics();
    }
  }

  @override
  void dispose() {
    EventCache.instance.removeListener(_onCacheChanged);
    super.dispose();
  }

  void _onCacheChanged() {
    if (!mounted) return;
    final updated = EventCache.instance.peekEvent(_event.id);
    if (updated != null && !identical(updated, _event)) {
      setState(() => _event = updated);
    }
  }

  Future<void> _refreshEvent() async {
    try {
      final updated = await EventCache.instance.event(_event.id, force: true);
      if (!mounted) return;
      setState(() => _event = updated);
    } catch (_) {
      // Offline / transient: keep the copy we were handed.
    }
  }

  void _prepareOwnerAnalytics() {
    if (!widget.showStatus || AuthStore.isAdmin) {
      _ownerAnalyticsFuture = null;
      _ownerAnalyticsInitialData = null;
      _ownerAnalyticsWasCached = false;
      return;
    }
    final userId = AuthStore.userId;
    final key = 'owner-event|$userId|${_event.id}';
    _ownerAnalyticsInitialData = AnalyticsCache.instance
        .peekFresh<Map<String, dynamic>>(key);
    _ownerAnalyticsWasCached = _ownerAnalyticsInitialData != null;
    _ownerAnalyticsFuture = AnalyticsCache.instance.get(
      key,
      () => fetchOwnerEventAnalytics(_event.id),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasImage = _event.coverUrl != null;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: ScrollConfiguration(
        behavior: ScrollConfiguration.of(
          context,
        ).copyWith(physics: const ClampingScrollPhysics()),
        child: NestedScrollView(
          headerSliverBuilder: (ctx, _) => [
            AppSliverAppBar(
              leading: IconButton(
                icon: const AppIcon(
                  AppIcons.back,
                  color: AppColors.textPrimary,
                ),
                onPressed: () => Navigator.pop(context),
              ),
            ),
          ],
          body: ListView(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.df,
              0,
              AppSpacing.df,
              AppSpacing.xxl,
            ),
            children: [
              if (hasImage) ...[
                ClipRRect(
                  borderRadius: AppSpacing.borderRadiusDf,
                  child: AspectRatio(
                    aspectRatio: 16 / 10,
                    child: Image.network(
                      _event.coverUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) =>
                          const ColoredBox(color: AppColors.fieldBackground),
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.lg),
              ],

              _titleCard(theme),
              const SizedBox(height: AppSpacing.lg),
              _factsCard(),
              if (_event.description.isNotEmpty)
                _section('Description', _event.description),
              if (widget.showStatus && !AuthStore.isAdmin)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.lg),
                  child: _ownerAnalyticsSection(),
                ),
              if (AuthStore.isAdmin && _event.itEquipment?.isNotEmpty == true)
                _section('IT Equipment', _event.itEquipment!),
              if (AuthStore.isAdmin && _event.materials?.isNotEmpty == true)
                _section('Materials', _event.materials!),
              if (_event.registrationUrl?.isNotEmpty == true)
                _registrationCard(_event.registrationUrl!, theme),
              if (_canModerate || _canResubmit || _canCancel || _canDelete)
                _buildBottomBar()!,
            ],
          ),
        ),
      ),
    );
  }

  Widget _ownerAnalyticsSection() {
    final future = _ownerAnalyticsFuture;
    if (future == null) return const SizedBox.shrink();
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      initialData: _ownerAnalyticsInitialData,
      builder: (context, snapshot) {
        if (!snapshot.hasData &&
            snapshot.connectionState != ConnectionState.done) {
          return const _OwnerAnalyticsSkeleton();
        }
        if (snapshot.hasError || snapshot.data == null) {
          return const SizedBox.shrink();
        }
        final data = snapshot.data!;
        final engagement = data['engagement'] as Map<String, dynamic>;
        final moderation = data['moderation'] as Map<String, dynamic>? ?? {};
        final ratings =
            data['rating_distribution'] as Map<String, dynamic>? ?? {};
        final history =
            (moderation['history'] as List<dynamic>?) ?? const <dynamic>[];
        final viewsOverTime =
            (data['views_over_time'] as List<dynamic>?) ?? const <dynamic>[];
        final content = Column(
          children: [
            _analyticsCard('Moderation health', [
              _OwnerStat(
                'Total review time',
                _duration(moderation['total_review_seconds']),
              ),
              _OwnerStat(
                'Review iterations',
                moderation['review_iterations'] ?? 0,
              ),
              _OwnerStat(
                'Changes requested',
                moderation['needs_changes_count'] ?? 0,
              ),
              _OwnerStat(
                'Resubmissions',
                moderation['resubmission_count'] ?? 0,
              ),
            ], timelineEntries: history),
            const SizedBox(height: AppSpacing.lg),
            _analyticsCard('Engagement', [
              _OwnerStat('Views', engagement['views'], span: 2),
              _OwnerStat('Registrations', engagement['register_clicks']),
              _OwnerStat('Shares', engagement['share_clicks']),
              _OwnerStat('Reminders', engagement['reminder_creates']),
              _OwnerStat('Favorites', engagement['favorites_added'] ?? 0),
            ], viewTrend: viewsOverTime),
            const SizedBox(height: AppSpacing.lg),
            _ratingsCard(
              data['average_rating'],
              data['total_reviews'],
              ratings,
            ),
          ],
        );
        if (_ownerAnalyticsWasCached) return content;
        return TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1),
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          builder: (context, opacity, child) =>
              Opacity(opacity: opacity, child: child),
          child: content,
        );
      },
    );
  }

  Widget _analyticsCard(
    String title,
    List<_OwnerStat> metrics, {
    List<dynamic> timelineEntries = const [],
    List<dynamic> viewTrend = const [],
    Object? averageRating,
    Object? totalReviews,
    Map<String, dynamic> ratingDistribution = const {},
    bool emptyRatings = false,
  }) {
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: double.infinity,
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: AppTextStyles.titleMedium,
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          _OwnerStatGrid(stats: metrics),
          if (timelineEntries.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            Text('Timeline', style: AppTextStyles.titleMedium),
            const SizedBox(height: AppSpacing.md),
            for (var index = 0; index < timelineEntries.length; index++)
              _OwnerTimelineEntry(
                entry: timelineEntries[index] as Map<String, dynamic>,
                isLast: index == timelineEntries.length - 1,
              ),
          ],
          if (viewTrend.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            _OwnerViewsOverTime(points: viewTrend),
          ],
          if (!emptyRatings && totalReviews != null) ...[
            _OwnerRatingsSummary(
              average: averageRating,
              total: totalReviews,
              distribution: ratingDistribution,
            ),
          ],
          if (emptyRatings)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
              child: Center(
                child: Text(
                  'Nothing here yet',
                  style: AppTextStyles.bodyMedium.copyWith(
                    color: AppColors.grey,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _ratingsCard(
    Object? average,
    Object? total,
    Map<String, dynamic> distribution,
  ) {
    if (total == 0) {
      return _analyticsCard('Ratings', const [], emptyRatings: true);
    }
    return _analyticsCard(
      'Ratings',
      const [],
      averageRating: average,
      totalReviews: total,
      ratingDistribution: distribution,
    );
  }

  String _duration(Object? value) {
    if (value == null) return '—';
    final seconds = (value as num).toDouble();
    if (seconds < 60) return '${seconds.round()}s';
    final minutes = seconds / 60;
    if (minutes < 60) return '${minutes.round()}m';
    final hours = minutes / 60;
    if (hours < 24) return '${hours.toStringAsFixed(hours < 10 ? 1 : 0)}h';
    final days = hours / 24;
    return '${days.toStringAsFixed(days < 10 ? 1 : 0)}d';
  }

  Widget? _buildBottomBar() {
    if (_canModerate) {
      return Padding(
        padding: const EdgeInsets.only(top: AppSpacing.lg),
        child: _moderationSection(),
      );
    }
    if (_canResubmit || _canCancel || _canDelete) {
      return Padding(
        padding: const EdgeInsets.only(top: AppSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_canResubmit)
              AppPrimaryButton(
                size: AppButtonSize.medium,
                text: _event.status == 'approved'
                    ? 'Edit event'
                    : AppLocalizations.get('editAndResubmit'),
                isLoading: _lifecycleMutating,
                onPressed: _lifecycleMutating ? null : _openResubmit,
              ),
            if (_canResubmit && _canCancel)
              const SizedBox(height: AppSpacing.sm),
            if (_canCancel)
              AppSecondaryButton(
                size: AppButtonSize.medium,
                text: 'Cancel event',
                isLoading: _lifecycleMutating,
                borderColor: AppColors.error,
                textColor: AppColors.error,
                onPressed: _lifecycleMutating ? null : _confirmCancel,
              ),
            if (_canDelete)
              AppSecondaryButton(
                size: AppButtonSize.medium,
                text: 'Delete event',
                isLoading: _lifecycleMutating,
                borderColor: AppColors.error,
                textColor: AppColors.error,
                onPressed: _lifecycleMutating ? null : _confirmDelete,
              ),
          ],
        ),
      );
    }
    return null;
  }

  Future<void> _openResubmit() async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: AppColors.transparent,
      isScrollControlled: true,
      useSafeArea: false,
      builder: (context) => SubmitScreen(initialEvent: _event, asSheet: true),
    );
    if (result == true && mounted) {
      Navigator.pop(context, true);
    }
  }

  Future<void> _confirmCancel() async {
    final comment = await _promptComment(
      icon: AppIcons.close,
      iconColor: AppColors.error,
      title: 'Cancel event?',
      description:
          'The event will be unpublished and can only be deleted afterward.',
      actionText: 'Cancel event',
      isDestructive: true,
      commentRequired: false,
    );
    if (comment == null || _lifecycleMutating) return;

    setState(() => _lifecycleMutating = true);
    try {
      final updated = await EventCache.instance.cancel(
        _event.id,
        comment: comment.trim().isEmpty ? null : comment.trim(),
      );
      if (!mounted) return;
      // the status banner on the card reflects the cancellation inline, so no
      // extra confirmation popup is shown
      setState(() => _event = updated);
    } on ApiException catch (error) {
      _showMessage(error.message);
    } catch (_) {
      _showMessage(AppLocalizations.get('somethingWentWrong'));
    } finally {
      if (mounted) setState(() => _lifecycleMutating = false);
    }
  }

  Future<void> _confirmDelete() async {
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: AppColors.transparent,
      barrierColor: AppColors.black.withValues(alpha: 0.48),
      isScrollControlled: true,
      enableDrag: true,
      builder: (sheetContext) => _DeleteConfirmSheet(
        onConfirm: () => Navigator.pop(sheetContext, true),
        onCancel: () => Navigator.pop(sheetContext, false),
      ),
    );
    if (confirmed != true || _lifecycleMutating) return;

    setState(() => _lifecycleMutating = true);
    try {
      await EventCache.instance.delete(_event.id);
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (error) {
      _showMessage(error.message);
    } catch (_) {
      _showMessage(AppLocalizations.get('somethingWentWrong'));
    } finally {
      if (mounted) setState(() => _lifecycleMutating = false);
    }
  }

  Widget _titleCard(ThemeData theme) {
    return AppCard(
      padding: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _event.title,
                  style: theme.textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  _event.organizerName,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          if (widget.showStatus ||
              (_event.status != 'approved' && _event.status != 'rejected'))
            Container(
              padding: const EdgeInsets.symmetric(
                vertical: AppSpacing.md,
                horizontal: AppSpacing.lg,
              ),
              color: _event.statusColor.withValues(alpha: 0.12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _event.statusLabel,
                          style: AppTextStyles.bodyMedium.copyWith(
                            color: _event.statusColor,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                  // Coordinator comment shown under any status that has one
                  // (approved / needs_changes / rejected), visible to the
                  // event submitter.
                  if (_event.moderationNote != null &&
                      _event.moderationNote!.trim().isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      '${AppLocalizations.get('coordinatorComment')}: ${_event.moderationNote!}',
                      style: AppTextStyles.bodySmall.copyWith(
                        color: _event.statusColor,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _factsCard() {
    return AppCard(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.df,
        vertical: AppSpacing.sm,
      ),
      child: Column(
        children: [
          _fact(
            AppIcons.calendar,
            '${_formatDate(_event.eventDate)} · ${_timeRange()}',
            iconColor: AppColors.blue,
            backgroundColor: AppColors.blueLight,
          ),
          _factDivider(),
          _fact(
            AppIcons.location,
            _event.location,
            iconColor: AppColors.green,
            backgroundColor: AppColors.lightGreen,
          ),
          _factDivider(),
          _fact(
            AppIcons.users,
            _event.category,
            iconColor: AppColors.primary,
            backgroundColor: AppColors.primaryLight,
          ),
        ],
      ),
    );
  }

  String _formatDate(String raw) {
    final parts = raw.split('-');
    if (parts.length != 3) return raw;
    return '${parts[2]}.${parts[1]}.${parts[0]}';
  }

  String _timeRange() => _event.eventEndTime != null
      ? '${_event.eventTime} – ${_event.eventEndTime}'
      : _event.eventTime;

  Widget _fact(
    AppIconData icon,
    String value, {
    Color? iconColor,
    Color? backgroundColor,
  }) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(
        vertical: AppSpacing.md,
        horizontal: AppSpacing.xs,
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color:
                  backgroundColor ?? AppColors.primary.withValues(alpha: 0.08),
              borderRadius: AppSpacing.borderRadiusMd,
            ),
            child: AppIcon(
              icon,
              size: 22,
              color: iconColor ?? AppColors.primary,
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              value,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _factDivider() =>
      const Divider(height: 1, thickness: 1, color: AppColors.borderGrey);

  Widget _section(String title, String body, [AppIconData? icon]) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.lg),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (icon != null) ...[
                  Container(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    decoration: BoxDecoration(
                      color: AppColors.fieldBackground,
                      borderRadius: AppSpacing.borderRadiusSm,
                    ),
                    child: AppIcon(
                      icon,
                      size: 18,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                ],
                Text(
                  title,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              body,
              style: theme.textTheme.bodyLarge?.copyWith(
                height: 1.6,
                color: AppColors.textPrimary.withValues(alpha: 0.85),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _registrationCard(String url, ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.lg),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Registration',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: AppColors.primary,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            GestureDetector(
              onTap: () => Clipboard.setData(ClipboardData(text: url)),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.df,
                  vertical: AppSpacing.md,
                ),
                decoration: BoxDecoration(
                  color: AppColors.fieldBackground,
                  borderRadius: AppSpacing.borderRadiusDf,
                ),
                child: Text(
                  url,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: AppColors.primary,
                    decoration: TextDecoration.underline,
                    decorationColor: AppColors.primary,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _moderationSection() {
    const h = 42.0;
    const style = ButtonStyle(
      elevation: WidgetStatePropertyAll(0),
      padding: WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: 8)),
      shape: WidgetStatePropertyAll(
        RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(12)),
        ),
      ),
    );
    final labelStyle = AppTextStyles.labelLarge.copyWith(
      fontWeight: FontWeight.w600,
    );

    // The button set always mirrors the current status so admins keep full,
    // symmetric control:
    //   approved            -> Edits + Reject
    //   rejected            -> Approve + Edits
    //   pending/needs/resub -> Approve + Edits + Reject
    // "Edits" (needs_changes) is reachable from every state.
    final showApprove = _event.status != 'approved';
    final showReject = _event.status != 'rejected';

    final approveButton = SizedBox(
      height: h,
      child: ElevatedButton(
        onPressed: _moderating ? null : _confirmApprove,
        style: style.copyWith(
          backgroundColor: const WidgetStatePropertyAll(AppColors.success),
          foregroundColor: const WidgetStatePropertyAll(AppColors.white),
        ),
        child: Text('Approve', style: labelStyle),
      ),
    );

    final editsButton = SizedBox(
      height: h,
      child: ElevatedButton(
        onPressed: _moderating ? null : _confirmRequestEdits,
        style: style.copyWith(
          backgroundColor: WidgetStatePropertyAll(
            AppColors.warning.withValues(alpha: 0.15),
          ),
          foregroundColor: const WidgetStatePropertyAll(AppColors.textPrimary),
          overlayColor: WidgetStatePropertyAll(
            AppColors.warning.withValues(alpha: 0.15),
          ),
        ),
        child: Text('Edits', style: labelStyle),
      ),
    );

    final rejectButton = SizedBox(
      height: h,
      child: ElevatedButton(
        onPressed: _moderating ? null : _confirmReject,
        style: style.copyWith(
          backgroundColor: WidgetStatePropertyAll(
            AppColors.error.withValues(alpha: 0.10),
          ),
          foregroundColor: const WidgetStatePropertyAll(AppColors.error),
          overlayColor: WidgetStatePropertyAll(
            AppColors.error.withValues(alpha: 0.10),
          ),
        ),
        child: Text('Reject', style: labelStyle),
      ),
    );

    final buttons = <Widget>[
      if (showApprove) approveButton,
      editsButton,
      if (showReject) rejectButton,
    ];

    return Row(
      children: [
        for (var i = 0; i < buttons.length; i++) ...[
          if (i > 0) const SizedBox(width: AppSpacing.sm),
          Expanded(child: buttons[i]),
        ],
      ],
    );
  }

  Future<void> _confirmApprove() async {
    await _moderateWithComment(
      status: 'approved',
      icon: AppIcons.check,
      iconColor: AppColors.success,
      title: 'Approve event?',
      description: 'The event will be published and the organiser notified.',
      actionText: 'Approve',
      commentRequired: false,
    );
  }

  Future<void> _confirmReject() async {
    await _moderateWithComment(
      status: 'rejected',
      icon: AppIcons.close,
      iconColor: AppColors.error,
      title: 'Reject event?',
      description:
          'The organiser will be notified that the request was declined.',
      actionText: 'Reject',
      isDestructive: true,
      commentRequired: true,
    );
  }

  Future<void> _confirmRequestEdits() async {
    await _moderateWithComment(
      status: 'needs_changes',
      icon: AppIcons.edit,
      iconColor: AppColors.warning,
      title: 'Request changes?',
      description: 'Add a comment explaining what needs to be fixed.',
      actionText: 'Request changes',
      commentRequired: true,
    );
  }

  Future<void> _moderateWithComment({
    required String status,
    required AppIconData icon,
    required Color iconColor,
    required String title,
    required String description,
    required String actionText,
    required bool commentRequired,
    bool isDestructive = false,
  }) async {
    final comment = await _promptComment(
      icon: icon,
      iconColor: iconColor,
      title: title,
      description: description,
      actionText: actionText,
      isDestructive: isDestructive,
      commentRequired: commentRequired,
    );
    if (comment == null) return;
    final normalizedComment = comment.trim();
    await _moderate(
      status,
      normalizedComment.isEmpty ? null : normalizedComment,
    );
  }

  Future<String?> _promptComment({
    required AppIconData icon,
    required Color iconColor,
    required String title,
    required String description,
    required String actionText,
    required bool isDestructive,
    required bool commentRequired,
  }) {
    return showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.transparent,
      barrierColor: AppColors.black.withValues(alpha: 0.48),
      enableDrag: true,
      builder: (_) => _ModerationCommentSheet(
        icon: icon,
        iconColor: iconColor,
        title: title,
        description: description,
        actionText: actionText,
        isDestructive: isDestructive,
        commentRequired: commentRequired,
      ),
    );
  }

  Future<void> _moderate(String status, String? comment) async {
    setState(() => _moderating = true);
    try {
      final updated = await EventCache.instance.updateStatus(
        _event.id,
        status,
        comment,
      );
      if (!mounted) return;
      setState(() => _event = updated);
    } on ApiException catch (e) {
      _showMessage(e.message);
    } catch (_) {
      _showMessage(AppLocalizations.get('somethingWentWrong'));
    } finally {
      if (mounted) setState(() => _moderating = false);
    }
  }

  void _showMessage(String message) {
    if (!mounted) return;
    showEventFeedback(context, message);
  }
}

class _OwnerStat {
  const _OwnerStat(this.label, this.value, {this.span = 1});

  final String label;
  final Object value;
  final int span;
}

class _OwnerAnalyticsSkeleton extends StatefulWidget {
  const _OwnerAnalyticsSkeleton();

  @override
  State<_OwnerAnalyticsSkeleton> createState() =>
      _OwnerAnalyticsSkeletonState();
}

class _OwnerAnalyticsSkeletonState extends State<_OwnerAnalyticsSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(begin: 0.45, end: 0.9).animate(_controller),
      child: Column(
        children: [
          _card(rows: 2),
          const SizedBox(height: AppSpacing.lg),
          _card(rows: 3),
          const SizedBox(height: AppSpacing.lg),
          _card(rows: 2),
        ],
      ),
    );
  }

  Widget _card({required int rows}) {
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        children: [
          FractionallySizedBox(widthFactor: 0.42, child: _bar(height: 14)),
          const SizedBox(height: AppSpacing.md),
          for (var index = 0; index < rows; index++) ...[
            Row(
              children: [
                Expanded(child: _block()),
                const SizedBox(width: AppSpacing.sm),
                Expanded(child: _block()),
              ],
            ),
            if (index != rows - 1) const SizedBox(height: AppSpacing.sm),
          ],
        ],
      ),
    );
  }

  Widget _block() {
    return Container(
      height: 72,
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: AppSpacing.borderRadiusMd,
      ),
    );
  }

  Widget _bar({required double height}) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: AppColors.lightGrey,
        borderRadius: BorderRadius.circular(999),
      ),
    );
  }
}

class _OwnerStatGrid extends StatelessWidget {
  const _OwnerStatGrid({required this.stats});

  final List<_OwnerStat> stats;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const spacing = AppSpacing.sm;
        final width = (constraints.maxWidth - spacing) / 2;
        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: [
            for (final stat in stats)
              SizedBox(
                width: width * stat.span + (stat.span - 1) * spacing,
                child: Container(
                  constraints: const BoxConstraints(minHeight: 82),
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md,
                    vertical: AppSpacing.sm,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.fieldBackground,
                    borderRadius: AppSpacing.borderRadiusMd,
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        '${stat.value}',
                        style: AppTextStyles.bodyLarge.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        stat.label,
                        textAlign: TextAlign.center,
                        style: AppTextStyles.bodySmall.copyWith(
                          color: AppColors.grey,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _OwnerViewsOverTime extends StatelessWidget {
  const _OwnerViewsOverTime({required this.points});

  final List<dynamic> points;

  @override
  Widget build(BuildContext context) {
    final counts = points
        .map(
          (point) =>
              ((point as Map<String, dynamic>)['count'] as num).toDouble(),
        )
        .toList();
    final total = counts.fold<double>(0, (sum, count) => sum + count);
    Map<String, dynamic>? peak;
    for (final point in points.cast<Map<String, dynamic>>()) {
      if (peak == null || (point['count'] as num) > (peak['count'] as num)) {
        peak = point;
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: double.infinity,
          child: Text(
            'Views over time',
            textAlign: TextAlign.center,
            style: AppTextStyles.bodyMedium.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        if (total == 0)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
            child: Center(
              child: Text(
                'No activity in this period',
                style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
              ),
            ),
          )
        else ...[
          SizedBox(
            width: double.infinity,
            height: 56,
            child: CustomPaint(
              size: Size.infinite,
              painter: _OwnerTrendPainter(counts),
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          if (peak != null)
            Text(
              'Peak: ${peak['count']} · ${_formatTrendDate(peak['date'] as String)}',
              style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
            ),
        ],
      ],
    );
  }

  static String _formatTrendDate(String value) {
    try {
      final date = DateTime.parse(value);
      final day = date.day.toString().padLeft(2, '0');
      final month = date.month.toString().padLeft(2, '0');
      return '$day.$month.${date.year}';
    } catch (_) {
      return value;
    }
  }
}

class _OwnerTrendPainter extends CustomPainter {
  const _OwnerTrendPainter(this.points);

  final List<double> points;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final maximum = points.fold<double>(0, (a, b) => a > b ? a : b);
    final dx = size.width / (points.length - 1);
    final baseline = size.height - 1;
    final path = Path();
    for (var i = 0; i < points.length; i++) {
      final x = dx * i;
      final y = maximum == 0
          ? baseline
          : baseline - (points[i] / maximum) * (size.height - 2);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = AppColors.primary
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _OwnerTrendPainter oldDelegate) =>
      !listEquals(oldDelegate.points, points);
}

class _OwnerTimelineEntry extends StatelessWidget {
  const _OwnerTimelineEntry({required this.entry, required this.isLast});

  final Map<String, dynamic> entry;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final action = entry['action'] as String;
    final color = _actionColor(action);
    final actor = entry['actor_name'] as String?;
    final comment = entry['comment'] as String?;
    final createdAt = entry['created_at'] as String;

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 24,
            child: Column(
              children: [
                const SizedBox(height: 4),
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(width: 2, color: AppColors.lightGrey),
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _actionLabel(action),
                          style: AppTextStyles.bodyMedium.copyWith(
                            color: color,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      Text(
                        _formatDateTime(createdAt),
                        style: AppTextStyles.bodySmall.copyWith(
                          color: AppColors.grey,
                        ),
                      ),
                    ],
                  ),
                  if (actor != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      actor,
                      style: AppTextStyles.bodySmall.copyWith(
                        color: AppColors.grey,
                      ),
                    ),
                  ],
                  if (comment?.isNotEmpty == true) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.sm,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.fieldBackground,
                        borderRadius: AppSpacing.borderRadiusMd,
                      ),
                      child: Text(comment!, style: AppTextStyles.bodyMedium),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  static Color _actionColor(String action) {
    return switch (action) {
      'approved' || 'restored' => AppColors.success,
      'rejected' || 'cancelled' => AppColors.error,
      'needs_changes' => AppColors.orange,
      'submitted' || 'resubmitted' => AppColors.primary,
      _ => AppColors.grey,
    };
  }

  static String _actionLabel(String action) {
    return switch (action) {
      'approved' => AppLocalizations.get('approvedLabel'),
      'rejected' => AppLocalizations.get('rejectedLabel'),
      'needs_changes' => AppLocalizations.get('needsChangesLabel'),
      'submitted' => AppLocalizations.get('submittedAction'),
      'resubmitted' => AppLocalizations.get('resubmitted'),
      'cancelled' => AppLocalizations.get('cancelledLabel'),
      'archived' => AppLocalizations.get('archivedLabel'),
      'restored' => AppLocalizations.get('restoredAction'),
      'edited' => AppLocalizations.get('editedAction'),
      _ => action,
    };
  }

  static String _formatDateTime(String value) {
    try {
      final date = DateTime.parse(value).toLocal();
      final month = date.month.toString().padLeft(2, '0');
      final day = date.day.toString().padLeft(2, '0');
      final hour = date.hour.toString().padLeft(2, '0');
      final minute = date.minute.toString().padLeft(2, '0');
      return '$day.$month ${date.year} $hour:$minute';
    } catch (_) {
      return value;
    }
  }
}

class _OwnerRatingsSummary extends StatelessWidget {
  const _OwnerRatingsSummary({
    required this.average,
    required this.total,
    required this.distribution,
  });

  final Object? average;
  final Object total;
  final Map<String, dynamic> distribution;

  @override
  Widget build(BuildContext context) {
    final totalCount = (total as num).toInt();
    return Column(
      children: [
        Text(
          '${(average as num).toDouble().toStringAsFixed(1)} / 5',
          style: AppTextStyles.titleLarge,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text('$totalCount reviews', style: AppTextStyles.bodySmall),
        const SizedBox(height: AppSpacing.md),
        for (var score = 5; score >= 1; score--)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.xs),
            child: Row(
              children: [
                SizedBox(width: 16, child: Text('$score')),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: LinearProgressIndicator(
                    value: totalCount == 0
                        ? 0
                        : ((distribution['$score'] as num?) ?? 0) / totalCount,
                    minHeight: 6,
                    borderRadius: AppSpacing.borderRadiusSm,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

// ─── Delete Confirm Sheet ─────────────────────────────────────────────────────

class _DeleteConfirmSheet extends StatelessWidget {
  const _DeleteConfirmSheet({required this.onConfirm, required this.onCancel});

  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final isLight = Theme.of(context).brightness == Brightness.light;
    final surface = isLight ? AppColors.surface : AppColors.surfaceDark;
    final textPrimary = isLight
        ? AppColors.textPrimary
        : AppColors.textPrimaryDark;
    final textSub = AppColors.textSecondary;

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: AppSpacing.borderRadiusTopSheet,
      ),
      padding: EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.sm,
        AppSpacing.lg,
        mq.padding.bottom + AppSpacing.md,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Center(
            child: Container(
              width: 32,
              height: 4,
              decoration: BoxDecoration(
                color: isLight ? AppColors.borderGrey : AppColors.borderDark,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'Delete event permanently?',
            style: AppTextStyles.titleMedium.copyWith(color: textPrimary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 6),
          Text(
            'This removes the event, its reminders, reviews, and moderation history. This cannot be undone.',
            style: AppTextStyles.bodyMedium.copyWith(color: textSub),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 20),
          _SheetActionRow(
            cancelColor: textSub,
            cancelBackground: isLight
                ? AppColors.fieldBackground
                : AppColors.surfaceDark,
            actionColor: AppColors.error,
            actionText: 'Delete',
            onCancel: onCancel,
            onAction: onConfirm,
          ),
        ],
      ),
    );
  }
}

class _ModerationCommentSheet extends StatefulWidget {
  const _ModerationCommentSheet({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.description,
    required this.actionText,
    required this.isDestructive,
    required this.commentRequired,
  });

  final AppIconData icon;
  final Color iconColor;
  final String title;
  final String description;
  final String actionText;
  final bool isDestructive;
  final bool commentRequired;

  @override
  State<_ModerationCommentSheet> createState() =>
      _ModerationCommentSheetState();
}

class _ModerationCommentSheetState extends State<_ModerationCommentSheet>
    with SingleTickerProviderStateMixin {
  final _controller = TextEditingController();
  bool _showComment = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final isLight = Theme.of(context).brightness == Brightness.light;
    final surface = isLight ? AppColors.surface : AppColors.surfaceDark;
    final textPrimary = isLight
        ? AppColors.textPrimary
        : AppColors.textPrimaryDark;
    final textSub = AppColors.textSecondary;
    final actionColor = widget.isDestructive
        ? AppColors.error
        : widget.iconColor;

    return AnimatedPadding(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOutCubic,
      padding: EdgeInsets.only(bottom: mq.viewInsets.bottom),
      child: Container(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: AppSpacing.borderRadiusTopSheet,
        ),
        padding: EdgeInsets.fromLTRB(
          AppSpacing.lg,
          AppSpacing.sm,
          AppSpacing.lg,
          mq.padding.bottom + AppSpacing.md,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Center(
              child: Container(
                width: 32,
                height: 4,
                decoration: BoxDecoration(
                  color: isLight ? AppColors.borderGrey : AppColors.borderDark,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 14),
            AnimatedSize(
              duration: const Duration(milliseconds: 320),
              curve: Curves.easeOutCubic,
              alignment: Alignment.topCenter,
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 280),
                switchInCurve: Curves.easeOutCubic,
                switchOutCurve: Curves.easeInCubic,
                layoutBuilder: (currentChild, previousChildren) {
                  return Stack(
                    alignment: Alignment.topCenter,
                    children: [...previousChildren, ?currentChild],
                  );
                },
                transitionBuilder: (child, animation) {
                  final curved = CurvedAnimation(
                    parent: animation,
                    curve: Curves.easeOutCubic,
                    reverseCurve: Curves.easeInCubic,
                  );
                  final offset = Tween<Offset>(
                    begin: const Offset(0, 0.06),
                    end: Offset.zero,
                  ).animate(curved);

                  return FadeTransition(
                    opacity: curved,
                    child: SlideTransition(position: offset, child: child),
                  );
                },
                child: _showComment
                    ? _buildCommentStep(
                        key: const ValueKey('comment'),
                        textPrimary: textPrimary,
                        textSub: textSub,
                        actionColor: actionColor,
                        isLight: isLight,
                      )
                    : _buildConfirmStep(
                        key: const ValueKey('confirm'),
                        textPrimary: textPrimary,
                        textSub: textSub,
                        actionColor: actionColor,
                        isLight: isLight,
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildConfirmStep({
    required Key key,
    required Color textPrimary,
    required Color textSub,
    required Color actionColor,
    required bool isLight,
  }) {
    return Column(
      key: key,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          widget.title,
          style: AppTextStyles.titleMedium.copyWith(color: textPrimary),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 4),
        Text(
          widget.description,
          style: AppTextStyles.bodyMedium.copyWith(color: textSub),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 16),
        _SheetActionRow(
          cancelColor: textSub,
          cancelBackground: isLight
              ? AppColors.fieldBackground
              : AppColors.surfaceDark,
          actionColor: actionColor,
          actionText: 'Continue',
          onCancel: () => Navigator.pop(context),
          onAction: () => setState(() => _showComment = true),
        ),
      ],
    );
  }

  Widget _buildCommentStep({
    required Key key,
    required Color textPrimary,
    required Color textSub,
    required Color actionColor,
    required bool isLight,
  }) {
    return Column(
      key: key,
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Center(
          child: Text(
            'Comment',
            style: AppTextStyles.titleMedium.copyWith(color: textPrimary),
          ),
        ),
        const SizedBox(height: 10),
        AppTextField(
          controller: _controller,
          maxLines: 3,
          maxLength: 500,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        _SheetActionRow(
          cancelColor: textSub,
          cancelBackground: isLight
              ? AppColors.fieldBackground
              : AppColors.surfaceDark,
          actionColor: actionColor,
          actionText: widget.actionText,
          onCancel: () => Navigator.pop(context),
          onAction: widget.commentRequired && _controller.text.trim().isEmpty
              ? null
              : () => Navigator.pop(context, _controller.text),
        ),
      ],
    );
  }
}

class _SheetActionRow extends StatelessWidget {
  const _SheetActionRow({
    required this.cancelColor,
    required this.cancelBackground,
    required this.actionColor,
    required this.actionText,
    required this.onCancel,
    required this.onAction,
  });

  final Color cancelColor;
  final Color cancelBackground;
  final Color actionColor;
  final String actionText;
  final VoidCallback onCancel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        GestureDetector(
          onTap: onCancel,
          child: Container(
            height: 42,
            padding: const EdgeInsets.symmetric(horizontal: 18),
            decoration: BoxDecoration(
              color: cancelBackground,
              borderRadius: AppSpacing.borderRadiusMd,
            ),
            alignment: Alignment.center,
            child: Text(
              'Cancel',
              style: AppTextStyles.labelLarge.copyWith(color: cancelColor),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: GestureDetector(
            onTap: onAction,
            child: Container(
              height: 42,
              decoration: BoxDecoration(
                color: onAction == null
                    ? actionColor.withValues(alpha: 0.45)
                    : actionColor,
                borderRadius: AppSpacing.borderRadiusMd,
              ),
              alignment: Alignment.center,
              child: Text(
                actionText,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: AppTextStyles.button.copyWith(
                  color: AppColors.white,
                  fontSize: 15,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
