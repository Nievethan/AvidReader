/// One illustrated key moment from `GET /books/{id}/scenes`.
class SceneItem {
  final String id;
  final String title;
  final String caption;
  final String sourceLocation; // e.g. "page 12" or "chapter 3"
  final int position;
  // "pending" | "ready" | "failed"
  final String status;
  // Relative to the API base URL, e.g. /api/v1/books/{id}/scenes/{sid}/image?v=...
  final String? imageUrl;

  const SceneItem({
    required this.id,
    required this.title,
    required this.caption,
    required this.sourceLocation,
    required this.position,
    required this.status,
    this.imageUrl,
  });

  bool get hasImage => status == 'ready' && imageUrl != null;
  bool get isPending => status == 'pending';

  factory SceneItem.fromJson(Map<String, dynamic> json) => SceneItem(
        id: json['id'] as String,
        title: (json['title'] as String?) ?? '',
        caption: (json['caption'] as String?) ?? '',
        sourceLocation: (json['source_location'] as String?) ?? '',
        position: (json['position'] as int?) ?? 0,
        status: (json['status'] as String?) ?? 'pending',
        imageUrl: json['image_url'] as String?,
      );
}

class ScenesResult {
  final String status; // "ready" | "not_available"
  final String? message;
  final List<SceneItem> scenes;

  const ScenesResult({
    required this.status,
    this.message,
    this.scenes = const [],
  });

  factory ScenesResult.fromJson(Map<String, dynamic> json) => ScenesResult(
        status: (json['status'] as String?) ?? 'not_available',
        message: json['message'] as String?,
        scenes: ((json['scenes'] as List?) ?? const [])
            .cast<Map<String, dynamic>>()
            .map(SceneItem.fromJson)
            .toList(),
      );
}

/// Answer to one Illustrate tap (`POST /books/{id}/scenes/at/{position}`).
class SceneResult {
  // "ready" | "failed" (painting failed, try again) | "not_available" (see message)
  final String status;
  final String? message;
  final SceneItem? scene;

  const SceneResult({required this.status, this.message, this.scene});

  factory SceneResult.fromJson(Map<String, dynamic> json) => SceneResult(
        status: (json['status'] as String?) ?? 'not_available',
        message: json['message'] as String?,
        scene: json['scene'] == null
            ? null
            : SceneItem.fromJson((json['scene'] as Map).cast<String, dynamic>()),
      );
}
