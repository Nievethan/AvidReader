import 'dart:async';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';

import '../models/book_item.dart';
import '../theme/classic_lit_theme.dart';
import '../widgets/paper_card.dart';
import '../widgets/vintage_progress_bar.dart';

class ReaderScreen extends StatefulWidget {
  final BookItem book;
  final VoidCallback onBackTap;
  final VoidCallback onAskAiTap;
  final VoidCallback onVisualizeTap;
  final ValueChanged<int> onPageChange;

  const ReaderScreen({
    super.key,
    required this.book,
    required this.onBackTap,
    required this.onAskAiTap,
    required this.onVisualizeTap,
    required this.onPageChange,
  });

  @override
  State<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends State<ReaderScreen> {
  double _fontSize = 16.0;
  String? _activeExplanation;
  bool _explaining = false;

  BookContent? _page;
  IngestionStatus? _ingestion;
  bool _loading = true;
  String? _error;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant ReaderScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.book.id != widget.book.id) _activeExplanation = null;
    if (oldWidget.book.id != widget.book.id ||
        oldWidget.book.currentPage != widget.book.currentPage ||
        oldWidget.book.currentChapter != widget.book.currentChapter ||
        oldWidget.book.processingStatus != widget.book.processingStatus) {
      _load();
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  // Not ready yet: check ingestion status and, while still "processing",
  // poll every 2s until it flips to ready/failed/unsupported.
  Future<void> _load() async {
    _pollTimer?.cancel();
    setState(() {
      _loading = true;
      _error = null;
      _page = null;
    });

    if (widget.book.processingStatus == 'ready') {
      await _loadContent();
      return;
    }

    try {
      final ingestion = await api.getIngestionStatus(widget.book.id);
      if (!mounted) return;
      setState(() {
        _ingestion = ingestion;
        _loading = false;
      });
      if (ingestion.status == 'processing') {
        _pollTimer = Timer(const Duration(seconds: 2), _load);
      } else if (ingestion.status == 'ready') {
        await _loadContent();
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _loadContent() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final isEpub = widget.book.fileType.toLowerCase() == 'epub';
      final result = isEpub
          ? await api.getContent(
              widget.book.id,
              // Chapters are already 1-based throughout the app.
              chapter: widget.book.currentChapter < 1
                  ? 1
                  : widget.book.currentChapter,
            )
          : await api.getContent(
              widget.book.id,
              // currentPage is 0-based ("p. 0 / 99" at the start) but
              // /content is 1-based, so it's always off by one.
              page: widget.book.currentPage + 1,
            );
      if (!mounted) return;
      setState(() {
        _page = result;
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

  Future<void> _explainPassage() async {
    final passage = _page?.content;
    if (passage == null || passage.isEmpty) return;
    setState(() {
      _explaining = true;
      _activeExplanation = 'Thinking…';
    });
    try {
      final result = await api.chat(
        bookId: widget.book.id,
        question: 'Explain this passage.',
        mode: 'study',
        interactionType: 'explain',
        selectedPassage: passage,
        currentPage: widget.book.currentPage,
        currentChapter: widget.book.currentChapter,
      );
      setState(() => _activeExplanation = result.answer);
    } on ApiException catch (e) {
      setState(
        () => _activeExplanation = 'Couldn\'t get an explanation: ${e.message}',
      );
    } finally {
      if (mounted) setState(() => _explaining = false);
    }
  }

  void _cycleFontSize() {
    setState(() {
      if (_fontSize == 16.0) {
        _fontSize = 18.5;
      } else if (_fontSize == 18.5) {
        _fontSize = 14.5;
      } else {
        _fontSize = 16.0;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Top Reader Header
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: const BoxDecoration(
            border: Border(
              bottom: BorderSide(color: ClassicLitTheme.deckleBorder),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              InkWell(
                onTap: widget.onBackTap,
                borderRadius: BorderRadius.circular(4),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                  child: Text(
                    '‹ Back',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: ClassicLitTheme.oxbloodPrimary,
                    ),
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  widget.book.title,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
              ),
              InkWell(
                onTap: _cycleFontSize,
                borderRadius: BorderRadius.circular(4),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    border: Border.all(color: ClassicLitTheme.deckleBorder),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'Aa',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                  ),
                ),
              ),
            ],
          ),
        ),

        // Reading Passage Body
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(18),
            children: [
              ..._buildPassageContent(),
              const SizedBox(height: 10),

              // 4-Button Contextual Selection Toolbar
              Row(
                children: [
                  _buildSelectionActionButton(
                    label: 'Explain',
                    onTap: (_explaining || (_page?.content ?? '').isEmpty)
                        ? () {}
                        : _explainPassage,
                  ),
                  const SizedBox(width: 6),
                  _buildSelectionActionButton(
                    label: 'Ask AI',
                    onTap: widget.onAskAiTap,
                  ),
                  const SizedBox(width: 6),
                  _buildSelectionActionButton(
                    label: 'Visualize',
                    onTap: widget.onVisualizeTap,
                  ),
                  const SizedBox(width: 6),
                  _buildSelectionActionButton(
                    label: 'Note',
                    onTap: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text(
                            'Notes aren\'t connected to the backend yet',
                          ),
                        ),
                      );
                    },
                  ),
                ],
              ),

              if (_activeExplanation != null) ...[
                const SizedBox(height: 12),
                PaperCard(
                  backgroundColor: ClassicLitTheme.elevatedPaper,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(
                        Icons.auto_stories,
                        size: 16,
                        color: ClassicLitTheme.oxbloodPrimary,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _activeExplanation!,
                          style: const TextStyle(fontSize: 12.5, height: 1.45),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

            ],
          ),
        ),

        // Bottom Chapter Progress Footer Card
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
          child: PaperCard(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    IconButton(
                      tooltip: 'Previous page',
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.chevron_left, size: 20),
                      onPressed: widget.book.currentPage > 0
                          ? () => widget.onPageChange(-1)
                          : null,
                    ),
                    Text(
                      widget.book.pagesLabel,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                    IconButton(
                      tooltip: 'Next page',
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.chevron_right, size: 20),
                      onPressed: () => widget.onPageChange(1),
                    ),
                    const Spacer(),
                    Text(
                      'Ch. ${widget.book.currentChapter}',
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: ClassicLitTheme.inkPrimary,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                VintageProgressBar(value: widget.book.progress),
              ],
            ),
          ),
        ),
      ],
    );
  }

  List<Widget> _buildPassageContent() {
    if (_loading) {
      return const [
        Padding(
          padding: EdgeInsets.symmetric(vertical: 24),
          child: Center(child: CircularProgressIndicator()),
        ),
      ];
    }

    if (_error != null) {
      return [_statusMessage('Couldn\'t load this page: $_error')];
    }

    // Trust what the Reader itself fetched, not widget.book.processingStatus:
    // the dashboard's book list isn't re-polled after upload, so it can stay
    // stuck on "processing" long after ingestion has actually finished.
    final content = _page?.content;
    if (content == null || content.isEmpty) {
      final ingestion = _ingestion;
      final message = switch (ingestion?.status) {
        'processing' => 'Still indexing this book — checking again shortly…',
        'failed' => ingestion?.message ?? 'Indexing this book failed.',
        'unsupported' =>
          ingestion?.message ?? 'This book format isn\'t supported yet.',
        'ready' => 'No text found for this page.',
        _ => 'This book isn\'t ready to read yet.',
      };
      return [_statusMessage(message)];
    }

    return [
      Text(
        content,
        style: TextStyle(
          fontFamily: ClassicLitTheme.serifFont,
          fontSize: _fontSize,
          height: 1.65,
          color: ClassicLitTheme.inkPrimary,
        ),
      ),
      const SizedBox(height: 16),
    ];
  }

  Widget _statusMessage(String text) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 24),
    child: Text(
      text,
      textAlign: TextAlign.center,
      style: const TextStyle(
        fontStyle: FontStyle.italic,
        color: ClassicLitTheme.inkSecondary,
      ),
    ),
  );

  Widget _buildSelectionActionButton({
    required String label,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: OutlinedButton(
        onPressed: onTap,
        style: OutlinedButton.styleFrom(
          foregroundColor: ClassicLitTheme.inkPrimary,
          backgroundColor: ClassicLitTheme.elevatedPaper,
          side: const BorderSide(color: ClassicLitTheme.inkPrimary, width: 1.1),
          padding: const EdgeInsets.symmetric(vertical: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}
