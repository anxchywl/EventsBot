import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/localization.dart';
import '../shared/loading_skeleton.dart';

/// One option in a capped selection sheet.
class SelectionOption<T> {
  final String title;
  final T value;
  final String? subtitle;

  const SelectionOption({
    required this.title,
    required this.value,
    this.subtitle,
  });
}

/// A selection sheet that grows only to its content and is capped at ~80% of the
/// screen (scrolling past that). Unlike the shared selection sheet, a long list
/// never takes over the whole screen. Returns the chosen value, or null if
/// dismissed.
Future<T?> showCappedSelection<T>({
  required BuildContext context,
  required String title,
  required List<SelectionOption<T>> options,
  T? selectedValue,
}) {
  return AppBottomSheet.show<T>(
    context: context,
    maxHeightFraction: 0.8,
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 2, 20, 12),
          child: Text(
            title,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w600,
              letterSpacing: -0.3,
              height: 1.2,
            ),
          ),
        ),
        ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.65,
          ),
          child: ListView.builder(
            shrinkWrap: true,
            padding: EdgeInsets.only(
              left: AppSpacing.sm,
              right: AppSpacing.sm,
              bottom: MediaQuery.paddingOf(context).bottom + AppSpacing.lg,
            ),
            itemCount: options.length,
            itemBuilder: (ctx, i) {
              final option = options[i];
              final selected = option.value == selectedValue;
              return ListTile(
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                ),
                title: Text(
                  option.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTextStyles.bodyLarge.copyWith(
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
                subtitle: option.subtitle == null
                    ? null
                    : Text(
                        option.subtitle!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTextStyles.bodySmall.copyWith(
                          color: AppColors.grey,
                        ),
                      ),
                trailing: selected
                    ? const Icon(Icons.check, color: AppColors.primary)
                    : null,
                onTap: () => Navigator.of(ctx).pop(option.value),
              );
            },
          ),
        ),
      ],
    ),
  );
}

/// One row in a "show all" ranking sheet.
class RankRow {
  final String label;
  final String value;
  final String? caption;

  const RankRow({required this.label, required this.value, this.caption});
}

/// Opens the full, server-sorted ranking as a bottom sheet. [loadPage] fetches a
/// page server-side (never the whole list at once); pagination fires on scroll.
Future<void> showRankingSheet({
  required BuildContext context,
  required String title,
  required Future<List<RankRow>> Function(int offset, int limit) loadPage,
}) {
  return AppBottomSheet.show<void>(
    context: context,
    maxHeightFraction: 0.8,
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 2, 20, 12),
          child: Text(
            title,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w600,
              letterSpacing: -0.3,
              height: 1.2,
            ),
          ),
        ),
        _RankingSheet(loadPage: loadPage),
      ],
    ),
  );
}

class _RankingSheet extends StatefulWidget {
  const _RankingSheet({required this.loadPage});

  final Future<List<RankRow>> Function(int offset, int limit) loadPage;

  @override
  State<_RankingSheet> createState() => _RankingSheetState();
}

class _RankingSheetState extends State<_RankingSheet> {
  static const _pageSize = 20;

  final ScrollController _scroll = ScrollController();
  List<RankRow> _items = [];
  bool _loading = true;
  bool _loadingMore = false;
  bool _hasMore = true;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _reload();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 240) {
      _loadMore();
    }
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await widget.loadPage(0, _pageSize);
      if (!mounted) return;
      setState(() {
        _items = page;
        _hasMore = page.length == _pageSize;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _loading || !_hasMore) return;
    setState(() => _loadingMore = true);
    try {
      final page = await widget.loadPage(_items.length, _pageSize);
      if (!mounted) return;
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
    // Grow only to the content, capped so the sheet never exceeds ~80% of the
    // screen (leaving room for the sheet's handle/title/padding).
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.7,
      ),
      child: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const AppSheetSkeleton();
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
    if (_items.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Center(
          child: Text(
            AppLocalizations.get('nothingYet'),
            style: AppTextStyles.bodyMedium.copyWith(color: AppColors.grey),
          ),
        ),
      );
    }
    return ListView.builder(
      controller: _scroll,
      shrinkWrap: true,
      padding: EdgeInsets.only(
        left: AppSpacing.lg,
        right: AppSpacing.lg,
        bottom: MediaQuery.paddingOf(context).bottom + AppSpacing.lg,
      ),
      itemCount: _items.length + (_hasMore ? 1 : 0),
      itemBuilder: (context, index) {
        if (index >= _items.length) {
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
        return _RankTile(rank: index + 1, row: _items[index]);
      },
    );
  }
}

class _RankTile extends StatelessWidget {
  const _RankTile({required this.rank, required this.row});

  final int rank;
  final RankRow row;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SizedBox(
            width: 24,
            child: Text(
              '$rank',
              style: AppTextStyles.bodyMedium.copyWith(
                color: AppColors.grey,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  row.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTextStyles.bodyMedium.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (row.caption != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    row.caption!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTextStyles.bodySmall.copyWith(
                      color: AppColors.grey,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Text(
            row.value,
            style: AppTextStyles.bodyMedium.copyWith(
              fontWeight: FontWeight.w700,
              color: AppColors.primary,
            ),
          ),
        ],
      ),
    );
  }
}
