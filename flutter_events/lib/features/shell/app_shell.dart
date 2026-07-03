import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/auth_store.dart';
import '../auth/login_screen.dart';
import '../events/events_screen.dart';
import '../my_events/my_events_screen.dart';
import '../stub/stub_screen.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _currentIndex = 2;

  Future<void> _logout() async {
    await AuthStore.clear();
    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }

  Widget _buildBody() {
    switch (_currentIndex) {
      case 0:
        return const StubScreen('Главная');
      case 1:
        return const StubScreen('Сообщества');
      case 2:
        return const EventsScreen();
      case 3:
        return const MyEventsScreen();
      default:
        return _buildProfile();
    }
  }

  Widget _buildProfile() {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: const AppAppBar(title: 'Профиль'),
      body: Center(
        child: Padding(
          padding: AppSpacing.screenPadding,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                AuthStore.firstName ?? 'Профиль',
                style: theme.textTheme.titleLarge,
              ),
              const SizedBox(height: AppSpacing.xl),
              AppSecondaryButton(text: 'Выйти', onPressed: _logout),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _buildBody(),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) => setState(() => _currentIndex = index),
        type: BottomNavigationBarType.fixed,
        selectedItemColor: AppColors.primary,
        unselectedItemColor: AppColors.grey,
        backgroundColor: AppColors.white,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home_outlined),
            label: 'Главная',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.groups_outlined),
            label: 'Сообщества',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.event_outlined),
            label: 'Ивенты',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.assignment_outlined),
            label: 'Мои заявки',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.person_outline),
            label: 'Профиль',
          ),
        ],
      ),
    );
  }
}
