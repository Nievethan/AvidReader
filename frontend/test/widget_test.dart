// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:frontend/main.dart';

void main() {
  testWidgets('AvidReader 5-tab navigation smoke test', (
    WidgetTester tester,
  ) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const AvidReaderApp());

    //Test for if library screen is visible and has the correct text
    expect(find.text('My Library'), findsOneWidget);
    expect(find.text('CONTINUE READING'), findsOneWidget);

    // Testing if resume button works and takes user to the correct screen
    await tester.tap(find.text('Resume'));
    await tester.pumpAndSettle();
    expect(find.text('Selected passage'), findsOneWidget);

    // Testing if ask AI button works and takes user to the correct screen
    await tester.tap(find.byIcon(Icons.auto_awesome_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(AskAiScreen), findsOneWidget);
    expect(find.text('Every answer cites the source text.'), findsOneWidget);

    // Testing if visualize button works and takes user to the correct screen
    await tester.tap(find.byIcon(Icons.palette_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(VisualizeScreen), findsOneWidget);

    // Testing if the user can scroll down to see the "CHARACTERS IN THIS CHAPTER" text
    await tester.drag(find.byType(VisualizeScreen), const Offset(0, -300));
    await tester.pumpAndSettle();
    expect(find.text('CHARACTERS IN THIS CHAPTER'), findsOneWidget);

    // Testing if progress button works and takes user to the correct screen
    await tester.tap(find.text('Progress').last);
    await tester.pumpAndSettle();
    expect(find.byType(ProgressScreen), findsOneWidget);
    expect(find.text('My Progress'), findsOneWidget);
    expect(find.text('Comprehension by chapter'), findsOneWidget);
  });
}
