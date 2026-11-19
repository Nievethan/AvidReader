import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'models/character_map_item.dart';
import 'models/engagement_item.dart';
import 'models/word_wall_item.dart';

export 'models/character_map_item.dart';
export 'models/engagement_item.dart';
export 'models/word_wall_item.dart';

/// Base URL of the FastAPI backend. Override at run time with:
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
/// (10.0.2.2 is how the Android emulator reaches your computer.)
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

class ApiException implements Exception {
  final int? statusCode;
  final String message;

  ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}

/// Raw book data from `GET /api/v1/books` merged with its progress.
class ApiBook {
  final String id;
  final String title;
  final String? author;
  final String fileType;
  final String processingStatus;
  final int? totalPages;
  final int? currentPage;
  final int? currentChapter;
  final double? percentComplete;

  ApiBook({
    required this.id,
    required this.title,
    required this.author,
    required this.fileType,
    required this.processingStatus,
    required this.totalPages,
    this.currentPage,
    this.currentChapter,
    this.percentComplete,
  });

  factory ApiBook.fromJson(Map<String, dynamic> json) => ApiBook(
    id: json['id'] as String,
    title: (json['title'] as String?) ?? (json['filename'] as String? ?? 'Untitled'),
    author: json['author'] as String?,
    fileType: (json['file_type'] as String?) ?? '',
    processingStatus: (json['processing_status'] as String?) ?? 'uploaded',
    totalPages: json['total_pages'] as int?,
  );

  ApiBook withProgress(Map<String, dynamic> p) => ApiBook(
    id: id,
    title: title,
    author: author,
    fileType: fileType,
    processingStatus: processingStatus,
    totalPages: totalPages,
    currentPage: p['current_page'] as int?,
    currentChapter: p['current_chapter'] as int?,
    percentComplete: (p['percent_complete'] as num?)?.toDouble(),
  );
}

/// `GET /books/{id}/ingestion`: processing status while a book indexes.
class IngestionStatus {
  final String status; // uploaded | processing | ready | failed | unsupported
  final String? message;
  final int? totalPages;
  final int? chunkCount;

  IngestionStatus({
    required this.status,
    this.message,
    this.totalPages,
    this.chunkCount,
  });

  factory IngestionStatus.fromJson(Map<String, dynamic> json) =>
      IngestionStatus(
        status: json['status'] as String,
        message: json['message'] as String?,
        totalPages: json['total_pages'] as int?,
        chunkCount: json['chunk_count'] as int?,
      );
}

/// `GET /books/{id}/content`: the real extracted text of one page/chapter.
class BookContent {
  final String status; // ready | processing | not_available
  final String? content;
  final String? reason;
  final int? index;
  final int? total;

  BookContent({
    required this.status,
    this.content,
    this.reason,
    this.index,
    this.total,
  });

  factory BookContent.fromJson(Map<String, dynamic> json) => BookContent(
    status: json['status'] as String,
    content: json['content'] as String?,
    reason: json['reason'] as String?,
    index: json['index'] as int?,
    total: json['total'] as int?,
  );
}

class ChatResult {
  final String conversationId;
  final String answer;
  final String providerStatus;
  final String answerType;
  final bool isHypothetical;
  final List<String> citations;
  final String? spoilerReason;

  ChatResult({
    required this.conversationId,
    required this.answer,
    required this.providerStatus,
    this.answerType = 'grounded',
    required this.isHypothetical,
    required this.citations,
    this.spoilerReason,
  });
}

class ApiClient {
  final String baseUrl;
  final http.Client _http;

  ApiClient({this.baseUrl = apiBaseUrl, http.Client? client})
    : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  /// Absolute URL for a backend-relative path such as a character's
  /// `portrait_url`.
  String absoluteUrl(String path) => '$baseUrl$path';

  dynamic _decode(http.Response res) {
    if (res.statusCode >= 200 && res.statusCode < 300) {
      if (res.body.isEmpty) return null;
      return jsonDecode(utf8.decode(res.bodyBytes));
    }
    String message = 'Request failed (${res.statusCode})';
    try {
      final body = jsonDecode(res.body);
      final err = body is Map ? body['error'] : null;
      if (err is Map && err['message'] != null) {
        message = err['message'] as String;
      }
    } catch (_) {}
    throw ApiException(message, statusCode: res.statusCode);
  }

  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on http.ClientException {
      throw ApiException(
        "Can't reach the backend at $baseUrl. Is docker-compose running?",
      );
    }
  }

  Future<List<ApiBook>> listBooks() => _guard(() async {
    final data = _decode(await _http.get(_uri('/api/v1/books')));
    final items = (data['items'] as List).cast<Map<String, dynamic>>();
    final books = items.map(ApiBook.fromJson).toList();
    return Future.wait(
      books.map((b) async => b.withProgress(await getProgress(b.id))),
    );
  });

  Future<Map<String, dynamic>> getProgress(String bookId) => _guard(() async {
    final data = _decode(
      await _http.get(_uri('/api/v1/books/$bookId/progress')),
    );
    return (data as Map).cast<String, dynamic>();
  });

  Future<Map<String, dynamic>> updateProgress(
    String bookId, {
    int? currentPage,
    int? currentChapter,
    double? percentComplete,
  }) => _guard(() async {
    final body = <String, dynamic>{
      'current_page': ?currentPage,
      'current_chapter': ?currentChapter,
      'percent_complete': ?percentComplete,
    };
    final data = _decode(
      await _http.put(
        _uri('/api/v1/books/$bookId/progress'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ),
    );
    return (data as Map).cast<String, dynamic>();
  });

  Future<ApiBook> uploadBook({
    required Uint8List bytes,
    required String filename,
    String? title,
    String? author,
  }) => _guard(() async {
    final req = http.MultipartRequest('POST', _uri('/api/v1/books'))
      ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    if (title != null && title.isNotEmpty) req.fields['title'] = title;
    if (author != null && author.isNotEmpty) req.fields['author'] = author;
    final res = await http.Response.fromStream(await _http.send(req));
    return ApiBook.fromJson((_decode(res) as Map).cast<String, dynamic>());
  });

  Future<void> deleteBook(String bookId) => _guard(() async {
    _decode(await _http.delete(_uri('/api/v1/books/$bookId')));
  });

  Future<RelationshipsResult> getRelationships(String bookId) =>
      _guard(() async {
        final data = _decode(
          await _http.get(_uri('/api/v1/books/$bookId/relationships')),
        );
        return RelationshipsResult.fromJson(
            (data as Map).cast<String, dynamic>());
      });

  Future<RelationshipsResult> generateRelationships(String bookId) =>
      _guard(() async {
        final data = _decode(
          await _http.post(_uri('/api/v1/books/$bookId/relationships/generate')),
        );
        return RelationshipsResult.fromJson(
            (data as Map).cast<String, dynamic>());
      });

  Future<List<WordWallEntry>> listWords(String bookId) => _guard(() async {
        final data = _decode(
          await _http.get(_uri('/api/v1/books/$bookId/words')),
        );
        final items =
            (data['items'] as List? ?? []).cast<Map<String, dynamic>>();
        return items.map(WordWallEntry.fromJson).toList();
      });

  Future<WordWallEntry> addWord(
    String bookId, {
    required String word,
    String? meaning,
    String? quote,
    String? sourceLocation,
  }) =>
      _guard(() async {
        final body = <String, dynamic>{
          'word': word,
          if (meaning != null && meaning.isNotEmpty) 'meaning': meaning,
          if (quote != null && quote.isNotEmpty) 'quote': quote,
          if (sourceLocation != null && sourceLocation.isNotEmpty)
            'source_location': sourceLocation,
        };
        final data = _decode(
          await _http.post(
            _uri('/api/v1/books/$bookId/words'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          ),
        );
        return WordWallEntry.fromJson((data as Map).cast<String, dynamic>());
      });

  Future<void> deleteWord(String bookId, String wordId) => _guard(() async {
        _decode(
          await _http.delete(_uri('/api/v1/books/$bookId/words/$wordId')),
        );
      });

  Future<ReadingLogResult> getReadingLog() => _guard(() async {
        final data = _decode(
          await _http.get(_uri('/api/v1/reading-log')),
        );
        return ReadingLogResult.fromJson(
            (data as Map).cast<String, dynamic>());
      });

  Future<AchievementsResult> getAchievements() => _guard(() async {
        final data = _decode(
          await _http.get(_uri('/api/v1/achievements')),
        );
        return AchievementsResult.fromJson(
            (data as Map).cast<String, dynamic>());
      });

  Future<IngestionStatus> getIngestionStatus(String bookId) => _guard(() async {
    final data = _decode(
      await _http.get(_uri('/api/v1/books/$bookId/ingestion')),
    );
    return IngestionStatus.fromJson((data as Map).cast<String, dynamic>());
  });

  /// Pass exactly one of `page` (PDF, 1-based) or `chapter` (EPUB, 1-based).
  Future<BookContent> getContent(
    String bookId, {
    int? page,
    int? chapter,
  }) => _guard(() async {
    final query = page != null ? 'page=$page' : 'chapter=$chapter';
    final data = _decode(
      await _http.get(_uri('/api/v1/books/$bookId/content?$query')),
    );
    return BookContent.fromJson((data as Map).cast<String, dynamic>());
  });

  Future<ChatResult> chat({
    required String bookId,
    required String question,
    String? conversationId,
    String mode = 'research',
    String interactionType = 'question',
    String explanationLevel = 'standard',
    String? selectedPassage,
    int? currentPage,
    int? currentChapter,
  }) => _guard(() async {
    final data = _decode(
      await _http.post(
        _uri('/api/v1/ai/chat'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'book_id': bookId,
          'conversation_id': conversationId,
          'question': question,
          'mode': mode,
          'interaction_type': interactionType,
          'explanation_level': explanationLevel,
          'selected_passage': selectedPassage,
          'reading_position': {
            'current_page': currentPage,
            'current_chapter': currentChapter,
            'location': null,
          },
        }),
      ),
    );
    final citations = (data['citations'] as List? ?? []).map((c) {
      if (c is Map && c['page'] != null) return 'p. ${c['page']}';
      return c.toString();
    }).toList();
    final spoilerScope =
        data['spoiler_scope'] is Map ? data['spoiler_scope'] as Map : null;
    return ChatResult(
      conversationId: data['conversation_id'] as String,
      answer: data['answer'] as String,
      providerStatus: (data['provider_status'] as String?) ?? '',
      answerType: (data['answer_type'] as String?) ?? 'grounded',
      isHypothetical: (data['is_hypothetical'] as bool?) ?? false,
      citations: citations,
      spoilerReason: spoilerScope?['reason'] as String?,
    );
  });
}
