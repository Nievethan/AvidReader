import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';
import '../models/book_item.dart';
import '../theme/classic_lit_theme.dart';
import '../widgets/filter_pill_row.dart';
import '../widgets/paper_card.dart';
import '../widgets/vintage_progress_bar.dart';

class ProgressScreen extends StatefulWidget {
  final BookItem book;

  const ProgressScreen({super.key, required this.book});

  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  int _selectedTabIndex = 0; // 0: Overview, 1: Word Wall, 2: Achievements, 3: Reading Log

  bool _loading = true;
  String? _error;

  ReadingLogResult? _readingLog;
  AchievementsResult? _achievements;
  List<WordWallEntry> _words = [];

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  @override
  void didUpdateWidget(covariant ProgressScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.book.id != widget.book.id) {
      _loadAll();
    }
  }

  Future<void> _loadAll() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        api.getReadingLog(),
        api.getAchievements(),
        api.listWords(widget.book.id),
      ]);
      if (!mounted) return;
      setState(() {
        _readingLog = results[0] as ReadingLogResult;
        _achievements = results[1] as AchievementsResult;
        _words = results[2] as List<WordWallEntry>;
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

  Future<void> _deleteWord(String wordId) async {
    try {
      await api.deleteWord(widget.book.id, wordId);
      setState(() {
        _words.removeWhere((w) => w.id == wordId);
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Removed word from Word Wall')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not delete word: ${e.message}')),
        );
      }
    }
  }

  void _showAddWordDialog() {
    final wordController = TextEditingController();
    final meaningController = TextEditingController();
    final quoteController = TextEditingController();
    final locController = TextEditingController(
      text: widget.book.fileType.toLowerCase() == 'epub'
          ? 'Ch. ${widget.book.currentChapter}'
          : 'page ${widget.book.currentPage + 1}',
    );

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ClassicLitTheme.parchmentBg,
        title: const Text(
          'Add to Word Wall',
          style: TextStyle(
            fontFamily: ClassicLitTheme.serifFont,
            fontWeight: FontWeight.w700,
            color: ClassicLitTheme.inkPrimary,
          ),
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: wordController,
                autofocus: true,
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
                  labelText: 'Quote from text',
                  hintText: 'e.g. with a lugubrious sigh',
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: locController,
                decoration: const InputDecoration(
                  labelText: 'Source Location',
                  hintText: 'e.g. page 4',
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
                final entry = await api.addWord(
                  widget.book.id,
                  word: w,
                  meaning: meaningController.text.trim(),
                  quote: quoteController.text.trim(),
                  sourceLocation: locController.text.trim(),
                );
                if (mounted) {
                  setState(() {
                    _words.insert(0, entry);
                  });
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Added "$w" to Word Wall')),
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
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Flexible(
                    child: Text(
                      widget.book.title,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    icon: const Icon(Icons.refresh, size: 18),
                    tooltip: 'Refresh',
                    onPressed: _loadAll,
                    visualDensity: VisualDensity.compact,
                  ),
                ],
              ),
            ],
          ),
        ),

        Expanded(
          child: _loading
              ? const Center(
                  child: CircularProgressIndicator(
                    color: ClassicLitTheme.oxbloodPrimary,
                  ),
                )
              : _error != null
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.error_outline,
                              size: 36,
                              color: ClassicLitTheme.oxbloodPrimary,
                            ),
                            const SizedBox(height: 10),
                            Text(_error!, textAlign: TextAlign.center),
                            const SizedBox(height: 12),
                            OutlinedButton(
                              onPressed: _loadAll,
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      ),
                    )
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        FilterPillRow(
                          options: const [
                            'Overview',
                            'Word Wall',
                            'Achievements',
                            'Reading Log',
                          ],
                          selectedIndex: _selectedTabIndex,
                          onSelected: (i) =>
                              setState(() => _selectedTabIndex = i),
                        ),
                        const SizedBox(height: 16),
                        ..._buildSelectedTab(),
                      ],
                    ),
        ),
      ],
    );
  }

  List<Widget> _buildSelectedTab() {
    switch (_selectedTabIndex) {
      case 1:
        return _buildWordWallTab();
      case 2:
        return _buildAchievementsTab();
      case 3:
        return _buildReadingLogTab();
      default:
        return _buildOverviewTab();
    }
  }

  List<Widget> _buildOverviewTab() {
    final streak = _readingLog?.currentStreak ?? 0;
    final longestStreak = _readingLog?.longestStreak ?? 0;
    final unlockedAchievements =
        _achievements?.achievements.where((a) => a.unlocked).length ?? 0;
    final totalAchievements = _achievements?.achievements.length ?? 6;

    return [
      // Card 1: Reading Progress & Streak
      PaperCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Reading progress',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
                Text(
                  widget.book.pagesLabel,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            VintageProgressBar(value: widget.book.progress),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  '${widget.book.progressPercent}% completed',
                  style: const TextStyle(
                    fontSize: 12,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.local_fire_department,
                      size: 16,
                      color: ClassicLitTheme.antiqueGold,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '$streak day streak (best: $longestStreak)',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: ClassicLitTheme.inkPrimary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
      const SizedBox(height: 14),

      // Card 2: Word Wall Preview
      PaperCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Word Wall (${_words.length})',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
                TextButton(
                  onPressed: () => setState(() => _selectedTabIndex = 1),
                  child: const Text('View All ›'),
                ),
              ],
            ),
            if (_words.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  'No words saved yet. Tap Word Wall in the Reader to save literary vocabulary.',
                  style: TextStyle(
                    fontSize: 12,
                    color: ClassicLitTheme.inkSecondary,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              )
            else
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: _words.take(5).map((w) {
                  return Chip(
                    label: Text(
                      w.word,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: ClassicLitTheme.inkPrimary,
                      ),
                    ),
                    backgroundColor: ClassicLitTheme.elevatedPaper,
                    side: const BorderSide(color: ClassicLitTheme.deckleBorder),
                  );
                }).toList(),
              ),
          ],
        ),
      ),
      const SizedBox(height: 14),

      // Card 3: Achievements Progress
      PaperCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Achievements ($unlockedAchievements / $totalAchievements)',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
                TextButton(
                  onPressed: () => setState(() => _selectedTabIndex = 2),
                  child: const Text('View All ›'),
                ),
              ],
            ),
            const SizedBox(height: 4),
            VintageProgressBar(
              value: totalAchievements > 0
                  ? unlockedAchievements / totalAchievements
                  : 0,
              fillColor: ClassicLitTheme.antiqueGold,
            ),
            const SizedBox(height: 10),
            ...(_achievements?.achievements ?? []).take(3).map((ach) {
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Icon(
                      ach.unlocked
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      size: 16,
                      color: ach.unlocked
                          ? ClassicLitTheme.libraryGreen
                          : ClassicLitTheme.inkSecondary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        ach.label,
                        style: TextStyle(
                          fontSize: 12.5,
                          fontWeight: ach.unlocked
                              ? FontWeight.w700
                              : FontWeight.w500,
                          color: ach.unlocked
                              ? ClassicLitTheme.inkPrimary
                              : ClassicLitTheme.inkSecondary,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
      const SizedBox(height: 14),

      // Card 4: Recent Reading Log Summary
      PaperCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Recent Reading Log',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
                TextButton(
                  onPressed: () => setState(() => _selectedTabIndex = 3),
                  child: const Text('View All ›'),
                ),
              ],
            ),
            if ((_readingLog?.days ?? []).isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  'No reading sessions logged yet. Your reading progress automatically logs daily activity.',
                  style: TextStyle(
                    fontSize: 12,
                    color: ClassicLitTheme.inkSecondary,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              )
            else
              ...(_readingLog?.days ?? []).take(3).map((d) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        d.date,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: ClassicLitTheme.oxbloodPrimary,
                        ),
                      ),
                      Text(
                        '${d.bookTitle} (p. ${d.currentPage ?? 0})',
                        style: const TextStyle(
                          fontSize: 12,
                          color: ClassicLitTheme.inkSecondary,
                        ),
                      ),
                    ],
                  ),
                );
              }),
          ],
        ),
      ),
    ];
  }

  List<Widget> _buildWordWallTab() {
    return [
      Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            'WORD WALL FOR THIS BOOK',
            style: Theme.of(context).textTheme.labelSmall,
          ),
          ElevatedButton.icon(
            onPressed: _showAddWordDialog,
            icon: const Icon(Icons.add, size: 14),
            label: const Text('Add Word'),
            style: ElevatedButton.styleFrom(
              backgroundColor: ClassicLitTheme.oxbloodPrimary,
              foregroundColor: ClassicLitTheme.inkOnPrimary,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              textStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
            ),
          ),
        ],
      ),
      const SizedBox(height: 12),
      if (_words.isEmpty)
        const PaperCard(
          child: Padding(
            padding: EdgeInsets.all(20),
            child: Column(
              children: [
                Icon(
                  Icons.menu_book,
                  size: 36,
                  color: ClassicLitTheme.inkSecondary,
                ),
                SizedBox(height: 8),
                Text(
                  'No words in this book\'s Word Wall yet.',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                SizedBox(height: 4),
                Text(
                  'Tap "Add Word" above or "Word Wall" in the Reader while reading to save definitions and quotes.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
              ],
            ),
          ),
        )
      else
        ..._words.map((w) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: PaperCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        w.word,
                        style: const TextStyle(
                          fontFamily: ClassicLitTheme.serifFont,
                          fontWeight: FontWeight.w700,
                          fontSize: 16,
                          color: ClassicLitTheme.oxbloodPrimary,
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.delete_outline, size: 18),
                        color: ClassicLitTheme.inkSecondary,
                        visualDensity: VisualDensity.compact,
                        tooltip: 'Delete word',
                        onPressed: () => _deleteWord(w.id),
                      ),
                    ],
                  ),
                  if (w.meaning != null && w.meaning!.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      w.meaning!,
                      style: const TextStyle(fontSize: 13, height: 1.4),
                    ),
                  ],
                  if (w.quote != null && w.quote!.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(8),
                      decoration: const BoxDecoration(
                        color: ClassicLitTheme.elevatedPaper,
                        border: Border(
                          left: BorderSide(
                            color: ClassicLitTheme.libraryGreen,
                            width: 2.5,
                          ),
                        ),
                      ),
                      child: Text(
                        '"${w.quote}"',
                        style: const TextStyle(
                          fontSize: 11.5,
                          fontStyle: FontStyle.italic,
                          color: ClassicLitTheme.libraryGreen,
                        ),
                      ),
                    ),
                  ],
                  if (w.sourceLocation != null &&
                      w.sourceLocation!.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      'Found on ${w.sourceLocation}',
                      style: const TextStyle(
                        fontSize: 11,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          );
        }),
    ];
  }

  List<Widget> _buildAchievementsTab() {
    final achievements = _achievements?.achievements ?? [];
    final currentStreak = _achievements?.currentStreak ?? 0;
    final longestStreak = _achievements?.longestStreak ?? 0;

    return [
      PaperCard(
        backgroundColor: ClassicLitTheme.goldHighlightWash,
        child: Row(
          children: [
            const Icon(
              Icons.emoji_events_outlined,
              size: 32,
              color: ClassicLitTheme.oxbloodPrimary,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Literary Milestones',
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: ClassicLitTheme.inkPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Current Streak: $currentStreak days • Longest: $longestStreak days',
                    style: const TextStyle(
                      fontSize: 12,
                      color: ClassicLitTheme.inkSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      const SizedBox(height: 14),
      Text(
        'ALL ACHIEVEMENTS',
        style: Theme.of(context).textTheme.labelSmall,
      ),
      const SizedBox(height: 10),
      ...achievements.map((ach) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: PaperCard(
            backgroundColor: ach.unlocked
                ? ClassicLitTheme.elevatedPaper
                : ClassicLitTheme.linenCard.withValues(alpha: 0.6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: ach.unlocked
                        ? ClassicLitTheme.oxbloodPrimary
                        : ClassicLitTheme.deckleBorder,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    ach.unlocked ? Icons.military_tech : Icons.lock_outline,
                    size: 22,
                    color: ClassicLitTheme.inkOnPrimary,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Text(
                              ach.label,
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 13.5,
                                color: ach.unlocked
                                    ? ClassicLitTheme.inkPrimary
                                    : ClassicLitTheme.inkSecondary,
                              ),
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: ach.unlocked
                                  ? ClassicLitTheme.libraryGreen.withValues(alpha: 0.15)
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(3),
                              border: Border.all(
                                color: ach.unlocked
                                    ? ClassicLitTheme.libraryGreen
                                    : ClassicLitTheme.deckleBorder,
                              ),
                            ),
                            child: Text(
                              ach.unlocked ? 'UNLOCKED' : 'LOCKED',
                              style: TextStyle(
                                fontSize: 9.5,
                                fontWeight: FontWeight.w700,
                                color: ach.unlocked
                                    ? ClassicLitTheme.libraryGreen
                                    : ClassicLitTheme.inkSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        ach.description,
                        style: const TextStyle(
                          fontSize: 12,
                          color: ClassicLitTheme.inkSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      }),
    ];
  }

  List<Widget> _buildReadingLogTab() {
    final days = _readingLog?.days ?? [];
    return [
      Text(
        'READING LOG HISTORY',
        style: Theme.of(context).textTheme.labelSmall,
      ),
      const SizedBox(height: 10),
      if (days.isEmpty)
        const PaperCard(
          child: Padding(
            padding: EdgeInsets.all(20),
            child: Text(
              'No reading activity recorded yet. As you turn pages in the Reader, daily progress is saved automatically.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12,
                color: ClassicLitTheme.inkSecondary,
                fontStyle: FontStyle.italic,
              ),
            ),
          ),
        )
      else
        ...days.map((entry) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: PaperCard(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        entry.bookTitle,
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          color: ClassicLitTheme.inkPrimary,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        entry.currentChapter != null
                            ? 'Chapter ${entry.currentChapter}'
                            : 'Page ${entry.currentPage ?? 0}',
                        style: const TextStyle(
                          fontSize: 11.5,
                          color: ClassicLitTheme.inkSecondary,
                        ),
                      ),
                    ],
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: ClassicLitTheme.elevatedPaper,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(color: ClassicLitTheme.deckleBorder),
                    ),
                    child: Text(
                      entry.date,
                      style: const TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w600,
                        color: ClassicLitTheme.oxbloodPrimary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        }),
    ];
  }
}
