import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

/// Placeholder screen for tabs that are not part of the events feature.
class StubScreen extends StatelessWidget {
  const StubScreen(this.label, {super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppAppBar(title: label),
      body: Center(
        child: Text(
          'Скоро появится',
          style: theme.textTheme.bodyLarge?.copyWith(color: AppColors.grey),
        ),
      ),
    );
  }
}
