import 'package:app_ui/app_ui.dart';
import 'package:flutter/foundation.dart';
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

  List<({Widget body, AppIconData icon, String label})> get _destinations {
    if (AuthStore.isAdmin) {
      return [
        (
          body: const CoordinatorDashboardScreen(),
          icon: AppIcons.request,
          label: AppLocalizations.get('requests'),
        ),
        (
          body: const EventsScreen(),
          icon: AppIcons.event,
          label: AppLocalizations.get('events'),
        ),
        (
          body: const EventManagerScreen(),
          icon: AppIcons.statistics,
          label: AppLocalizations.get('analytics'),
        ),
      ];
    }
    return [
      (
        body: const EventsScreen(),
        icon: AppIcons.event,
        label: AppLocalizations.get('events'),
      ),
      (
        body: const MyEventsScreen(),
        icon: AppIcons.assignment,
        label: AppLocalizations.get('myRequests'),
      ),
    ];
  }

  Widget _buildBody() {
    final destinations = _destinations;
    final index = _currentIndex.clamp(0, destinations.length - 1);
    return IndexedStack(
      index: index,
      children: destinations.map((destination) => destination.body).toList(),
    );
  }

  void _setCurrentIndex(int index) {
    setState(() => _currentIndex = index);
  }

  Future<void> _handleNavigationTap(int index) async {
    final eventsIndex = AuthStore.isAdmin ? 1 : 0;
    if (index == _currentIndex && index != eventsIndex) return;

    if (index != eventsIndex) {
      _eventsTapCount = 0;
      _setCurrentIndex(index);
      return;
    }

    // Debug-only role switcher: 5 taps on the Events tab flips admin↔user so
    // both shells can be exercised on a single account. Compiled out of release
    // builds so real users can't trip it.
    if (kDebugMode) {
      _eventsTapCount += 1;
      if (_eventsTapCount >= 5) {
        _eventsTapCount = 0;
        await AuthStore.cycleTestRole();
      }
    }
    if (!mounted) return;
    _setCurrentIndex(index);
  }

  @override
  Widget build(BuildContext context) {
    final destinations = _destinations;
    final currentIndex = _currentIndex.clamp(0, destinations.length - 1);
    return Scaffold(
      body: _buildBody(),
      bottomNavigationBar: SafeArea(
        top: false,
        minimum: const EdgeInsets.fromLTRB(
          AppSpacing.df,
          0,
          AppSpacing.df,
          AppSpacing.sm,
        ),
        child: Align(
          heightFactor: 1,
          alignment: Alignment.bottomCenter,
          child: Container(
            height: AppSpacing.xxxl + AppSpacing.sm,
            constraints: const BoxConstraints(maxWidth: 320),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: AppSpacing.borderRadiusXl,
              border: Border.all(color: AppColors.borderGrey),
              boxShadow: HomeShadows.navBar,
            ),
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.xs,
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                return Row(
                  children: [
                    for (var i = 0; i < destinations.length; i++)
                      Expanded(
                        child: _NavIconButton(
                          icon: destinations[i].icon,
                          label: destinations[i].label,
                          selected: i == currentIndex,
                          onTap: () => _handleNavigationTap(i),
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}

class _NavIconButton extends StatelessWidget {
  const _NavIconButton({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final AppIconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.primary : AppColors.iconSecondary;
    return Tooltip(
      message: label,
      child: Semantics(
        label: label,
        selected: selected,
        button: true,
        child: InkWell(
          onTap: onTap,
          borderRadius: AppSpacing.borderRadiusLg,
          child: Center(
            child: AnimatedScale(
              scale: selected ? 1.08 : 1,
              duration: const Duration(milliseconds: 160),
              curve: Curves.easeOutCubic,
              child: AppIcon(icon, size: AppSpacing.xl, color: color),
            ),
          ),
        ),
      ),
    );
  }
}
