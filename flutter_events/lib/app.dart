import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import 'features/shell/app_shell.dart';

class EventsApp extends StatelessWidget {
  const EventsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.light,
      debugShowCheckedModeBanner: false,
      home: const AppShell(),
    );
  }
}
