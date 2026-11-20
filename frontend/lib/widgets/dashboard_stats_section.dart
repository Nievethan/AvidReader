import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';
import '../theme/classic_lit_theme.dart';
import 'paper_card.dart';
import 'vintage_progress_bar.dart';

/// Reading Log and Achievements are cross-book dashboard data (the backend
/// itself says so -- neither is scoped to one book), so they live here on
/// the Library screen instead of nested under a single book's "My
/// Progress" view, where showing every book's history inside what looks
/// like a per-book screen was actively misleading.
class DashboardStatsSection extends StatefulWidget {
  const DashboardStatsSection({super.key});

  @override
  State<DashboardStatsSection> createState() => _DashboardStatsSectionState();
}

class _DashboardStatsSectionState extends State<DashboardStatsSection> {
  bool _loading = true;
  String? _error;
  ReadingLogResult? _readingLog;
  AchievementsResult? _achievements;
  bool _showAllAchievements = false;
  bool _showAllLog = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        api.getReadingLog(),
        api.getAchievements(),
      ]);
      if (!mounted) return;
      setState(() {
        _readingLog = results[0] as ReadingLogResult;
        _achievements = results[1] as AchievementsResult;
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

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const PaperCard(
        child: SizedBox(
          height: 40,
          child: Center(
            child: SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: ClassicLitTheme.oxbloodPrimary,
              ),
            ),
          ),
        ),
      );
    }

    if (_error != null) {
      return PaperCard(
        child: Row(
          children: [
            const Icon(
              Icons.cloud_off,
              size: 18,
              color: ClassicLitTheme.oxbloodPrimary,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Could not load reading stats: $_error',
                style: const TextStyle(fontSize: 12),
              ),
            ),
            TextButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }

    final achievements = _achievements?.achievements ?? [];
    final unlocked = achievements.where((a) => a.unlocked).length;
    final days = _readingLog?.days ?? [];
    final streak = _readingLog?.currentStreak ?? 0;
    final longestStreak = _readingLog?.longestStreak ?? 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('YOUR READING JOURNEY', style: Theme.of(context).textTheme.labelSmall),
        const SizedBox(height: 8),

        // Achievements
        PaperCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.emoji_events_outlined,
                        size: 16,
                        color: ClassicLitTheme.oxbloodPrimary,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Achievements ($unlocked/${achievements.length})',
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.local_fire_department,
                        size: 15,
                        color: ClassicLitTheme.antiqueGold,
                      ),
                      const SizedBox(width: 3),
                      Text(
                        '$streak day streak (best: $longestStreak)',
                        style: const TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: ClassicLitTheme.inkSecondary,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 8),
              VintageProgressBar(
                value: achievements.isEmpty ? 0 : unlocked / achievements.length,
                fillColor: ClassicLitTheme.antiqueGold,
              ),
              const SizedBox(height: 10),
              ...(_showAllAchievements ? achievements : achievements.take(3))
                  .map((ach) => Padding(
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
                      )),
              if (achievements.length > 3)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => setState(
                      () => _showAllAchievements = !_showAllAchievements,
                    ),
                    child: Text(_showAllAchievements ? 'Show less' : 'Show all ›'),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 14),

        // Reading log
        PaperCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Reading Log',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
              ),
              const SizedBox(height: 8),
              if (days.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    'No reading activity recorded yet. As you turn pages in '
                    'the Reader, daily progress is saved automatically.',
                    style: TextStyle(
                      fontSize: 12,
                      color: ClassicLitTheme.inkSecondary,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                )
              else
                ...(_showAllLog ? days : days.take(5)).map((d) => Padding(
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
                          Flexible(
                            child: Text(
                              '${d.bookTitle} (p. ${d.currentPage ?? 0})',
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.right,
                              style: const TextStyle(
                                fontSize: 12,
                                color: ClassicLitTheme.inkSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                    )),
              if (days.length > 5)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => setState(() => _showAllLog = !_showAllLog),
                    child: Text(_showAllLog ? 'Show less' : 'Show all ›'),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
