import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api_client.dart';
import '../../core/auth_store.dart';
import '../../core/exceptions.dart';
import '../../core/localization.dart';
import '../../models/event_model.dart';

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

  bool get _canModerate =>
      AuthStore.isAdmin &&
      (_event.status == 'pending' || _event.status == 'needs_changes');

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasImage = _event.coverUrl != null;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: AppColors.textPrimary),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.df, 0, AppSpacing.df, AppSpacing.xxl),
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
          if (_event.moderationNote?.isNotEmpty == true)
            _section(
              AppLocalizations.get('coordinatorComment'),
              _event.moderationNote!,
            ),
          const SizedBox(height: AppSpacing.xxl),
        ],
      ),
      bottomNavigationBar: _canModerate
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                    AppSpacing.df, AppSpacing.sm, AppSpacing.df, AppSpacing.md),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_event.moderationNote != null) ...[
                      Text(
                        _event.moderationNote!,
                        style: AppTextStyles.bodySmall
                            .copyWith(color: _event.statusColor),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                    ],
                    _moderationSection(),
                  ],
                ),
              ),
            )
          : null,
    );
  }

  Widget _titleCard(ThemeData theme) {
    return AppCard(
      padding: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _event.title,
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  _event.organizerName,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: AppColors.textSecondary,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          if (widget.showStatus ||
              (_event.status != 'approved' && _event.status != 'rejected'))
            Container(
              padding: const EdgeInsets.symmetric(
                vertical: AppSpacing.sm,
                horizontal: AppSpacing.md,
              ),
              color: _event.statusColor.withValues(alpha: 0.12),
              child: Row(
                children: [
                  if (_event.status != 'approved' &&
                      _event.status != 'rejected' &&
                      _event.status != 'pending') ...[
                    Icon(
                      Icons.info_outline_rounded,
                      size: 14,
                      color: _event.statusColor,
                    ),
                    const SizedBox(width: AppSpacing.xs),
                  ],
                  Expanded(
                    child: Text(
                      _event.statusLabel,
                      style: AppTextStyles.bodySmall.copyWith(
                        color: _event.statusColor,
                        fontWeight: FontWeight.w600,
                        fontSize: 12,
                      ),
                    ),
                  ),
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
          horizontal: AppSpacing.df, vertical: AppSpacing.xs),
      child: Column(
        children: [
          _fact(Icons.calendar_today_rounded, _formatDate(_event.eventDate)),
          _factDivider(),
          _fact(Icons.schedule_rounded, _timeRange()),
          _factDivider(),
          _fact(Icons.place_rounded, _event.location),
          _factDivider(),
          _fact(Icons.category_rounded, _event.category),
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

  Widget _fact(IconData icon, String value) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 20, color: AppColors.primary),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              value,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }

  Widget _factDivider() =>
      const Divider(height: 1, thickness: 1, color: AppColors.borderGrey);

  Widget _section(String title, String body, [IconData? icon]) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.lg),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (icon != null) ...[
                  Icon(icon, size: 20, color: AppColors.primary),
                  const SizedBox(width: AppSpacing.sm),
                ],
                Text(
                  title,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: AppColors.primary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              body,
              style: theme.textTheme.bodyMedium?.copyWith(height: 1.55),
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
            Row(
              children: [
                const Icon(Icons.link_rounded, size: 20, color: AppColors.primary),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'Registration',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: AppColors.primary,
                  ),
                ),
              ],
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
        RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(12))),
      ),
    );
    const labelStyle = TextStyle(
      fontSize: 14,
      fontWeight: FontWeight.w600,
      letterSpacing: -0.1,
    );

    return Row(
      children: [
        Expanded(
          child: SizedBox(
            height: h,
            child: ElevatedButton(
              onPressed: _moderating ? null : _confirmApprove,
              style: style.copyWith(
                backgroundColor: WidgetStateProperty.resolveWith((states) =>
                  states.contains(WidgetState.disabled)
                    ? AppColors.success.withValues(alpha: 0.5)
                    : AppColors.success,
                ),
                foregroundColor: const WidgetStatePropertyAll(AppColors.white),
              ),
              child: _moderating
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(AppColors.white),
                      ),
                    )
                  : const Text('Approve', style: labelStyle),
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: SizedBox(
            height: h,
            child: ElevatedButton(
              onPressed: _confirmRequestEdits,
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
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: SizedBox(
            height: h,
            child: ElevatedButton(
              onPressed: _confirmReject,
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
          ),
        ),
      ],
    );
  }

  Future<void> _confirmApprove() async {
    final confirmed = await AppPremiumDialog.show(
      context: context,
      icon: AppIcons.check,
      iconColor: AppColors.success,
      title: 'Approve event?',
      description: 'The event will be published and the organiser notified.',
      confirmText: 'Approve',
      cancelText: 'Cancel',
      showIcon: false,
    );
    if (!confirmed || !mounted) return;
    await _moderate('approved', null);
  }

  Future<void> _confirmReject() async {
    final confirmed = await AppPremiumDialog.show(
      context: context,
      icon: AppIcons.close,
      iconColor: AppColors.error,
      title: 'Reject event?',
      description: 'The organiser will be notified that the request was declined.',
      confirmText: 'Reject',
      cancelText: 'Cancel',
      isDestructive: true,
      showIcon: false,
    );
    if (!confirmed || !mounted) return;
    await _moderateWithComment('rejected');
  }

  Future<void> _confirmRequestEdits() async {
    final confirmed = await AppPremiumDialog.show(
      context: context,
      icon: AppIcons.edit,
      iconColor: AppColors.warning,
      title: 'Request changes?',
      description: 'Add a comment explaining what needs to be fixed.',
      confirmText: 'Continue',
      cancelText: 'Cancel',
      showIcon: false,
    );
    if (!confirmed || !mounted) return;
    await _moderateWithComment('needs_changes');
  }

  Future<void> _moderateWithComment(String status) async {
    final comment = await _promptComment();
    if (comment == null) return;
    await _moderate(status, comment.isEmpty ? null : comment);
  }

  Future<String?> _promptComment() {
    return showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.48),
      enableDrag: true,
      builder: (_) => const _CommentSheet(),
    );
  }

  Future<void> _moderate(String status, String? comment) async {
    setState(() => _moderating = true);
    try {
      final updated = await updateEventStatus(_event.id, status, comment);
      if (!mounted) return;
      setState(() => _event = updated);
      _showMessage('Done');
    } on ApiException catch (e) {
      _showMessage(e.message);
    } finally {
      if (mounted) setState(() => _moderating = false);
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}

// ── Comment bottom sheet ──────────────────────────────────────────────────────

class _CommentSheet extends StatefulWidget {
  const _CommentSheet();

  @override
  State<_CommentSheet> createState() => _CommentSheetState();
}

class _CommentSheetState extends State<_CommentSheet> {
  final _controller = TextEditingController();

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
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Handle
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

            Text(
              'Comment',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                letterSpacing: -0.3,
                color: textPrimary,
                height: 1.2,
              ),
            ),
            const SizedBox(height: 10),

            AppTextField(controller: _controller, maxLines: 3),
            const SizedBox(height: 12),

            Row(
              children: [
                // Cancel
                GestureDetector(
                  onTap: () => Navigator.pop(context),
                  child: Container(
                    height: 42,
                    padding: const EdgeInsets.symmetric(horizontal: 18),
                    decoration: BoxDecoration(
                      color: isLight
                          ? const Color(0xFFF2F2F7)
                          : const Color(0xFF2C2C2E),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      'Cancel',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: textSub,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                // Done — fills rest
                Expanded(
                  child: GestureDetector(
                    onTap: () => Navigator.pop(context, _controller.text),
                    child: Container(
                      height: 42,
                      decoration: BoxDecoration(
                        color: AppColors.primary,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      alignment: Alignment.center,
                      child: const Text(
                        'Done',
                        style: TextStyle(
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
            ),
          ],
        ),
      ),
    );
  }
}
