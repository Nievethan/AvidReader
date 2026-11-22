import 'dart:async';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';

import '../models/book_item.dart';
import '../theme/classic_lit_theme.dart';
import '../widgets/paper_card.dart';
import '../widgets/scene_gallery.dart';
import '../widgets/vintage_progress_bar.dart';

class ReaderScreen extends StatefulWidget {
  final BookItem book;
  final VoidCallback onBackTap;
  final VoidCallback onAskAiTap;
  final VoidCallback onVisualizeTap;
  final ValueChanged<int> onPageChange;
  final ValueChanged<int> onGoToPage;

  const ReaderScreen({
    super.key,
    required this.book,
    required this.onBackTap,
    required this.onAskAiTap,
    required this.onVisualizeTap,
    required this.onPageChange,
    required this.onGoToPage,
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
        // currentPage is 0-based; the backend's spoiler boundary (and
        // /content) are 1-based -- same +1 as _loadContent() above.
        currentPage: widget.book.currentPage + 1,
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

  /// Illustrate button: asks the backend for a picture of the page (PDF) or
  /// chapter (EPUB) on screen and shows it in a dialog. A page illustrated
  /// before comes back instantly; a new one takes a few seconds to paint.
  Future<void> _illustratePage() async {
    final isEpub = widget.book.fileType.toLowerCase() == 'epub';
    final unit = isEpub ? 'chapter' : 'page';
    // Same 1-based conversion as _loadContent(): currentPage is 0-based.
    final position = isEpub
        ? (widget.book.currentChapter < 1 ? 1 : widget.book.currentChapter)
        : widget.book.currentPage + 1;
    final future = api.illustrate(widget.book.id, position);

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ClassicLitTheme.parchmentBg,
        contentPadding: const EdgeInsets.fromLTRB(14, 14, 14, 0),
        content: SizedBox(
          width: 360,
          child: FutureBuilder<SceneResult>(
            future: future,
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const CircularProgressIndicator(
                        color: ClassicLitTheme.oxbloodPrimary,
                      ),
                      const SizedBox(height: 14),
                      Text(
                        'Painting this $unit… this takes a few seconds.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                );
              }
              if (snap.hasError) {
                final error = snap.error;
                return Text(
                  error is ApiException
                      ? error.message
                      : 'Something went wrong. Try again.',
                  textAlign: TextAlign.center,
                );
              }
              final result = snap.data!;
              final scene = result.scene;
              return SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (scene != null) SceneCard(scene: scene),
                    if (result.message != null) ...[
                      const SizedBox(height: 8),
                      Text(result.message!, textAlign: TextAlign.center),
                    ],
                  ],
                ),
              );
            },
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  void _showAddWordDialog({String? defaultWord, String? defaultMeaning}) {
    final wordController = TextEditingController(text: defaultWord);
    final meaningController = TextEditingController(text: defaultMeaning);
    final quoteController = TextEditingController();
    final loc = widget.book.fileType.toLowerCase() == 'epub'
        ? 'chapter ${widget.book.currentChapter}'
        : 'page ${widget.book.currentPage + 1}';
    final locController = TextEditingController(text: loc);

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ClassicLitTheme.parchmentBg,
        title: const Text(
          'Add to Word Wall',
          style: TextStyle(
            fontFamily: ClassicLitTheme.serifFont,
            fontWeight: FontWeight.w700,
            color: ClassicLitTheme.oxbloodPrimary,
          ),
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: wordController,
                autofocus: defaultWord == null || defaultWord.isEmpty,
                decoration: const InputDecoration(
                  labelText: 'Word / Phrase *',
                  hintText: 'e.g. lugubrious',
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: meaningController,
                decoration: const InputDecoration(
                  labelText: 'Meaning / Definition',
                  hintText: 'e.g. mournful, dismal',
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: quoteController,
                decoration: const InputDecoration(
                  labelText: 'Quote from page',
                  hintText: 'e.g. with a lugubrious sigh',
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: locController,
                decoration: const InputDecoration(
                  labelText: 'Source Location',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final w = wordController.text.trim();
              if (w.isEmpty) return;
              Navigator.pop(ctx);
              try {
                await api.addWord(
                  widget.book.id,
                  word: w,
                  meaning: meaningController.text.trim(),
                  quote: quoteController.text.trim(),
                  sourceLocation: locController.text.trim(),
                );
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Saved "$w" to Word Wall')),
                  );
                }
              } on ApiException catch (e) {
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Could not save word: ${e.message}')),
                  );
                }
              }
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: ClassicLitTheme.oxbloodPrimary,
              foregroundColor: ClassicLitTheme.inkOnPrimary,
            ),
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  // PDF page jump only: EPUB chapter navigation isn't wired up anywhere in
  // the Reader yet (Prev/Next only ever change currentPage, never
  // currentChapter), so there's no page/chapter number to jump to for EPUB
  // today -- that's a separate, pre-existing gap, not something this adds.
  void _showGoToPageDialog() {
    final total = widget.book.totalPages;
    final current = widget.book.currentPage + 1; // 1-based for display
    final controller = TextEditingController(text: '$current');
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ClassicLitTheme.parchmentBg,
        title: const Text('Go to Page'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.number,
          decoration: InputDecoration(
            labelText: total != null ? 'Page number (1-$total)' : 'Page number',
          ),
          onSubmitted: (_) => _submitGoToPage(ctx, controller.text),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => _submitGoToPage(ctx, controller.text),
            style: ElevatedButton.styleFrom(
              backgroundColor: ClassicLitTheme.oxbloodPrimary,
              foregroundColor: ClassicLitTheme.inkOnPrimary,
            ),
            child: const Text('Go'),
          ),
        ],
      ),
    );
  }

  void _submitGoToPage(BuildContext dialogContext, String text) {
    final target = int.tryParse(text.trim());
    if (target == null || target < 1) return;
    Navigator.pop(dialogContext);
    widget.onGoToPage(target - 1); // pages are stored 0-based internally
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
            children: _buildPassageContent(),
          ),
        ),

        // 4-Button Contextual Selection Toolbar -- fixed in place (not
        // inside the scrollable passage above), so it's always reachable
        // without scrolling through the whole page.
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 0, 18, 10),
          child: Row(
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
                label: 'Word Wall',
                onTap: () => _showAddWordDialog(),
              ),
              const SizedBox(width: 6),
              _buildSelectionActionButton(
                label: 'Illustrate',
                onTap: (_page?.content ?? '').isEmpty ? () {} : _illustratePage,
              ),
            ],
          ),
        ),

        // Explanation panel -- also fixed in place, with its own bounded
        // height + internal scroll, so it never gets lost below the fold.
        if (_activeExplanation != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 10),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 180),
              child: SingleChildScrollView(
                child: PaperCard(
                  backgroundColor: ClassicLitTheme.elevatedPaper,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
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
                              style:
                                  const TextStyle(fontSize: 12.5, height: 1.45),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton.icon(
                          onPressed: () => _showAddWordDialog(
                            defaultMeaning: _activeExplanation,
                          ),
                          icon: const Icon(Icons.bookmark_add_outlined,
                              size: 14),
                          label: const Text(
                            'Save to Word Wall',
                            style: TextStyle(
                              fontSize: 11.5,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
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
                    InkWell(
                      onTap: widget.book.fileType.toLowerCase() == 'epub'
                          ? null
                          : _showGoToPageDialog,
                      borderRadius: BorderRadius.circular(4),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 4,
                          vertical: 2,
                        ),
                        child: Text(
                          widget.book.pagesLabel,
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: ClassicLitTheme.inkSecondary,
                            decoration: TextDecoration.underline,
                            decorationStyle: TextDecorationStyle.dotted,
                          ),
                        ),
                      ),
                    ),
                    IconButton(
                      tooltip: 'Next page',
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.chevron_right, size: 20),
                      onPressed: (widget.book.totalPages == null ||
                              widget.book.currentPage <
                                  widget.book.totalPages! - 1)
                          ? () => widget.onPageChange(1)
                          : null,
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
      final isIndexing =
          ingestion == null || ingestion.status == 'processing';
      return [
        _statusMessage(message),
        if (isIndexing) ...[
          const SizedBox(height: 12),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 40),
            child: LinearProgressIndicator(
              color: ClassicLitTheme.oxbloodPrimary,
              backgroundColor: ClassicLitTheme.elevatedPaper,
            ),
          ),
        ],
      ];
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
