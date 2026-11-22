import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';
import '../theme/classic_lit_theme.dart';
import 'paper_card.dart';

/// "Scenes" tab of the Visualize screen: every page/chapter the reader has
/// illustrated (with the reader's Illustrate button), in reading order.
/// Scenes beyond the reader's position are never sent by the backend.
///
/// The parent refreshes it through a `GlobalKey<SceneGalleryState>`
/// (`key.currentState?.reload()`), so the header's Update button works here.
class SceneGallery extends StatefulWidget {
  final String bookId;

  const SceneGallery({super.key, required this.bookId});

  @override
  State<SceneGallery> createState() => SceneGalleryState();
}

class SceneGalleryState extends State<SceneGallery> {
  bool _loading = true;
  String? _error;
  ScenesResult? _result;

  @override
  void initState() {
    super.initState();
    reload();
  }

  @override
  void didUpdateWidget(covariant SceneGallery oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.bookId != widget.bookId) reload();
  }

  Future<void> reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final bookId = widget.bookId;
    try {
      final res = await api.getScenes(bookId);
      if (!mounted || widget.bookId != bookId) return;
      setState(() {
        _result = res;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(32),
        child: Center(
          child: CircularProgressIndicator(color: ClassicLitTheme.oxbloodPrimary),
        ),
      );
    }
    if (_error != null) {
      return _message(Icons.error_outline, _error!, onRetry: reload);
    }

    final scenes = _result?.scenes ?? const <SceneItem>[];
    if (scenes.isEmpty) {
      return _message(
        Icons.photo_library_outlined,
        _result?.message ?? 'No scenes yet.',
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('THE STORY SO FAR', style: Theme.of(context).textTheme.labelSmall),
        const SizedBox(height: 8),
        for (final scene in scenes) ...[
          SceneCard(scene: scene),
          const SizedBox(height: 12),
        ],
      ],
    );
  }

  Widget _message(IconData icon, String text, {VoidCallback? onRetry}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 12),
      child: Column(
        children: [
          Icon(icon, size: 44, color: ClassicLitTheme.inkSecondary),
          const SizedBox(height: 10),
          Text(text, textAlign: TextAlign.center),
          if (onRetry != null) ...[
            const SizedBox(height: 12),
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ],
      ),
    );
  }
}

/// One illustrated scene: picture, title and where it is. The caption isn't
/// shown (it repeats the title) but is read out by screen readers as the
/// picture's description.
/// Used by the gallery and by the reader's Illustrate dialog.
class SceneCard extends StatelessWidget {
  final SceneItem scene;

  const SceneCard({super.key, required this.scene});

  @override
  Widget build(BuildContext context) {
    return PaperCard(
      backgroundColor: ClassicLitTheme.elevatedPaper,
      padding: const EdgeInsets.all(10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: AspectRatio(aspectRatio: 1, child: _image()),
          ),
          const SizedBox(height: 8),
          Text(
            scene.title,
            style: const TextStyle(
              fontFamily: ClassicLitTheme.serifFont,
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: ClassicLitTheme.inkPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            scene.sourceLocation,
            style: const TextStyle(fontSize: 11, color: ClassicLitTheme.inkSecondary),
          ),
        ],
      ),
    );
  }

  Widget _image() {
    if (scene.hasImage) {
      return Image.network(
        api.absoluteUrl(scene.imageUrl!),
        fit: BoxFit.cover,
        gaplessPlayback: true,
        semanticLabel: scene.caption.isNotEmpty ? scene.caption : scene.title,
        errorBuilder: (_, _, _) =>
            _placeholder(Icons.broken_image_outlined, 'Picture unavailable'),
      );
    }
    if (scene.isPending) {
      return _placeholder(Icons.brush_outlined, 'Painting…');
    }
    return _placeholder(
        Icons.image_not_supported_outlined, 'Tap Illustrate on this page to try again');
  }

  Widget _placeholder(IconData icon, String label) {
    return Container(
      color: ClassicLitTheme.linenCard,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 36, color: ClassicLitTheme.inkSecondary),
          const SizedBox(height: 6),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12, color: ClassicLitTheme.inkSecondary),
          ),
        ],
      ),
    );
  }
}
