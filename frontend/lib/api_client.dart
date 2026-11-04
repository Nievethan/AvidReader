import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

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

class ChatResult {
  final String conversationId;
  final String answer;
  final String providerStatus;
  final bool isHypothetical;
  final List<String> citations;

  ChatResult({
    required this.conversationId,
    required this.answer,
    required this.providerStatus,
    required this.isHypothetical,
    required this.citations,
  });
}

class ApiClient {
  final String baseUrl;
  final http.Client _http;

  ApiClient({this.baseUrl = apiBaseUrl, http.Client? client})
    : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

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

  Future<ChatResult> chat({
    required String bookId,
    required String question,
    String? conversationId,
    String mode = 'research',
    String interactionType = 'question',
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
    return ChatResult(
      conversationId: data['conversation_id'] as String,
      answer: data['answer'] as String,
      providerStatus: (data['provider_status'] as String?) ?? '',
      isHypothetical: (data['is_hypothetical'] as bool?) ?? false,
      citations: citations,
    );
  });
}
