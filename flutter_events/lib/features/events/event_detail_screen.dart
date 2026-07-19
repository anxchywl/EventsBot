import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/auth_store.dart';
import '../../core/cache_store.dart';
import '../../core/exceptions.dart';
import '../../core/localization.dart';
import '../../models/event_model.dart';
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
    // Opened from a list; pull the freshest copy in the background (cache-first
    // for instant render, revalidated silently).
    unawaited(_refreshEvent());
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasImage = _event.coverUrl != null;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: NestedScrollView(
        headerSliverBuilder: (ctx, _) => [
          AppSliverAppBar(
            leading: IconButton(
              icon: const AppIcon(AppIcons.back, color: AppColors.textPrimary),
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
          if (AuthStore.isAdmin && _event.itEquipment?.isNotEmpty == true)
            _section('IT Equipment', _event.itEquipment!),
          if (AuthStore.isAdmin && _event.materials?.isNotEmpty == true)
            _section('Materials', _event.materials!),
          if (_event.registrationUrl?.isNotEmpty == true)
            _registrationCard(_event.registrationUrl!, theme),
          const SizedBox(height: AppSpacing.xxl),
        ],
      ),
      ),
      bottomNavigationBar: _buildBottomBar(),
    );
  }

  Widget? _buildBottomBar() {
    if (_canModerate) {
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.df,
            AppSpacing.sm,
            AppSpacing.df,
            AppSpacing.md,
          ),
          child: _moderationSection(),
        ),
      );
    }
    if (_canResubmit || _canCancel || _canDelete) {
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.df,
            AppSpacing.sm,
            AppSpacing.df,
            AppSpacing.md,
          ),
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
        ),
      );
    }
    return null;
  }

  Future<void> _openResubmit() async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Colors.transparent,
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
      setState(() => _event = updated);
      _showMessage('Event cancelled');
    } on ApiException catch (error) {
      _showMessage(error.message);
    } catch (_) {
      _showMessage(AppLocalizations.get('somethingWentWrong'));
    } finally {
      if (mounted) setState(() => _lifecycleMutating = false);
    }
  }

  Future<void> _confirmDelete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Delete event permanently?'),
        content: const Text(
          'This removes the event, its reminders, reviews, and moderation history. This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AppLocalizations.get('cancel')),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text(
              'Delete',
              style: TextStyle(color: AppColors.error),
            ),
          ),
        ],
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
                    fontWeight: FontWeight.w800,
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
                            fontWeight: FontWeight.w700,
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
          _fact(AppIcons.calendar, _formatDate(_event.eventDate)),
          _factDivider(),
          _fact(AppIcons.time, _timeRange()),
          _factDivider(),
          _fact(AppIcons.location, _event.location),
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

  Widget _fact(AppIconData icon, String value) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.md, horizontal: AppSpacing.xs),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
            ),
            child: AppIcon(icon, size: 22, color: AppColors.primary),
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
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: AppColors.fieldBackground,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: AppIcon(icon, size: 18, color: AppColors.textSecondary),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                ],
                Text(
                  title,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
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
    const labelStyle = TextStyle(
      fontSize: 14,
      fontWeight: FontWeight.w600,
      letterSpacing: -0.1,
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
        child: const Text('Approve', style: labelStyle),
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
          foregroundColor: const WidgetStatePropertyAll(Color(0xFFB87800)),
          overlayColor: WidgetStatePropertyAll(
            AppColors.warning.withValues(alpha: 0.15),
          ),
        ),
        child: const Text('Edits', style: labelStyle),
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
        child: const Text('Reject', style: labelStyle),
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
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.48),
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
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(SnackBar(content: Text(message)));
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
    final surface = isLight ? Colors.white : const Color(0xFF1C1C1E);
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;
    final textSub = isLight ? const Color(0xFF6B6B80) : const Color(0xFF8E8EA3);
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
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: EdgeInsets.fromLTRB(20, 8, 20, mq.padding.bottom + 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Center(
              child: Container(
                width: 32,
                height: 4,
                decoration: BoxDecoration(
                  color: isLight
                      ? const Color(0xFFD1D1D6)
                      : const Color(0xFF48484A),
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
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.3,
            color: textPrimary,
            height: 1.2,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 4),
        Text(
          widget.description,
          style: TextStyle(fontSize: 13, color: textSub, height: 1.4),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 16),
        _SheetActionRow(
          cancelColor: textSub,
          cancelBackground: isLight
              ? const Color(0xFFF2F2F7)
              : const Color(0xFF2C2C2E),
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
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              letterSpacing: -0.3,
              color: textPrimary,
              height: 1.2,
            ),
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
              ? const Color(0xFFF2F2F7)
              : const Color(0xFF2C2C2E),
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
              borderRadius: BorderRadius.circular(12),
            ),
            alignment: Alignment.center,
            child: Text(
              'Cancel',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: cancelColor,
              ),
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
                color: actionColor,
                borderRadius: BorderRadius.circular(12),
              ),
              alignment: Alignment.center,
              child: Text(
                actionText,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -0.2,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
