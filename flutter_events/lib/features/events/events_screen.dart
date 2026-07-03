import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_store.dart';
import '../../models/category_model.dart';
import '../../models/event_model.dart';
import '../moderation/pending_events_screen.dart';
import '../submit/submit_screen.dart';
import 'event_card.dart';
import 'event_detail_screen.dart';

class EventsScreen extends StatefulWidget {
  const EventsScreen({super.key});

  @override
  State<EventsScreen> createState() => _EventsScreenState();
}

class _EventsScreenState extends State<EventsScreen> {
  bool _loading = true;
  String? _error;

  List<EventModel> _events = [];
  List<EventModel> _filtered = [];
  List<CategoryModel> _categories = [];

  final _searchController = TextEditingController();
  String _search = '';
  String? _selectedCategory;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        fetchApprovedEvents(),
        fetchCategories(),
      ]);
      if (!mounted) return;
      setState(() {
        _events = results[0] as List<EventModel>;
        _categories = results[1] as List<CategoryModel>;
        _loading = false;
        _applyFilters();
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _applyFilters() {
    final search = _search.trim().toLowerCase();
    _filtered = _events.where((event) {
      final matchesCategory =
          _selectedCategory == null || event.category == _selectedCategory;
      final matchesSearch =
          search.isEmpty || event.title.toLowerCase().contains(search);
      return matchesCategory && matchesSearch;
    }).toList();
  }

  Future<void> _openSubmit() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const SubmitScreen()),
    );
    await _load();
  }

  Future<void> _openPending() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const PendingEventsScreen()),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppAppBar(
        title: 'Ивенты',
        actions: [
          if (AuthStore.isModerator)
            IconButton(
              icon: const Icon(Icons.fact_check_outlined),
              onPressed: _openPending,
            ),
          IconButton(
            icon: const Icon(Icons.add_outlined),
            onPressed: _openSubmit,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: AppLoader());
    if (_error != null) {
      return Center(
        child: Padding(
          padding: AppSpacing.screenPadding,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.df),
              AppSecondaryButton(text: 'Повторить', onPressed: _load),
            ],
          ),
        ),
      );
    }

    return Column(
      children: [
        Padding(
          padding: AppSpacing.screenHorizontal,
          child: GlobalSearchBar(
            controller: _searchController,
            hint: 'Поиск',
            onChanged: (value) => setState(() {
              _search = value;
              _applyFilters();
            }),
            onClear: () => setState(() {
              _search = '';
              _applyFilters();
            }),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        _buildCategoryBar(),
        Expanded(
          child: _filtered.isEmpty
              ? Center(
                  child: Text(
                    'Ничего не найдено',
                    style: Theme.of(context)
                        .textTheme
                        .bodyLarge
                        ?.copyWith(color: AppColors.grey),
                  ),
                )
              : ListView.builder(
                  padding: AppSpacing.screenPadding,
                  itemCount: _filtered.length,
                  itemBuilder: (context, index) {
                    final event = _filtered[index];
                    return Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.md),
                      child: EventCard(
                        event: event,
                        onTap: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => EventDetailScreen(event: event),
                          ),
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildCategoryBar() {
    final labels = ['Все', ..._categories.map((c) => c.name)];
    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: AppSpacing.screenHorizontal,
        itemCount: labels.length,
        separatorBuilder: (_, _) => const SizedBox(width: AppSpacing.sm),
        itemBuilder: (context, index) {
          final label = labels[index];
          final isAll = index == 0;
          final selected =
              isAll ? _selectedCategory == null : _selectedCategory == label;
          return FilterChip(
            label: Text(label),
            selected: selected,
            showCheckmark: false,
            backgroundColor: AppColors.fieldBackground,
            selectedColor: AppColors.primary,
            side: BorderSide.none,
            shape: const StadiumBorder(),
            labelStyle: AppTextStyles.chip.copyWith(
              color: selected ? AppColors.white : AppColors.textSecondary,
            ),
            onSelected: (_) => setState(() {
              _selectedCategory = isAll ? null : label;
              _applyFilters();
            }),
          );
        },
      ),
    );
  }
}
