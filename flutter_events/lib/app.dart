import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import 'core/auth_store.dart';
import 'features/shell/app_shell.dart';

class EventsApp extends StatelessWidget {
  const EventsApp({
    super.key,
    this.onStandaloneSignIn,
    this.onDevelopmentRoleSwitch,
  });

  final Future<void> Function()? onStandaloneSignIn;
  final Future<void> Function()? onDevelopmentRoleSwitch;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.light,
      debugShowCheckedModeBanner: false,
      home: _StandaloneSessionGate(
        onStandaloneSignIn: onStandaloneSignIn,
        onDevelopmentRoleSwitch: onDevelopmentRoleSwitch,
      ),
    );
  }
}

class EventsFeature extends StatelessWidget {
  const EventsFeature({super.key, this.onDevelopmentRoleSwitch});

  final Future<void> Function()? onDevelopmentRoleSwitch;

  @override
  Widget build(BuildContext context) {
    return AppShell(onDevelopmentRoleSwitch: onDevelopmentRoleSwitch);
  }
}

class _StandaloneSessionGate extends StatefulWidget {
  const _StandaloneSessionGate({
    required this.onStandaloneSignIn,
    required this.onDevelopmentRoleSwitch,
  });

  final Future<void> Function()? onStandaloneSignIn;
  final Future<void> Function()? onDevelopmentRoleSwitch;

  @override
  State<_StandaloneSessionGate> createState() => _StandaloneSessionGateState();
}

class _StandaloneSessionGateState extends State<_StandaloneSessionGate> {
  bool _signingIn = false;
  String? _error;

  Future<void> _signIn() async {
    final signIn = widget.onStandaloneSignIn;
    if (signIn == null || _signingIn) return;
    setState(() {
      _signingIn = true;
      _error = null;
    });
    try {
      await signIn();
      if (!AuthStore.isLoggedIn) {
        throw StateError('Development account sign-in failed');
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Could not start the development session.');
      }
    } finally {
      if (mounted) setState(() => _signingIn = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<int>(
      valueListenable: AuthStore.sessionChanges,
      builder: (context, _, _) {
        if (AuthStore.isLoggedIn) {
          return EventsFeature(
            onDevelopmentRoleSwitch: widget.onDevelopmentRoleSwitch,
          );
        }
        return _SessionRequiredScreen(
          canUseDevelopmentAccess: widget.onStandaloneSignIn != null,
          isLoading: _signingIn,
          error: _error,
          onRetry: _signIn,
        );
      },
    );
  }
}

class _SessionRequiredScreen extends StatelessWidget {
  const _SessionRequiredScreen({
    required this.canUseDevelopmentAccess,
    required this.isLoading,
    required this.error,
    required this.onRetry,
  });

  final bool canUseDevelopmentAccess;
  final bool isLoading;
  final String? error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final message = canUseDevelopmentAccess
        ? 'The development account is not available right now.'
        : 'Open Events from Jas Wallet to continue.';
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: AppSpacing.screenPadding,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const AppIcon(
                    AppIcons.event,
                    size: 48,
                    color: AppColors.primary,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  Text(
                    'Session required',
                    textAlign: TextAlign.center,
                    style: AppTextStyles.titleLarge,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    error ?? message,
                    textAlign: TextAlign.center,
                    style: AppTextStyles.bodyMedium.copyWith(
                      color: error == null
                          ? AppColors.textSecondary
                          : AppColors.error,
                    ),
                  ),
                  if (canUseDevelopmentAccess) ...[
                    const SizedBox(height: AppSpacing.lg),
                    AppPrimaryButton(
                      size: AppButtonSize.medium,
                      text: 'Retry development sign-in',
                      isLoading: isLoading,
                      onPressed: isLoading ? null : onRetry,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
