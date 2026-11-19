class CharacterNode {
  final String id;
  final String name;
  final String? role;
  final String? description;
  final String? firstSeenChunkId;
  final String? appearance;
  // "none" | "pending" | "ready" | "failed"
  final String portraitStatus;
  // Relative to the API base URL, e.g. /api/v1/books/{id}/characters/{cid}/portrait?v=...
  final String? portraitUrl;

  const CharacterNode({
    required this.id,
    required this.name,
    this.role,
    this.description,
    this.firstSeenChunkId,
    this.appearance,
    this.portraitStatus = 'none',
    this.portraitUrl,
  });

  bool get hasPortrait => portraitStatus == 'ready' && portraitUrl != null;
  bool get portraitPending => portraitStatus == 'pending';

  factory CharacterNode.fromJson(Map<String, dynamic> json) => CharacterNode(
        id: json['id'] as String,
        name: json['name'] as String,
        role: json['role'] as String?,
        description: json['description'] as String?,
        firstSeenChunkId: json['first_seen_chunk_id'] as String?,
        appearance: json['appearance'] as String?,
        portraitStatus: (json['portrait_status'] as String?) ?? 'none',
        portraitUrl: json['portrait_url'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'role': role,
        'description': description,
        'first_seen_chunk_id': firstSeenChunkId,
        'appearance': appearance,
        'portrait_status': portraitStatus,
        'portrait_url': portraitUrl,
      };
}

class CharacterEdge {
  final String id;
  final String source;
  final String target;
  final String? relationship;
  final String? label;
  final String? evidence;

  const CharacterEdge({
    required this.id,
    required this.source,
    required this.target,
    this.relationship,
    this.label,
    this.evidence,
  });

  factory CharacterEdge.fromJson(Map<String, dynamic> json) => CharacterEdge(
        id: json['id'] as String,
        source: json['source'] as String,
        target: json['target'] as String,
        relationship: json['relationship'] as String?,
        label: json['label'] as String?,
        evidence: json['evidence'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'source': source,
        'target': target,
        'relationship': relationship,
        'label': label,
        'evidence': evidence,
      };
}

class RelationshipsResult {
  final String bookId;
  final String status; // "ready" | "not_available"
  final String source; // "extracted" | "fixture" | "none"
  final String? message;
  final List<CharacterNode> nodes;
  final List<CharacterEdge> edges;
  final DateTime? generatedAt;
  final String? boundaryLabel;

  const RelationshipsResult({
    required this.bookId,
    required this.status,
    required this.source,
    this.message,
    required this.nodes,
    required this.edges,
    this.generatedAt,
    this.boundaryLabel,
  });

  bool get isReady => status == 'ready';

  factory RelationshipsResult.fromJson(Map<String, dynamic> json) =>
      RelationshipsResult(
        bookId: json['book_id'] as String,
        status: (json['status'] as String?) ?? 'not_available',
        source: (json['source'] as String?) ?? 'none',
        message: json['message'] as String?,
        nodes: (json['nodes'] as List? ?? [])
            .map((n) =>
                CharacterNode.fromJson((n as Map).cast<String, dynamic>()))
            .toList(),
        edges: (json['edges'] as List? ?? [])
            .map((e) =>
                CharacterEdge.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        generatedAt: json['generated_at'] != null
            ? DateTime.tryParse(json['generated_at'] as String)
            : null,
        boundaryLabel: json['boundary_label'] as String?,
      );
}
