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
  // Too little description to paint yet: shown as initials until the book
  // describes them (no AI cost).
  bool get portraitWaiting => portraitStatus == 'waiting';

  /// "Ser Waymar Royce" -> "WR", "Hodor" -> "H" (titles skipped).
  String get initials {
    // Mirrors ALL_TITLES in backend/app/integrations/character_looks.py
    // (checked by test_flutter_initials_titles_match_the_shared_list).
    const titles = {
      'a', 'abbess', 'abbot', 'admiral', 'agent', 'ambassador', 'an', 'aunt',
      'auntie', 'baron', 'baroness', 'big', 'bishop', 'brother', 'capt',
      'captain', 'cardinal', 'chancellor', 'chief', 'colonel', 'commander',
      'constable', 'corporal', 'count', 'countess', 'dame', 'daughter',
      'deacon', 'detective', 'doctor', 'dr', 'duchess', 'duke', 'earl',
      'elder', 'emperor', 'empress', 'father', 'frau', 'fraulein', 'friar',
      'general', 'governor', 'grandfather', 'grandma', 'grandmother',
      'grandpa', 'granny', 'headmaster', 'headmistress', 'herr', 'husband',
      'imam', 'inspector', 'judge', 'justice', 'khal', 'khaleesi', 'king',
      'knight', 'lady', 'lieutenant', 'little', 'lord', 'lt', 'madam',
      'madame', 'mademoiselle', 'maester', 'magister', 'maid', 'major',
      'marchioness', 'marquess', 'marquis', 'master', 'mayor', 'minister',
      'miss', 'mister', 'mistress', 'mlle', 'mme', 'monk', 'monsieur',
      'mother', 'mr', 'mrs', 'ms', 'nana', 'nun', 'nurse', 'of', 'officer',
      'old', 'pastor', 'pope', 'president', 'priest', 'priestess', 'prince',
      'princess', 'private', 'prof', 'professor', 'queen', 'rabbi', 'rev',
      'reverend', 'saint', 'senator', 'senor', 'senora', 'senorita', 'septa',
      'septon', 'ser', 'sergeant', 'sgt', 'signor', 'signora', 'sir',
      'sister', 'son', 'squire', 'st', 'teacher', 'the', 'uncle', 'vicar',
      'viscount', 'viscountess', 'wife', 'young',
    };
    final words = name
        .split(RegExp(r"[^A-Za-z']+"))
        .where((w) => w.isNotEmpty && !titles.contains(w.toLowerCase()))
        .toList();
    final picked = words.isEmpty ? [name] : words;
    final letters = picked.length == 1
        ? picked.first.substring(0, 1)
        : '${picked.first[0]}${picked.last[0]}';
    return letters.toUpperCase();
  }

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
