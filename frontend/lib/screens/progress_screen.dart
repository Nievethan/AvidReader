import 'package:flutter/material.dart';

import '../models/book_item.dart';
import '../theme/classic_lit_theme.dart';
import '../widgets/paper_card.dart';
import '../widgets/vintage_progress_bar.dart';

class ProgressScreen extends StatelessWidget {
  final BookItem book;

  const ProgressScreen({super.key, required this.book});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Top Header
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: const BoxDecoration(
            border: Border(
              bottom: BorderSide(color: ClassicLitTheme.deckleBorder),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'My Progress',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(width: 12),
              Flexible(
                child: Text(
                  book.title,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
              ),
            ],
          ),
        ),

        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // Card 1: Reading Progress & Streak
              PaperCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Reading progress',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 8),
                    VintageProgressBar(value: book.progress),
                    const SizedBox(height: 6),
                    Text(
                      '${book.progressPercent}% • streak 12 days',
                      style: const TextStyle(
                        fontSize: 12,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Card 2: Comprehension by Chapter
              PaperCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Comprehension by chapter',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 10),
                    _buildChapterMasteryRow('Ch. 5', 0.88),
                    const SizedBox(height: 8),
                    _buildChapterMasteryRow('Ch. 6', 0.64),
                    const SizedBox(height: 8),
                    _buildChapterMasteryRow('Ch. 7', 0.28),
                    const SizedBox(height: 10),
                    const Text(
                      'Explanations adapt to your level.',
                      style: TextStyle(
                        fontSize: 11,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Action Row: Start Quiz & Flashcards
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'Launching Chapter 7 Socratic Quiz...',
                            ),
                          ),
                        );
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: ClassicLitTheme.oxbloodPrimary,
                        foregroundColor: ClassicLitTheme.inkOnPrimary,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(vertical: 11),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      child: const Text(
                        'Start quiz',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Opening 14 Literary Flashcards...'),
                          ),
                        );
                      },
                      style: OutlinedButton.styleFrom(
                        foregroundColor: ClassicLitTheme.inkPrimary,
                        side: const BorderSide(
                          color: ClassicLitTheme.inkPrimary,
                          width: 1.2,
                        ),
                        padding: const EdgeInsets.symmetric(vertical: 11),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      child: const Text(
                        'Flashcards',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),

              // Card 3: Literary Insights
              PaperCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Insights',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 10),
                    _buildInsightItem(
                      badgeLabel: 'Map',
                      title: 'Character relationships',
                    ),
                    const SizedBox(height: 8),
                    _buildInsightItem(
                      badgeLabel: 'Line',
                      title: 'Plot timeline',
                    ),
                    const SizedBox(height: 8),
                    _buildInsightItem(badgeLabel: 'Tags', title: 'Themes'),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Card 4: Flagged Concepts
              const PaperCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Flagged concepts',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 14,
                      ),
                    ),
                    SizedBox(height: 6),
                    Text(
                      'Utilitarian Ethics • Psychological Dualism • St. Petersburg Topography',
                      style: TextStyle(
                        fontSize: 12.5,
                        color: ClassicLitTheme.oxbloodPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildChapterMasteryRow(String chapterLabel, double progress) {
    return Row(
      children: [
        SizedBox(
          width: 40,
          child: Text(
            chapterLabel,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: ClassicLitTheme.inkPrimary,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: VintageProgressBar(
            value: progress,
            fillColor: ClassicLitTheme.libraryGreen,
          ),
        ),
      ],
    );
  }

  Widget _buildInsightItem({
    required String badgeLabel,
    required String title,
  }) {
    return Row(
      children: [
        Container(
          width: 44,
          padding: const EdgeInsets.symmetric(vertical: 6),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: ClassicLitTheme.elevatedPaper,
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: ClassicLitTheme.deckleBorder),
          ),
          child: Text(
            badgeLabel,
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: ClassicLitTheme.oxbloodPrimary,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Text(
          title,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: ClassicLitTheme.inkPrimary,
          ),
        ),
      ],
    );
  }
}
