import 'dart:ui' show lerpDouble;

import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/auth_store.dart';
import '../../core/cache_store.dart';
import '../../core/localization.dart';
import '../coordinator/coordinator_dashboard_screen.dart';
import '../event_manager/event_manager_screen.dart';
import '../events/events_screen.dart';
import '../my_events/my_events_screen.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key, this.onDevelopmentRoleSwitch});

  final Future<void> Function()? onDevelopmentRoleSwitch;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  late int _currentIndex;
  int _eventsTapCount = 0;

  @override
  void initState() {
    super.initState();
    _currentIndex = 0;
    // Single, app-wide realtime subscription. The cache patches the shared event
    // map on each event_status_changed and notifies every screen — screens no
    // longer each open their own SSE listener and refetch independently.
    EventCache.instance.attachRealtime();
  }

  List<({Widget body, AppIconData icon, String label})> get _destinations {
    if (AuthStore.isAdmin) {
      return [
        (
          body: const EventsScreen(),
          icon: AppIcons.event,
          label: AppLocalizations.get('events'),
        ),
        (
          body: const CoordinatorDashboardScreen(),
          icon: AppIcons.request,
          label: AppLocalizations.get('requests'),
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
        icon: AppIcons.request,
        label: AppLocalizations.get('myRequests'),
      ),
    ];
  }

  Widget _buildBody() {
    final destinations = _destinations;
    final index = _currentIndex.clamp(0, destinations.length - 1);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 840),
        child: SizedBox.expand(
          child: IndexedStack(
            index: index,
            children: destinations
                .map((destination) => destination.body)
                .toList(),
          ),
        ),
      ),
    );
  }

  void _setCurrentIndex(int index) {
    setState(() => _currentIndex = index);
  }

  Future<void> _handleNavigationTap(int index) async {
    const eventsIndex = 0;
    if (index == _currentIndex && index != eventsIndex) return;

    if (index != eventsIndex) {
      _eventsTapCount = 0;
      _setCurrentIndex(index);
      return;
    }

    final switchRole = widget.onDevelopmentRoleSwitch;
    if (switchRole == null) {
      _setCurrentIndex(index);
      return;
    }

    // Role switcher: 5 taps on the Events tab swaps between the user and admin
    // test accounts so both shells can be exercised without a login screen.
    _eventsTapCount += 1;
    if (_eventsTapCount >= 5) {
      _eventsTapCount = 0;
      try {
        await switchRole();
      } catch (_) {
        // ignore network errors; keep the current role
      }
      if (!mounted) return;
      setState(() => _currentIndex = 0);
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(
          content: Text('Switched to ${AuthStore.isAdmin ? 'admin' : 'user'}'),
          duration: const Duration(seconds: 1),
        ),
      );
      return;
    }
    if (!mounted) return;
    _setCurrentIndex(index);
  }

  @override
  Widget build(BuildContext context) {
    final destinations = _destinations;
    final currentIndex = _currentIndex.clamp(0, destinations.length - 1);
    final isLight = Theme.of(context).brightness == Brightness.light;
    return Scaffold(
      resizeToAvoidBottomInset: false,
      extendBody: false,
      body: _buildBody(),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: isLight ? AppColors.surface : AppColors.surfaceDark,
          border: Border(
            top: BorderSide(
              color: isLight ? AppColors.borderGrey : AppColors.borderDark,
            ),
          ),
          boxShadow: HomeShadows.navBar,
        ),
        padding: EdgeInsets.only(
          left: AppSpacing.sm,
          right: AppSpacing.sm,
          top: AppSpacing.xs,
          bottom: MediaQuery.paddingOf(context).bottom + AppSpacing.xs,
        ),
        child: Align(
          alignment: Alignment.bottomCenter,
          heightFactor: 1,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 840),
            child: Row(
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
    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        label: label,
        selected: selected,
        button: true,
        excludeSemantics: true,
        child: InkWell(
          borderRadius: AppSpacing.borderRadiusMd,
          canRequestFocus: true,
          onTap: onTap,
          child: TweenAnimationBuilder<double>(
            tween: Tween<double>(begin: 0, end: selected ? 1 : 0),
            duration: const Duration(milliseconds: 240),
            curve: Curves.easeOutCubic,
            builder: (context, progress, child) {
              final color = Color.lerp(
                AppColors.iconSecondary,
                AppColors.primary,
                progress,
              )!;
              final background = Color.lerp(
                AppColors.transparent,
                AppColors.primaryLight,
                progress,
              )!;
              final horizontalPadding = lerpDouble(
                AppSpacing.xs,
                AppSpacing.sm,
                progress,
              )!;

              return Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                      vertical: AppSpacing.xs,
                    ),
                    decoration: BoxDecoration(
                      color: background,
                      borderRadius: AppSpacing.borderRadiusMd,
                    ),
                    child: AppIcon(icon, size: AppSpacing.iconDf, color: color),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTextStyles.labelSmall.copyWith(
                      color: color,
                      fontWeight: progress > 0.5
                          ? FontWeight.w600
                          : FontWeight.w500,
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}
