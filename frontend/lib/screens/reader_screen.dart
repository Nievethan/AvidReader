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
  // Sample passage until the backend can return real book text
  // (GET /books/{id}/content is "not_available" until ingestion exists).
  static const String _samplePassage =
      'He had successfully avoided meeting his landlady on the staircase. His garret was under the roof of a high, five-storied house and was more like a cupboard than a room.';

  double _fontSize = 16.0;
  String? _activeExplanation;
  bool _explaining = false;

  @override
  void didUpdateWidget(covariant ReaderScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.book.id != widget.book.id) _activeExplanation = null;
  }

  Future<void> _explainPassage() async {
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
        selectedPassage: _samplePassage,
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
              if (!widget.book.isProcessed) ...[
                const Text(
                  'Showing a sample passage: real book text appears once ingestion is connected.',
                  style: TextStyle(
                    fontSize: 11,
                    fontStyle: FontStyle.italic,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
                const SizedBox(height: 12),
              ],
              Text(
                'On an exceptionally hot evening early in July a young man came out of the garret in which he lodged in S. Place and walked slowly, as though in hesitation, towards K. bridge.',
                style: TextStyle(
                  fontFamily: ClassicLitTheme.serifFont,
                  fontSize: _fontSize,
                  height: 1.65,
                  color: ClassicLitTheme.inkPrimary,
                ),
              ),
              const SizedBox(height: 16),

              // Highlighted / Selected Passage Box
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: ClassicLitTheme.goldHighlightWash,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: ClassicLitTheme.antiqueGold,
                    width: 1.5,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '“$_samplePassage”',
                      style: TextStyle(
                        fontFamily: ClassicLitTheme.serifFont,
                        fontSize: _fontSize,
                        fontStyle: FontStyle.italic,
                        height: 1.6,
                        color: ClassicLitTheme.inkPrimary,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Selected passage',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),

              // 4-Button Contextual Selection Toolbar
              Row(
                children: [
                  _buildSelectionActionButton(
                    label: 'Explain',
                    onTap: _explaining ? () {} : _explainPassage,
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

              const SizedBox(height: 18),
              Text(
                'The landlady who provided him with garret, dinners, and attendance, lived on the floor below, and every time he went out he was obliged to pass her kitchen, the door of which invariably stood open. And each time he passed, the young man had a sick, frightened feeling, which made him scowl and feel ashamed.',
                style: TextStyle(
                  fontFamily: ClassicLitTheme.serifFont,
                  fontSize: _fontSize,
                  height: 1.65,
                  color: ClassicLitTheme.inkPrimary,
                ),
              ),
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
