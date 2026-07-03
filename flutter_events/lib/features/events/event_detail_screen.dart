import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_store.dart';
import '../../core/exceptions.dart';
import '../../models/event_model.dart';

class EventDetailScreen extends StatefulWidget {
  const EventDetailScreen({super.key, required this.event});

  final EventModel event;

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
    final sections = <Widget>[];
    if (!_event.isApproved) sections.add(_statusBanner());
    sections.add(_titleBlock());
    sections.add(_infoRows());
    sections.add(const Divider(color: AppColors.divider));
    sections.add(_textSection('Описание', _event.description));
    if (_event.itEquipment != null) {
      sections.add(_textSection('IT-оборудование', _event.itEquipment!));
    }
    if (_event.materials != null) {
      sections.add(_textSection('Материалы', _event.materials!));
    }
    if (_event.registrationUrl != null) {
      sections.add(_registrationButton());
    }
    if (_canModerate) sections.add(_moderationSection());

    final children = <Widget>[];
    for (var i = 0; i < sections.length; i++) {
      if (i > 0) children.add(const SizedBox(height: AppSpacing.lg));
      children.add(sections[i]);
    }

    return Scaffold(
      appBar: AppAppBar(showBackButton: true, title: _event.title),
      body: SingleChildScrollView(
        padding: AppSpacing.screenPadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: children,
        ),
      ),
    );
  }

  Widget _statusBanner() {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: _event.statusColor.withValues(alpha: 0.1),
        border: Border(
          left: BorderSide(color: _event.statusColor, width: 4),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _event.statusLabel,
            style: AppTextStyles.sectionHeader.copyWith(
              color: _event.statusColor,
            ),
          ),
          if (_event.moderationNote != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              _event.moderationNote!,
              style:
                  theme.textTheme.bodySmall?.copyWith(color: AppColors.grey),
            ),
          ],
        ],
      ),
    );
  }

  Widget _titleBlock() {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(_event.title, style: theme.textTheme.headlineSmall),
        const SizedBox(height: AppSpacing.xs),
        Text(
          _event.organizerName,
          style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.grey),
        ),
      ],
    );
  }

  Widget _infoRows() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _infoRow(Icons.calendar_today_outlined, _event.eventDate),
        const SizedBox(height: AppSpacing.sm),
        _infoRow(Icons.access_time_outlined, _event.eventTime),
        const SizedBox(height: AppSpacing.sm),
        _infoRow(Icons.location_on_outlined, _event.location),
        const SizedBox(height: AppSpacing.sm),
        _infoRow(Icons.category_outlined, _event.category),
      ],
    );
  }

  Widget _infoRow(IconData icon, String text) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: AppSpacing.iconSm, color: AppColors.grey),
        const SizedBox(width: AppSpacing.sm),
        Expanded(child: Text(text, style: theme.textTheme.bodyMedium)),
      ],
    );
  }

  Widget _textSection(String title, String body) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: AppTextStyles.sectionHeader),
        const SizedBox(height: AppSpacing.sm),
        Text(body, style: theme.textTheme.bodyMedium),
      ],
    );
  }

  Widget _registrationButton() {
    return AppPrimaryButton(
      text: 'Зарегистрироваться',
      onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Открыть: ${_event.registrationUrl}')),
      ),
    );
  }

  Widget _moderationSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Модерация', style: AppTextStyles.sectionHeader),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            Expanded(
              child: AppPrimaryButton(
                text: 'Одобрить',
                isLoading: _moderating,
                onPressed: () => _moderate('approved', null),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: AppSecondaryButton(
                text: 'Правки',
                onPressed: () => _moderateWithComment('needs_changes'),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: OutlinedButton(
                onPressed: () => _moderateWithComment('rejected'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.error,
                  side: const BorderSide(color: AppColors.error),
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
                ),
                child: const FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text('Отклонить'),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _moderateWithComment(String status) async {
    final comment = await _promptComment();
    if (comment == null) return;
    await _moderate(status, comment.isEmpty ? null : comment);
  }

  Future<String?> _promptComment() {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Комментарий'),
          content: AppTextField(controller: controller, maxLines: 3),
          actions: [
            AppTextButton(
              text: 'Отмена',
              onPressed: () => Navigator.pop(dialogContext),
            ),
            AppTextButton(
              text: 'Готово',
              onPressed: () => Navigator.pop(dialogContext, controller.text),
            ),
          ],
        );
      },
    );
  }

  Future<void> _moderate(String status, String? comment) async {
    setState(() => _moderating = true);
    try {
      final updated = await updateEventStatus(_event.id, status, comment);
      if (!mounted) return;
      setState(() => _event = updated);
      _showMessage('Готово');
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
