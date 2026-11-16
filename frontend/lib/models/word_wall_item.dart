class WordWallEntry {
  final String id;
  final String bookId;
  final String word;
  final String? meaning;
  final String? quote;
  final String? sourceLocation;
  final DateTime? createdAt;

  const WordWallEntry({
    required this.id,
    required this.bookId,
    required this.word,
    this.meaning,
    this.quote,
    this.sourceLocation,
    this.createdAt,
  });

  factory WordWallEntry.fromJson(Map<String, dynamic> json) => WordWallEntry(
        id: json['id'] as String,
        bookId: json['book_id'] as String,
        word: json['word'] as String,
        meaning: json['meaning'] as String?,
        quote: json['quote'] as String?,
        sourceLocation: json['source_location'] as String?,
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'book_id': bookId,
        'word': word,
        'meaning': meaning,
        'quote': quote,
        'source_location': sourceLocation,
        'created_at': createdAt?.toIso8601String(),
      };
}
