import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/localization.dart';
import '../../models/analytics_model.dart';

/// Result of the event-picker sheet. A null [event] means "All events" (clear
/// the event filter); a non-null selection scopes analytics to that event.
class EventPickerResult {
  final AnalyticsEventOption? event;
  const EventPickerResult(this.event);
}

/// Opens the searchable, lazily-paginated event picker as a bottom sheet.
/// Returns null if dismissed without a choice (preserving the current filter).
Future<EventPickerResult?> pickAnalyticsEvent(
  BuildContext context, {
  int? selectedId,
}) {
  return AppBottomSheet.show<EventPickerResult>(
    context: context,
    title: AppLocalizations.get('selectEvent'),
    maxHeightFraction: 0.85,
    child: _EventPickerSheet(selectedId: selectedId),
  );
}

/// Small status pill reused for event rows.
Color statusColor(String status) {
  switch (status) {
    case 'approved':
      return AppColors.success;
    case 'pending':
    case 'resubmitted':
    case 'needs_changes':
      return AppColors.orange;
    case 'rejected':
      return AppColors.error;
    default: // archived / cancelled
      return AppColors.grey;
  }
}

class _EventPickerSheet extends StatefulWidget {
  const _EventPickerSheet({this.selectedId});

  final int? selectedId;

  @override
  State<_EventPickerSheet> createState() => _EventPickerSheetState();
}

class _EventPickerSheetState extends State<_EventPickerSheet> {
  static const _pageSize = 20;

  final ScrollController _scroll = ScrollController();
  final TextEditingController _searchCtrl = TextEditingController();
  Timer? _debounce;

  List<AnalyticsEventOption> _items = [];
  String _query = '';
  bool _loading = true;
  bool _loadingMore = false;
  bool _hasMore = true;
  Object? _error;
  int _requestId = 0;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _reload();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _scroll.dispose();
    _searchCtrl.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    // debounce keystrokes so we don't fire a request per character
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      if (value.trim() == _query) return;
      _query = value.trim();
      _reload();
    });
  }

  void _onScroll() {
    if (_scroll.position.pixels >=
        _scroll.position.maxScrollExtent - 240) {
      _loadMore();
    }
  }

  Future<void> _reload() async {
    final requestId = ++_requestId;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await fetchAnalyticsEvents(
        search: _query,
        limit: _pageSize,
        offset: 0,
      );
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _items = page;
        _hasMore = page.length == _pageSize;
        _loading = false;
      });
    } catch (e) {
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _loading || !_hasMore) return;
    final requestId = _requestId;
    setState(() => _loadingMore = true);
    try {
      final page = await fetchAnalyticsEvents(
        search: _query,
        limit: _pageSize,
        offset: _items.length,
      );
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _items = [..._items, ...page];
        _hasMore = page.length == _pageSize;
        _loadingMore = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadingMore = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          child: GlobalSearchBar(
            controller: _searchCtrl,
            hint: AppLocalizations.get('searchEvents'),
            autofocus: false,
            onChanged: _onSearchChanged,
            onClear: () {
              _query = '';
              _reload();
            },
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Flexible(child: _buildList()),
      ],
    );
  }

  Widget _buildList() {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: Center(child: AppLoader()),
      );
    }
    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(AppLocalizations.get('failedToLoad')),
            const SizedBox(height: AppSpacing.md),
            AppSecondaryButton(
              text: AppLocalizations.get('retry'),
              onPressed: _reload,
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      itemCount: 1 + (_items.isEmpty ? 1 : _items.length) + (_hasMore ? 1 : 0),
      itemBuilder: (context, index) {
        // row 0 is always the "All events" reset option
        if (index == 0) {
          return _AllEventsTile(
            selected: widget.selectedId == null,
            onTap: () =>
                Navigator.of(context).pop(const EventPickerResult(null)),
          );
        }
        if (_items.isEmpty) {
          return Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Center(
              child: Text(
                AppLocalizations.get('noEventsFound'),
                style:
                    AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
              ),
            ),
          );
        }
        final itemIndex = index - 1;
        if (itemIndex >= _items.length) {
          // trailing loader while the next page streams in
          return const Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: Center(
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          );
        }
        final event = _items[itemIndex];
        return _EventTile(
          event: event,
          selected: event.id == widget.selectedId,
          onTap: () =>
              Navigator.of(context).pop(EventPickerResult(event)),
        );
      },
    );
  }
}

class _AllEventsTile extends StatelessWidget {
  const _AllEventsTile({required this.selected, required this.onTap});

  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      leading: const Icon(Icons.all_inclusive, color: AppColors.primary),
      title: Text(
        AppLocalizations.get('allEvents'),
        style: AppTextStyles.bodyLarge.copyWith(fontWeight: FontWeight.w700),
      ),
      trailing: selected
          ? const Icon(Icons.check, color: AppColors.primary)
          : null,
      onTap: onTap,
    );
  }
}

class _EventTile extends StatelessWidget {
  const _EventTile({
    required this.event,
    required this.selected,
    required this.onTap,
  });

  final AnalyticsEventOption event;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      title: Text(
        event.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: AppTextStyles.bodyLarge.copyWith(fontWeight: FontWeight.w600),
      ),
      subtitle: Text(
        '${event.category} · ${event.eventDate}',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
      ),
      trailing: Container(
        padding:
            const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 3),
        decoration: BoxDecoration(
          color: statusColor(event.status).withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(
          event.status,
          style: AppTextStyles.bodySmall.copyWith(
            color: statusColor(event.status),
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      selected: selected,
      onTap: onTap,
    );
  }
}
