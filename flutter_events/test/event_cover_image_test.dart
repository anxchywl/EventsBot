import 'package:cached_network_image/cached_network_image.dart';
import 'package:events_feature/features/shared/event_cover_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('EventCoverImage', () {
    testWidgets('renders the muted fallback when there is no cover', (
      tester,
    ) async {
      await tester.pumpWidget(
        const Directionality(
          textDirection: TextDirection.ltr,
          child: EventCoverImage(url: null),
        ),
      );

      // no network image is built for a removed cover
      expect(find.byType(CachedNetworkImage), findsNothing);
      expect(find.byType(ColoredBox), findsOneWidget);
    });

    testWidgets('uses the disk-cached network image when a cover url exists', (
      tester,
    ) async {
      await tester.pumpWidget(
        const Directionality(
          textDirection: TextDirection.ltr,
          child: EventCoverImage(
            url: 'https://host/api/events/tok/cover?v=fid-1',
          ),
        ),
      );

      final widget = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      // the versioned URL is what keys the on-disk cache: unchanged -> disk hit,
      // replaced -> new key -> one re-download
      expect(widget.imageUrl, 'https://host/api/events/tok/cover?v=fid-1');
    });
  });
}
