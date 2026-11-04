import 'package:flutter/material.dart';

import '../models/book_item.dart';
import '../models/character_visual.dart';
import '../theme/classic_lit_theme.dart';
import '../widgets/filter_pill_row.dart';
import '../widgets/paper_card.dart';
import '../widgets/vintage_progress_bar.dart';

class VisualizeScreen extends StatefulWidget {
  final BookItem book;

  const VisualizeScreen({super.key, required this.book});

  @override
  State<VisualizeScreen> createState() => _VisualizeScreenState();
}

class _VisualizeScreenState extends State<VisualizeScreen> {
  int _selectedCategoryIndex = 0;
  int _selectedCharacterIndex = 0;

  final List<CharacterVisual> _characters = const [
    CharacterVisual(
      name: 'Rodion Raskolnikov',
      role: 'Former Law Student',
      description: 'Slender, finely featured young man dressed in threadbare overcoat, feverish gaze reflecting intense philosophical turmoil.',
      citations: ['p. 84', 'p. 91'],
      icon: Icons.person_outline,
    ),
    CharacterVisual(
      name: 'Sofya Semyonovna (Sonya)',
      role: 'Quiet Confidante',
      description: 'Pale, gentle countenance with clear blue eyes characterized by unwavering compassion and quiet moral resilience.',
      citations: ['p. 98', 'p. 104'],
      icon: Icons.favorite_border,
    ),
    CharacterVisual(
      name: 'Porfiry Petrovich',
      role: 'Examining Magistrate',
      description: 'Stout, clean-shaven official with a shrewd, deceptively genial twinkle in his eye during psychological questioning.',
      citations: ['p. 108', 'p. 111'],
      icon: Icons.balance_outlined,
    ),
    CharacterVisual(
      name: 'Dmitri Razumikhin',
      role: 'Loyal University Friend',
      description: 'Tall, expressive, energetic companion whose warmth contrasts sharply with Raskolnikov’s brooding isolation.',
      citations: ['p. 88', 'p. 95'],
      icon: Icons.handshake_outlined,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final currentCharacter = _characters[_selectedCharacterIndex];

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
                'Visualize',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              Text(
                'Ch. ${widget.book.currentChapter}',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: ClassicLitTheme.inkSecondary,
                ),
              ),
            ],
          ),
        ),

        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              FilterPillRow(
                options: const ['Characters', 'Settings', 'Concept map'],
                selectedIndex: _selectedCategoryIndex,
                onSelected: (index) =>
                    setState(() => _selectedCategoryIndex = index),
              ),
              const SizedBox(height: 14),

              // Main Etching / Generated Image Canvas
              Container(
                height: 210,
                width: double.infinity,
                decoration: BoxDecoration(
                  color: ClassicLitTheme.linenCard,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: ClassicLitTheme.inkPrimary,
                    width: 1.2,
                  ),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      currentCharacter.icon,
                      size: 54,
                      color: ClassicLitTheme.oxbloodPrimary.withValues(
                        alpha: 0.75,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Generated image • ${currentCharacter.name}',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      '(19th-Century Woodcut / Etching Style)',
                      style: TextStyle(
                        fontSize: 11,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Character Details Card
              PaperCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      currentCharacter.name,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      currentCharacter.description,
                      style: const TextStyle(fontSize: 12.5, height: 1.45),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Based on ${currentCharacter.citations.join(', ')}',
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: ClassicLitTheme.libraryGreen,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),

              // Background Scene Generation Queue Card
              const PaperCard(
                backgroundColor: ClassicLitTheme.elevatedPaper,
                padding: EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Generating scene... about 8 s. Keep reading meanwhile.',
                      style: TextStyle(
                        fontSize: 11.5,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                    SizedBox(height: 6),
                    VintageProgressBar(
                      value: 0.68,
                      fillColor: ClassicLitTheme.libraryGreen,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),

              // Regenerate & Save Buttons
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(
                              'Regenerating portrait for ${currentCharacter.name}...',
                            ),
                          ),
                        );
                      },
                      style: OutlinedButton.styleFrom(
                        foregroundColor: ClassicLitTheme.inkPrimary,
                        side: const BorderSide(
                          color: ClassicLitTheme.inkPrimary,
                          width: 1.2,
                        ),
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      child: const Text(
                        'Regenerate',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(
                              'Saved ${currentCharacter.name} to Bookplate Gallery',
                            ),
                          ),
                        );
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: ClassicLitTheme.oxbloodPrimary,
                        foregroundColor: ClassicLitTheme.inkOnPrimary,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      child: const Text(
                        'Save',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 16),
              Text(
                'CHARACTERS IN THIS CHAPTER',
                style: Theme.of(context).textTheme.labelSmall,
              ),
              const SizedBox(height: 8),

              // 4-Item Character Thumbnail Strip
              Row(
                children: List.generate(_characters.length, (index) {
                  final char = _characters[index];
                  final isSelected = index == _selectedCharacterIndex;
                  return Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 3),
                      child: GestureDetector(
                        onTap: () =>
                            setState(() => _selectedCharacterIndex = index),
                        child: Container(
                          height: 68,
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? ClassicLitTheme.goldHighlightWash
                                : ClassicLitTheme.elevatedPaper,
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(
                              color: isSelected
                                  ? ClassicLitTheme.oxbloodPrimary
                                  : ClassicLitTheme.deckleBorder,
                              width: isSelected ? 1.6 : 1.1,
                            ),
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                char.icon,
                                size: 20,
                                color: isSelected
                                    ? ClassicLitTheme.oxbloodPrimary
                                    : ClassicLitTheme.inkSecondary,
                              ),
                              const SizedBox(height: 4),
                              Text(
                                char.name.split(' ').first,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: isSelected
                                      ? FontWeight.w700
                                      : FontWeight.w500,
                                  color: ClassicLitTheme.inkPrimary,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                }),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
