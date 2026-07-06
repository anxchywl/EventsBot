import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
    maxHeightFraction: 0.8,
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
  final FocusNode _focusNode = FocusNode();
  Timer? _debounce;

  List<AnalyticsEventOption> _items = [];
  String _query = '';
  bool _loading = true;
  bool _loadingMore = false;
  bool _hasMore = true;
  Object? _error;
  int _requestId = 0;
  bool _searchActive = false;
  bool _centeredSelected = false;

  final GlobalKey _selectedKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _focusNode.addListener(_onFocusChange);
    _reload();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _scroll.dispose();
    _searchCtrl.dispose();
    _focusNode.removeListener(_onFocusChange);
    _focusNode.dispose();
    super.dispose();
  }

  void _onFocusChange() {
    final focused = _focusNode.hasFocus;
    if (focused != _searchActive) {
      setState(() => _searchActive = focused);
    }
  }

  void _dismissSearch() {
    _focusNode.unfocus();
  }

  /// Mirrors _buildFocusAnim from submit_screen: collapses [child] to zero
  /// height when [isVisible] is false, using the same curve + durations.
  Widget _focusAnim(Widget child, {required bool isVisible}) {
    return AnimatedSize(
      duration: const Duration(milliseconds: 350),
      curve: Curves.fastOutSlowIn,
      alignment: Alignment.topCenter,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 250),
        layoutBuilder: (currentChild, previousChildren) => Stack(
          clipBehavior: Clip.hardEdge,
          alignment: Alignment.topCenter,
          children: [
            for (final prev in previousChildren)
              Positioned(left: 0, right: 0, top: 0, child: prev),
            ?currentChild,
          ],
        ),
        transitionBuilder: (child, animation) =>
            FadeTransition(opacity: animation, child: child),
        child: isVisible
            ? child
            : const SizedBox(
                key: ValueKey('hidden'),
                width: double.infinity,
                height: 0,
              ),
      ),
    );
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
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 240) {
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
      _centerSelectedEvent(requestId);
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

  Future<void> _centerSelectedEvent(int requestId) async {
    if (_centeredSelected || widget.selectedId == null || _query.isNotEmpty) {
      return;
    }
    _centeredSelected = true;
    while (mounted &&
        requestId == _requestId &&
        _hasMore &&
        !_items.any((event) => event.id == widget.selectedId)) {
      final page = await fetchAnalyticsEvents(
        search: _query,
        limit: _pageSize,
        offset: _items.length,
      );
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _items = [..._items, ...page];
        _hasMore = page.length == _pageSize;
      });
      if (page.isEmpty) break;
    }
    if (!mounted || requestId != _requestId) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ctx = _selectedKey.currentContext;
      if (ctx == null || !ctx.mounted) return;
      Scrollable.ensureVisible(
        ctx,
        alignment: 0.5,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOutCubic,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final maxListHeight = mq.size.height * 0.65;
    final isLight = Theme.of(context).brightness == Brightness.light;
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;
    // Mirror submit_screen's _isEditing: keyboard is actually up.
    final keyboardUp = mq.viewInsets.bottom > 0;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // ── Title — collapses while keyboard is open ─────────────────
        _focusAnim(
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 2, 20, 12),
            child: Text(
              AppLocalizations.get('selectEvent'),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w600,
                letterSpacing: -0.3,
                height: 1.2,
                color: textPrimary,
              ),
            ),
          ),
          isVisible: !keyboardUp,
        ),

        // ── Search bar + Done button ─────────────────────────────────
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: GlobalSearchBar(
                  controller: _searchCtrl,
                  focusNode: _focusNode,
                  hint: AppLocalizations.get('searchEvents'),
                  autofocus: false,
                  inputFormatters: [SanitizingFormatter()],
                  onChanged: _onSearchChanged,
                  onClear: () {
                    _query = '';
                    _reload();
                  },
                ),
              ),
              // Done button — same AnimatedSize as submit_screen's Done
              AnimatedSize(
                duration: const Duration(milliseconds: 350),
                curve: Curves.fastOutSlowIn,
                child: _searchActive
                    ? GestureDetector(
                        onTap: _dismissSearch,
                        child: Padding(
                          padding: const EdgeInsets.only(left: 10),
                          child: TweenAnimationBuilder<double>(
                            tween: Tween(begin: 0.0, end: 1.0),
                            duration: const Duration(milliseconds: 250),
                            curve: Curves.fastOutSlowIn,
                            builder: (context, t, child) => Opacity(
                              opacity: t,
                              child: Transform.translate(
                                offset: Offset(6 * (1 - t), 0),
                                child: child,
                              ),
                            ),
                            child: Text(
                              AppLocalizations.get('done'),
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                                color: AppColors.primary,
                              ),
                            ),
                          ),
                        ),
                      )
                    : const SizedBox.shrink(),
              ),
            ],
          ),
        ),

        // ── Event list — collapses while keyboard is open ─────────────
        _focusAnim(
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: AppSpacing.sm),
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: maxListHeight),
                child: _buildList(),
              ),
            ],
          ),
          isVisible: !keyboardUp,
        ),
      ],
    );
  }

  Widget _buildList() {
    if (_loading) {
      return const SizedBox(height: 120, child: Center(child: AppLoader()));
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
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        0,
        AppSpacing.md,
        AppSpacing.xl,
      ),
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
                style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
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
        final isSelected = event.id == widget.selectedId;
        return _EventTile(
          key: isSelected ? _selectedKey : null,
          event: event,
          selected: isSelected,
          onTap: () => Navigator.of(context).pop(EventPickerResult(event)),
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

// Converts a YYYY-MM-DD string from the backend to dd.mm.yyyy display format.
String _fmtDate(String iso) {
  final parts = iso.split('-');
  if (parts.length != 3) return iso;
  return '${parts[2]}.${parts[1]}.${parts[0]}';
}

class _EventTile extends StatelessWidget {
  const _EventTile({
    super.key,
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
        '${event.category} · ${_fmtDate(event.eventDate)}',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: AppTextStyles.bodySmall.copyWith(color: AppColors.grey),
      ),
      trailing: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: 3,
        ),
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

class SanitizingFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    String text = newValue.text;
    if (text.startsWith(' ')) {
      text = text.trimLeft();
    }
    text = text.replaceAll(RegExp(r'\s{2,}'), ' ');
    text = text
        .replaceAll("'", "")
        .replaceAll('"', "")
        .replaceAll(';', "")
        .replaceAll('--', "")
        .replaceAll('/*', "")
        .replaceAll('*/', "");

    int selectionIndex =
        newValue.selection.end - (newValue.text.length - text.length);
    if (selectionIndex < 0) selectionIndex = 0;
    if (selectionIndex > text.length) selectionIndex = text.length;

    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: selectionIndex),
    );
  }
}
