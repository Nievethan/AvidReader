import 'package:flutter/material.dart';

import '../theme/classic_lit_theme.dart';
import '../widgets/dashboard_stats_section.dart';

/// Dashboard-level tab, a peer of Library rather than something buried
/// inside it -- Achievements and Reading Log are cross-book data, so they
/// get their own destination instead of competing for space on the book
/// list.
class ReadingJourneyScreen extends StatelessWidget {
  const ReadingJourneyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
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
                'Reading Journey',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const Icon(
                Icons.emoji_events_outlined,
                color: ClassicLitTheme.oxbloodPrimary,
              ),
            ],
          ),
        ),
        const Expanded(
          child: SingleChildScrollView(
            padding: EdgeInsets.all(16),
            child: DashboardStatsSection(),
          ),
        ),
      ],
    );
  }
}
