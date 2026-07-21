import 'dart:async';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'core/auth_store.dart';
import 'core/cache_store.dart';
import 'core/exceptions.dart';
import 'features/shell/app_shell.dart';

Future<void>? _runtimeInitialization;

Future<void> initializeEventsFeature() {
  final existingInitialization = _runtimeInitialization;
  if (existingInitialization != null) return existingInitialization;

  late final Future<void> initialization;
  initialization = () async {
    try {
      await AuthStore.init();
      await CacheStore.init();
    } catch (_) {
      if (identical(_runtimeInitialization, initialization)) {
        _runtimeInitialization = null;
      }
      rethrow;
    }
  }();
  _runtimeInitialization = initialization;
  return initialization;
}

@visibleForTesting
void resetEventsFeatureRuntimeForTesting() {
  _runtimeInitialization = null;
}

class EventsHostSession {
  const EventsHostSession({required this.accessToken})
    : assert(accessToken != '');

  final String accessToken;
}

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

class EventsFeature extends StatefulWidget {
  const EventsFeature({
    super.key,
    required EventsHostSession session,
    this.onSessionExpired,
  }) : _session = session,
       onDevelopmentRoleSwitch = null;

  const EventsFeature.standalone({super.key, this.onDevelopmentRoleSwitch})
    : _session = null,
      onSessionExpired = null;

  final EventsHostSession? _session;
  final VoidCallback? onSessionExpired;
  final Future<void> Function()? onDevelopmentRoleSwitch;

  @override
  State<EventsFeature> createState() => _EventsFeatureState();
}

class _EventsFeatureState extends State<EventsFeature> {
  bool _loading = false;
  bool _ready = false;
  bool _expired = false;
  bool _expiryReported = false;
  String? _error;
  int _attempt = 0;

  @override
  void initState() {
    super.initState();
    AuthStore.sessionExpiryChanges.addListener(_onSessionExpired);
    if (widget._session == null) {
      _ready = AuthStore.isLoggedIn;
    } else {
      unawaited(_bootstrapHostSession());
    }
  }

  @override
  void didUpdateWidget(covariant EventsFeature oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget._session?.accessToken != widget._session?.accessToken) {
      _expiryReported = false;
      unawaited(_bootstrapHostSession());
    }
  }

  @override
  void dispose() {
    _attempt++;
    AuthStore.sessionExpiryChanges.removeListener(_onSessionExpired);
    super.dispose();
  }

  Future<void> _bootstrapHostSession() async {
    final session = widget._session;
    if (session == null) return;
    final attempt = ++_attempt;
    if (session.accessToken.trim().isEmpty) {
      _showExpired();
      return;
    }
    setState(() {
      _loading = true;
      _ready = false;
      _expired = false;
      _error = null;
    });

    try {
      await initializeEventsFeature();
      if (AuthStore.token != null && AuthStore.token != session.accessToken) {
        await AuthStore.clear();
      }
      final profile = await bootstrapSession(session.accessToken);
      if (!mounted || attempt != _attempt) return;
      await AuthStore.save(
        token: session.accessToken,
        role: profile.role,
        firstName: profile.firstName,
        userId: profile.userId,
        persist: false,
      );
      if (!mounted || attempt != _attempt) return;
      setState(() => _ready = true);
    } on UnauthorizedException {
      if (!mounted || attempt != _attempt) return;
      _showExpired();
    } on ForbiddenException catch (error) {
      if (!mounted || attempt != _attempt) return;
      setState(() => _error = error.message);
    } on ApiException catch (error) {
      if (!mounted || attempt != _attempt) return;
      setState(() => _error = error.message);
    } catch (_) {
      if (!mounted || attempt != _attempt) return;
      setState(() => _error = 'Could not start Events. Please try again.');
    } finally {
      if (mounted && attempt == _attempt) {
        setState(() => _loading = false);
      }
    }
  }

  void _onSessionExpired() {
    if (widget._session != null) _showExpired();
  }

  void _showExpired() {
    if (!mounted) return;
    setState(() {
      _expired = true;
      _ready = false;
      _loading = false;
      _error = null;
    });
    if (!_expiryReported) {
      _expiryReported = true;
      widget.onSessionExpired?.call();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_ready && AuthStore.isLoggedIn) {
      return ValueListenableBuilder<int>(
        valueListenable: AuthStore.sessionChanges,
        builder: (context, _, _) =>
            AppShell(onDevelopmentRoleSwitch: widget.onDevelopmentRoleSwitch),
      );
    }
    if (_loading) {
      return const _FeatureStartupScreen(isLoading: true);
    }
    if (_expired) {
      return const _FeatureStartupScreen(
        message:
            'Your Jas Wallet session has expired. Reopen Events to continue.',
      );
    }
    return _FeatureStartupScreen(
      message: _error ?? 'Events could not verify your Jas Wallet session.',
      actionText: 'Retry',
      onAction: _bootstrapHostSession,
    );
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
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
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
          return EventsFeature.standalone(
            onDevelopmentRoleSwitch: widget.onDevelopmentRoleSwitch,
          );
        }
        // Dev convenience: open the app shell without a backend session so the
        // UI can be built and iterated on while auth is unavailable. Debug-only
        // — release / Jas Wallet builds still require a real session below.
        if (kDebugMode) {
          return AppShell(
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

class _FeatureStartupScreen extends StatelessWidget {
  const _FeatureStartupScreen({
    this.message,
    this.actionText,
    this.onAction,
    this.isLoading = false,
  });

  final String? message;
  final String? actionText;
  final VoidCallback? onAction;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
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
                  if (isLoading)
                    const CircularProgressIndicator()
                  else ...[
                    Text(
                      'Session required',
                      textAlign: TextAlign.center,
                      style: AppTextStyles.titleLarge,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      message ?? 'Starting Events…',
                      textAlign: TextAlign.center,
                      style: AppTextStyles.bodyMedium.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                    if (actionText != null && onAction != null) ...[
                      const SizedBox(height: AppSpacing.lg),
                      AppPrimaryButton(
                        size: AppButtonSize.medium,
                        text: actionText!,
                        onPressed: onAction,
                      ),
                    ],
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
        : 'Authentication required. Open Events from Jas Wallet to continue.';
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
