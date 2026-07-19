import 'package:events_feature/app.dart';
import 'package:events_feature/core/auth_store.dart';
import 'package:events_feature/core/cache_store.dart';
import 'package:events_feature/core/dev_session.dart';
import 'package:events_feature/models/event_model.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
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
}
