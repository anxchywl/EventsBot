import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/auth_store.dart';
import '../../core/localization.dart';
import '../coordinator/coordinator_dashboard_screen.dart';
import '../event_manager/event_manager_screen.dart';
import '../events/events_screen.dart';
import '../my_events/my_events_screen.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  late int _currentIndex;
  int _eventsTapCount = 0;

  @override
  void initState() {
    super.initState();
    _currentIndex = AuthStore.isAdmin ? 1 : 0;
  }

  List<({Widget body, BottomNavigationBarItem item})> get _destinations {
    if (AuthStore.isAdmin) {
      return [
        (
          body: const CoordinatorDashboardScreen(),
          item: BottomNavigationBarItem(
            icon: const Icon(Icons.inbox_outlined),
            label: AppLocalizations.get('requests'),
          ),
        ),
        (
          body: const EventsScreen(),
          item: BottomNavigationBarItem(
            icon: const Icon(Icons.event_outlined),
            label: AppLocalizations.get('events'),
          ),
        ),
        (
          body: const EventManagerScreen(),
          item: BottomNavigationBarItem(
            icon: const Icon(Icons.insights_outlined),
            label: AppLocalizations.get('analytics'),
          ),
        ),
      ];
    }
    return [
      (
        body: const EventsScreen(),
        item: BottomNavigationBarItem(
          icon: const Icon(Icons.event_outlined),
          label: AppLocalizations.get('events'),
        ),
      ),
      (
        body: const MyEventsScreen(),
        item: BottomNavigationBarItem(
          icon: const Icon(Icons.assignment_outlined),
          label: AppLocalizations.get('myBookings'),
        ),
      ),
    ];
  }

  Widget _buildBody() {
    final destinations = _destinations;
    final index = _currentIndex.clamp(0, destinations.length - 1);
    return IndexedStack(
      index: index,
      children: destinations.map((d) => d.body).toList(),
    );
  }

  Future<void> _handleNavigationTap(int index) async {
    final eventsIndex = AuthStore.isAdmin ? 1 : 0;
    if (index != eventsIndex) {
      _eventsTapCount = 0;
      setState(() => _currentIndex = index);
      return;
    }

    _eventsTapCount += 1;
    if (_eventsTapCount >= 5) {
      _eventsTapCount = 0;
      await AuthStore.cycleTestRole();
    }
    if (!mounted) return;
    setState(() => _currentIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    final destinations = _destinations;
    final currentIndex = _currentIndex.clamp(0, destinations.length - 1);
    return Scaffold(
      body: _buildBody(),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: currentIndex,
        onTap: _handleNavigationTap,
        type: BottomNavigationBarType.fixed,
        selectedItemColor: AppColors.primary,
        unselectedItemColor: AppColors.grey,
        backgroundColor: AppColors.white,
        items: destinations.map((destination) => destination.item).toList(),
      ),
    );
  }
}
