import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/api_client.dart';
import 'package:frontend/main.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _bookId = '40fae399-b025-4bc3-a17f-f51ba31fc493';

/// Fake backend that answers like the real FastAPI routes in docs/API_CONTRACT.md.
http.Client _fakeBackend() => MockClient((req) async {
  final path = req.url.path;
  if (req.method == 'GET' && path == '/api/v1/books') {
    return http.Response(
      jsonEncode({
        'items': [
          {
            'id': _bookId,
            'title': 'Test Book',
            'author': 'Capstone Team',
            'filename': 'test.pdf',
            'file_type': 'pdf',
            'processing_status': 'ready',
            'total_pages': 10,
          },
        ],
        'total': 1,
      }),
      200,
    );
  }
  if (req.method == 'GET' && path == '/api/v1/books/$_bookId/progress') {
    return http.Response(
      jsonEncode({
        'book_id': _bookId,
        'current_page': 3,
        'current_chapter': 1,
        'location': null,
        'percent_complete': null,
        'updated_at': null,
      }),
      200,
    );
  }
  if (req.method == 'GET' && path == '/api/v1/books/$_bookId/content') {
    return http.Response(
      jsonEncode({
        'book_id': _bookId,
        'status': 'ready',
        'content': 'The real backend returned this page of the book.',
        'unit': 'page',
        'index': 3,
        'total': 10,
        'title': null,
      }),
      200,
    );
  }
  if (req.method == 'POST' && path == '/api/v1/ai/chat') {
    return http.Response(
      jsonEncode({
        'conversation_id': 'conv-1',
        'message_id': 'msg-1',
        'book_id': _bookId,
        'answer': '[MOCK RESPONSE] hello',
        'answer_type': 'grounded',
        'provider_status': 'ok',
        'is_hypothetical': false,
        'citations': [],
        'spoiler_scope': {'restricted_to_progress': false, 'reason': ''},
        'created_at': '2026-10-30T15:19:59.613607',
      }),
      200,
    );
  }
  return http.Response('{"error":{"code":"NOT_FOUND","message":"nope"}}', 404);
});

void main() {
  setUp(() => api = ApiClient(client: _fakeBackend()));

  testWidgets('AvidReader 5-tab navigation smoke test', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const AvidReaderApp());
    await tester.pumpAndSettle();

    // Library shows the book loaded from the (fake) backend
    expect(find.text('My Library'), findsOneWidget);
    expect(find.text('CONTINUE READING'), findsOneWidget);
    expect(find.text('Test Book'), findsWidgets);

    // Resume opens the reader
    await tester.tap(find.text('Resume'));
    await tester.pumpAndSettle();
    expect(
      find.text('The real backend returned this page of the book.'),
      findsOneWidget,
    );
    expect(find.text('p. 3 / 10'), findsOneWidget);

    // Ask AI sends a question and shows the backend's answer
    await tester.tap(find.byIcon(Icons.auto_awesome_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(AskAiScreen), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'Who is the narrator?');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();
    expect(find.text('[MOCK RESPONSE] hello'), findsOneWidget);

    // Visualize
    await tester.tap(find.byIcon(Icons.palette_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(VisualizeScreen), findsOneWidget);
    await tester.drag(find.byType(VisualizeScreen), const Offset(0, -300));
    await tester.pumpAndSettle();
    expect(find.text('CHARACTERS IN THIS CHAPTER'), findsOneWidget);

    // Progress
    await tester.tap(find.text('Progress').last);
    await tester.pumpAndSettle();
    expect(find.byType(ProgressScreen), findsOneWidget);
    expect(find.text('My Progress'), findsOneWidget);
    expect(find.text('Comprehension by chapter'), findsOneWidget);
  });
}
