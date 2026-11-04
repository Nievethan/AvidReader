import 'package:flutter/material.dart';

import '../api_client.dart';
import '../theme/classic_lit_theme.dart';

class BookItem {
  final String id;
  final String title;
  final String author;
  final int currentChapter;
  final int currentPage;
  // Null until the backend's parser knows the real page count.
  final int? totalPages;
  final double? percentComplete;
  final String processingStatus;
  final Color spineColor;

  const BookItem({
    required this.id,
    required this.title,
    required this.author,
    required this.currentChapter,
    required this.currentPage,
    required this.totalPages,
    required this.spineColor,
    this.percentComplete,
    this.processingStatus = 'ready',
  });

  static const List<Color> _spinePalette = [
    ClassicLitTheme.oxbloodPrimary,
    ClassicLitTheme.libraryGreen,
    Color(0xFF4A3B32),
    Color(0xFF5B3246),
  ];

  factory BookItem.fromApi(ApiBook b) => BookItem(
    id: b.id,
    title: b.title,
    author: b.author ?? 'Unknown author',
    currentChapter: b.currentChapter ?? 1,
    currentPage: b.currentPage ?? 0,
    totalPages: b.totalPages,
    percentComplete: b.percentComplete,
    processingStatus: b.processingStatus,
    spineColor: _spinePalette[b.id.hashCode.abs() % _spinePalette.length],
  );

  BookItem copyWith({int? currentPage, double? percentComplete}) => BookItem(
    id: id,
    title: title,
    author: author,
    currentChapter: currentChapter,
    currentPage: currentPage ?? this.currentPage,
    totalPages: totalPages,
    percentComplete: percentComplete ?? this.percentComplete,
    processingStatus: processingStatus,
    spineColor: spineColor,
  );

  bool get isProcessed => processingStatus == 'ready';

  double get progress {
    if (percentComplete != null) {
      return (percentComplete! / 100).clamp(0, 1).toDouble();
    }
    final total = totalPages;
    if (total == null || total == 0) return 0;
    return (currentPage / total).clamp(0, 1).toDouble();
  }

  int get progressPercent => (progress * 100).round();
  String get pagesLabel => 'p. $currentPage / ${totalPages ?? '?'}';
}
