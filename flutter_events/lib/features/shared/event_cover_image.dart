import 'package:app_ui/app_ui.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

/// Cover image with on-disk caching, shared by the list card and the detail
/// screen so both cache identically.
///
/// The [url] carries the backend `?v=<poster_file_id>` version. Because
/// [CachedNetworkImage] keys its persistent disk cache by the full URL, an
/// unchanged cover is served straight from disk across a full app restart (no
/// re-download and it renders offline), while a cover replaced by an organiser
/// or admin arrives under a new URL — a cache miss that fetches the new image
/// exactly once. A removed cover yields a null [url] and the muted fallback.
class EventCoverImage extends StatelessWidget {
  const EventCoverImage({
    super.key,
    required this.url,
    this.fit = BoxFit.cover,
  });

  final String? url;
  final BoxFit fit;

  @override
  Widget build(BuildContext context) {
    final coverUrl = url;
    if (coverUrl == null) return const _MutedCover();
    return CachedNetworkImage(
      imageUrl: coverUrl,
      fit: fit,
      fadeInDuration: const Duration(milliseconds: 120),
      placeholder: (_, _) => const _MutedCover(),
      errorWidget: (_, _, _) => const _MutedCover(),
    );
  }
}

class _MutedCover extends StatelessWidget {
  const _MutedCover();

  @override
  Widget build(BuildContext context) =>
      const ColoredBox(color: AppColors.fieldBackground);
}
