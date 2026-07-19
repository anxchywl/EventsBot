import 'package:events_feature/core/event_draft_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('drafts round-trip only for their owning account', () async {
    final updatedAt = DateTime.utc(2026, 7, 19, 10);
    await EventDraftStore.save(
      EventDraft(
        userId: 7,
        clientRequestId: 'request-id',
        updatedAt: updatedAt,
        currentStep: 1,
        title: 'Community meetup',
        description: 'Bring everyone together',
        organizer: 'Student Life',
        location: 'Main hall',
        registrationUrl: 'https://example.com/register',
        itEquipment: 'Projector',
        materials: 'Badges',
        eventDate: '2026-07-25',
        startTime: '18:00',
        endTime: '19:00',
        categoryId: 4,
        categoryName: 'Community',
      ),
    );

    expect(await EventDraftStore.load(8, now: updatedAt), isNull);
    final restored = await EventDraftStore.load(7, now: updatedAt);
    expect(restored?.title, 'Community meetup');
    expect(restored?.clientRequestId, 'request-id');
    expect(restored?.currentStep, 1);
    expect(restored?.categoryId, 4);
  });

  test('expired drafts are removed', () async {
    final updatedAt = DateTime.utc(2026, 7, 1);
    await EventDraftStore.save(
      EventDraft(
        userId: 7,
        clientRequestId: 'request-id',
        updatedAt: updatedAt,
        currentStep: 0,
        title: 'Old draft',
        description: '',
        organizer: '',
        location: '',
        registrationUrl: '',
        itEquipment: '',
        materials: '',
      ),
    );

    expect(
      await EventDraftStore.load(
        7,
        now: updatedAt.add(EventDraftStore.retention + const Duration(days: 1)),
      ),
      isNull,
    );
    expect(await EventDraftStore.load(7, now: updatedAt), isNull);
  });
}
