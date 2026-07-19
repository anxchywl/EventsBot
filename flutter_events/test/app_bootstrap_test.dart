import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:app_ui/app_ui.dart';
import 'package:events_feature/app.dart';
import 'package:events_feature/core/api_client.dart';
import 'package:events_feature/core/auth_store.dart';
import 'package:events_feature/core/cache_store.dart';
import 'package:events_feature/core/dev_session.dart';
import 'package:events_feature/core/event_draft_store.dart';
import 'package:events_feature/core/exceptions.dart';
import 'package:events_feature/features/shell/app_shell.dart';
import 'package:events_feature/features/submit/submit_screen.dart';
import 'package:events_feature/models/event_model.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    resetEventsFeatureRuntimeForTesting();
    await AuthStore.init();
    await CacheStore.init();
  });

  test('development access cannot be enabled outside debug mode', () {
    expect(
      developmentAccessAllowed(isDebugMode: false, requested: true),
      isFalse,
    );
    expect(
      developmentAccessAllowed(isDebugMode: true, requested: false),
      isFalse,
    );
    expect(
      developmentAccessAllowed(isDebugMode: true, requested: true),
      isTrue,
    );
  });

  test('creator lifecycle actions only appear in valid states', () {
    EventModel event(String status) => EventModel(
      id: 1,
      publicToken: 'token',
      title: 'Title',
      description: 'Description',
      eventDate: '2099-05-01',
      eventTime: '18:00',
      eventEndTime: '20:00',
      location: 'Block C',
      category: 'Tech',
      organizerName: 'Club',
      status: status,
    );

    for (final status in [
      'pending',
      'approved',
      'needs_changes',
      'resubmitted',
    ]) {
      expect(event(status).canCreatorCancel, isTrue, reason: status);
      expect(event(status).canCreatorDelete, isFalse, reason: status);
    }
    for (final status in ['cancelled', 'rejected']) {
      expect(event(status).canCreatorCancel, isFalse, reason: status);
      expect(event(status).canCreatorDelete, isTrue, reason: status);
    }
    expect(event('archived').canCreatorCancel, isFalse);
    expect(event('archived').canCreatorDelete, isFalse);
  });

  testWidgets('standalone host requires a Jas Wallet session in production', (
    tester,
  ) async {
    await tester.pumpWidget(const EventsApp());

    expect(find.text('Session required'), findsOneWidget);
    expect(
      find.text('Open Events from Jas Wallet to continue.'),
      findsOneWidget,
    );
    expect(find.text('Retry development sign-in'), findsNothing);
  });

  testWidgets('development sign-in failures have an explicit retry state', (
    tester,
  ) async {
    await tester.pumpWidget(
      EventsApp(
        onStandaloneSignIn: () async {
          throw StateError('offline');
        },
      ),
    );

    await tester.tap(find.text('Retry development sign-in'));
    await tester.pumpAndSettle();

    expect(
      find.text('Could not start the development session.'),
      findsOneWidget,
    );
    expect(find.text('Retry development sign-in'), findsOneWidget);
  });

  testWidgets('shell navigation remains focusable with accessible labels', (
    tester,
  ) async {
    await _pumpShell(tester, size: const Size(360, 640));

    for (final label in ['Events', 'Requests', 'Analytics']) {
      final tooltip = find.byTooltip(label);
      expect(tooltip, findsOneWidget, reason: label);
      final control = find.descendant(
        of: tooltip,
        matching: find.byType(InkWell),
      );
      expect(control, findsOneWidget, reason: label);
      expect(tester.widget<InkWell>(control).canRequestFocus, isTrue);
    }
    final search = find.byWidgetPredicate(
      (widget) => widget is Tooltip && widget.message == 'Search',
      skipOffstage: false,
    );
    expect(search, findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (widget) => widget is Tooltip && widget.message == 'Sorting',
        skipOffstage: false,
      ),
      findsOneWidget,
    );
    final searchControl = find.descendant(
      of: search,
      matching: find.byType(InkWell, skipOffstage: false),
      skipOffstage: false,
    );
    expect(searchControl, findsOneWidget);
    expect(tester.getSize(searchControl).width, greaterThanOrEqualTo(48));
    expect(tester.getSize(searchControl).height, greaterThanOrEqualTo(48));
    await _disposeShell(tester);
  });

  testWidgets(
    'compact shell supports two-times text scaling without overflow',
    (tester) async {
      await _pumpShell(
        tester,
        size: const Size(320, 568),
        textScaler: const TextScaler.linear(2),
      );

      expect(tester.takeException(), isNull);
      expect(find.text('Events'), findsWidgets);
      expect(
        tester.getSize(find.byType(IndexedStack)).height,
        greaterThan(400),
      );
      await _disposeShell(tester);
    },
  );

  testWidgets('wide hosts keep feature content at a readable width', (
    tester,
  ) async {
    await _pumpShell(tester, size: const Size(1200, 800));

    expect(tester.getSize(find.byType(IndexedStack)).width, 840);
    expect(tester.takeException(), isNull);
    await _disposeShell(tester);
  });

  testWidgets('dirty event forms require an explicit discard decision', (
    tester,
  ) async {
    await _pumpSubmitRoute(tester);
    final locationField = find.byWidgetPredicate(
      (widget) => widget is AppTextField && widget.label == 'Place',
    );
    final location = find.descendant(
      of: locationField,
      matching: find.byType(TextFormField),
    );
    await tester.enterText(location, 'Main hall');
    tester.testTextInput.hide();
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump();

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();

    expect(find.text('Unsaved changes'), findsOneWidget);
    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    expect(find.byType(SubmitScreen), findsOneWidget);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discard'));
    await tester.pumpAndSettle();
    expect(find.byType(SubmitScreen), findsNothing);
    expect(find.text('Host'), findsOneWidget);
  });

  testWidgets('prefilled event values are not treated as unsaved changes', (
    tester,
  ) async {
    final event = EventModel(
      id: 42,
      publicToken: 'token',
      title: 'Orientation',
      description: 'Welcome session',
      eventDate: '2099-09-10',
      eventTime: '10:00',
      eventEndTime: '11:00',
      location: 'Main hall',
      category: 'Community',
      organizerName: 'Student Life',
      status: 'needs_changes',
    );
    await _pumpSubmitRoute(tester, initialEvent: event);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();

    expect(find.text('Unsaved changes'), findsNothing);
    expect(find.byType(SubmitScreen), findsNothing);
    expect(find.text('Host'), findsOneWidget);
  });

  testWidgets('dirty event sheets block barrier dismissal', (tester) async {
    await _pumpSubmitRoute(tester, asSheet: true);
    final locationField = find.byWidgetPredicate(
      (widget) => widget is AppTextField && widget.label == 'Place',
    );
    await tester.enterText(
      find.descendant(of: locationField, matching: find.byType(TextFormField)),
      'Main hall',
    );
    tester.testTextInput.hide();
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump();

    await tester.tapAt(const Offset(8, 8));
    await tester.pumpAndSettle();

    expect(find.text('Unsaved changes'), findsOneWidget);
    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    expect(find.byType(SubmitScreen), findsOneWidget);
  });

  testWidgets('unfinished create drafts can be restored after a refresh', (
    tester,
  ) async {
    await AuthStore.save(token: 'user-token', role: 'user', userId: 7);
    await EventDraftStore.save(
      EventDraft(
        userId: 7,
        clientRequestId: 'persisted-request-id',
        updatedAt: DateTime.now(),
        currentStep: 0,
        title: '',
        description: '',
        organizer: '',
        location: 'Main hall',
        registrationUrl: '',
        itEquipment: '',
        materials: '',
      ),
    );

    await _pumpSubmitRoute(tester);
    expect(find.text('Restore draft?'), findsOneWidget);
    await tester.tap(find.text('Restore'));
    await tester.pumpAndSettle();

    final locationField = find.byWidgetPredicate(
      (widget) => widget is AppTextField && widget.label == 'Place',
    );
    final locationInput = find.descendant(
      of: locationField,
      matching: find.byType(TextFormField),
    );
    expect(
      tester.widget<TextFormField>(locationInput).controller?.text,
      'Main hall',
    );
    await tester.pumpWidget(const SizedBox.shrink());
    await AuthStore.clear();
    await tester.pump();
  });

  testWidgets('create forms persist changes before process replacement', (
    tester,
  ) async {
    await AuthStore.save(token: 'user-token', role: 'user', userId: 7);
    await _pumpSubmitRoute(tester);
    final locationField = find.byWidgetPredicate(
      (widget) => widget is AppTextField && widget.label == 'Place',
    );
    await tester.enterText(
      find.descendant(of: locationField, matching: find.byType(TextFormField)),
      'Main hall',
    );
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();

    final draft = await EventDraftStore.load(7);
    expect(draft?.location, 'Main hall');
    expect(draft?.clientRequestId, isNotEmpty);
    await AuthStore.clear();
    await tester.pump();
  });

  testWidgets('host session resolves its authoritative role before mounting', (
    tester,
  ) async {
    setApiClientForTesting(
      MockClient((request) async {
        expect(request.headers['authorization'], 'Bearer jas-wallet-token');
        if (request.url.path == '/api/flutter/auth/session') {
          return http.Response(
            jsonEncode({
              'user_id': 17,
              'role': 'admin',
              'first_name': 'Aruzhan',
              'is_verified': true,
            }),
            200,
          );
        }
        return http.Response('[]', 200);
      }),
    );

    await tester.pumpWidget(
      const MaterialApp(
        home: EventsFeature(
          session: EventsHostSession(accessToken: 'jas-wallet-token'),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(AuthStore.token, 'jas-wallet-token');
    expect(AuthStore.userId, 17);
    expect(AuthStore.role, 'admin');
    expect(
      (await SharedPreferences.getInstance()).getString('auth_token'),
      isNull,
    );
    expect(find.text('Session required'), findsNothing);

    await tester.pumpWidget(const SizedBox());
    await AuthStore.clear();
  });

  testWidgets('expired host session is reported once without a retry loop', (
    tester,
  ) async {
    var expiryCalls = 0;
    setApiClientForTesting(
      MockClient(
        (_) async =>
            http.Response(jsonEncode({'detail': 'Invalid session'}), 401),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: EventsFeature(
          session: const EventsHostSession(accessToken: 'expired-token'),
          onSessionExpired: () => expiryCalls++,
        ),
      ),
    );
    await tester.pump();
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(
      find.text(
        'Your Jas Wallet session has expired. Reopen Events to continue.',
      ),
      findsOneWidget,
    );
    expect(expiryCalls, 1);
    await tester.pump(const Duration(seconds: 1));
    expect(expiryCalls, 1);
  });

  testWidgets('blank host sessions are rejected without an API request', (
    tester,
  ) async {
    var requests = 0;
    var expiryCalls = 0;
    setApiClientForTesting(
      MockClient((_) async {
        requests++;
        return http.Response('{}', 200);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: EventsFeature(
          session: const EventsHostSession(accessToken: '   '),
          onSessionExpired: () => expiryCalls++,
        ),
      ),
    );
    await tester.pump();

    expect(requests, 0);
    expect(expiryCalls, 1);
    expect(
      find.text(
        'Your Jas Wallet session has expired. Reopen Events to continue.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('blank replacement invalidates an in-flight host bootstrap', (
    tester,
  ) async {
    final requestStarted = Completer<void>();
    final releaseResponse = Completer<void>();
    setApiClientForTesting(
      MockClient((_) async {
        requestStarted.complete();
        await releaseResponse.future;
        return http.Response(
          jsonEncode({
            'user_id': 17,
            'role': 'admin',
            'first_name': 'Aruzhan',
            'is_verified': true,
          }),
          200,
        );
      }),
    );

    await tester.pumpWidget(
      const MaterialApp(
        home: EventsFeature(
          session: EventsHostSession(accessToken: 'old-host-token'),
        ),
      ),
    );
    await requestStarted.future;
    await tester.pumpWidget(
      const MaterialApp(
        home: EventsFeature(session: EventsHostSession(accessToken: '   ')),
      ),
    );
    releaseResponse.complete();
    await tester.pumpAndSettle();

    expect(AuthStore.token, isNull);
    expect(
      find.text(
        'Your Jas Wallet session has expired. Reopen Events to continue.',
      ),
      findsOneWidget,
    );
  });

  test('a late 401 cannot clear a replacement session', () async {
    final requestStarted = Completer<void>();
    final releaseResponse = Completer<void>();
    setApiClientForTesting(
      MockClient((_) async {
        requestStarted.complete();
        await releaseResponse.future;
        return http.Response(jsonEncode({'detail': 'Expired'}), 401);
      }),
    );
    await AuthStore.save(token: 'old-token', role: 'user', userId: 1);

    final oldRequest = fetchCategories();
    await requestStarted.future;
    await AuthStore.save(token: 'replacement-token', role: 'user', userId: 1);
    releaseResponse.complete();

    await expectLater(oldRequest, throwsA(isA<UnauthorizedException>()));
    expect(AuthStore.token, 'replacement-token');
    expect(AuthStore.isLoggedIn, isTrue);
  });

  test('network failures use a retryable user-facing exception', () async {
    setApiClientForTesting(
      MockClient((_) async => throw const SocketException('offline')),
    );

    await expectLater(
      bootstrapSession('host-token'),
      throwsA(
        isA<NetworkException>().having(
          (error) => error.message,
          'message',
          'No connection. Check your network and try again.',
        ),
      ),
    );
  });

  test('nested rate-limit errors preserve the server message', () async {
    setApiClientForTesting(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'detail': {
              'detail': 'Too many attempts. Try again later.',
              'retry_after': 60,
            },
          }),
          429,
        ),
      ),
    );

    await expectLater(
      login('membertest@example.edu', 'password'),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'Too many attempts. Try again later.',
        ),
      ),
    );
  });

  test('development session replaces an expired cached token', () async {
    final prefs = await SharedPreferences.getInstance();
    await AuthStore.save(token: 'expired-dev-token', role: 'user', userId: 1);
    await prefs.setString(
      'dev_session_user',
      jsonEncode({
        'token': 'expired-dev-token',
        'role': 'user',
        'first_name': 'Member',
        'user_id': 1,
        'is_verified': true,
      }),
    );
    setApiClientForTesting(
      MockClient((request) async {
        if (request.url.path == '/api/flutter/auth/session') {
          return http.Response(jsonEncode({'detail': 'Expired'}), 401);
        }
        expect(request.url.path, '/api/flutter/auth/login');
        return http.Response(
          jsonEncode({
            'token': 'fresh-dev-token',
            'role': 'user',
            'first_name': 'Member',
            'user_id': 1,
            'is_verified': true,
          }),
          200,
        );
      }),
    );

    await ensureDevSession();

    expect(AuthStore.token, 'fresh-dev-token');
    expect(prefs.getString('dev_session_user'), contains('fresh-dev-token'));
  });

  test('development session keeps cached access while offline', () async {
    await AuthStore.save(token: 'offline-token', role: 'user', userId: 1);
    setApiClientForTesting(
      MockClient((_) async => throw const SocketException('offline')),
    );

    await ensureDevSession();

    expect(AuthStore.token, 'offline-token');
    expect(AuthStore.isLoggedIn, isTrue);
  });
}

Future<void> _pumpShell(
  WidgetTester tester, {
  required Size size,
  TextScaler textScaler = TextScaler.noScaling,
}) async {
  setApiClientForTesting(
    MockClient((request) async {
      if (request.url.path == '/api/flutter/events/categories' ||
          request.url.path == '/api/flutter/events' ||
          request.url.path == '/api/flutter/events/my' ||
          request.url.path == '/api/flutter/events/pending') {
        return http.Response('[]', 200);
      }
      return http.Response(
        jsonEncode({'detail': 'Unavailable in widget test'}),
        503,
      );
    }),
  );
  await AuthStore.save(token: 'admin-token', role: 'admin', userId: 7);
  await tester.binding.setSurfaceSize(size);
  addTearDown(() async {
    await tester.binding.setSurfaceSize(null);
    await AuthStore.clear();
  });

  await tester.pumpWidget(
    MaterialApp(
      home: MediaQuery(
        data: MediaQueryData(size: size, textScaler: textScaler),
        child: const AppShell(),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

Future<void> _disposeShell(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await AuthStore.clear();
  await tester.pump();
}

Future<void> _pumpSubmitRoute(
  WidgetTester tester, {
  EventModel? initialEvent,
  bool asSheet = false,
}) async {
  await CacheStore.clearAll();
  setApiClientForTesting(
    MockClient((request) async {
      if (request.url.path == '/api/flutter/events/categories') {
        return http.Response(
          jsonEncode([
            {'id': 1, 'name': 'Community', 'slug': 'community'},
          ]),
          200,
        );
      }
      if (request.url.path == '/api/flutter/events') {
        return http.Response('[]', 200);
      }
      return http.Response(jsonEncode({'detail': 'Not found'}), 404);
    }),
  );

  await tester.pumpWidget(
    MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () {
              if (asSheet) {
                unawaited(
                  showModalBottomSheet<void>(
                    context: context,
                    isScrollControlled: true,
                    builder: (_) =>
                        SubmitScreen(initialEvent: initialEvent, asSheet: true),
                  ),
                );
                return;
              }
              unawaited(
                Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) => SubmitScreen(initialEvent: initialEvent),
                  ),
                ),
              );
            },
            child: const Text('Host'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Host'));
  await tester.pumpAndSettle();
  expect(find.byType(SubmitScreen), findsOneWidget);
}
