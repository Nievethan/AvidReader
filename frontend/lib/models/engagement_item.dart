class ReadingLogDay {
  final String date; // "YYYY-MM-DD"
  final String bookId;
  final String bookTitle;
  final int? currentPage;
  final int? currentChapter;

  const ReadingLogDay({
    required this.date,
    required this.bookId,
    required this.bookTitle,
    this.currentPage,
    this.currentChapter,
  });

  factory ReadingLogDay.fromJson(Map<String, dynamic> json) => ReadingLogDay(
        date: json['date'] as String,
        bookId: json['book_id'] as String,
        bookTitle: (json['book_title'] as String?) ?? 'Untitled Book',
        currentPage: json['current_page'] as int?,
        currentChapter: json['current_chapter'] as int?,
      );

  Map<String, dynamic> toJson() => {
        'date': date,
        'book_id': bookId,
        'book_title': bookTitle,
        'current_page': currentPage,
        'current_chapter': currentChapter,
      };
}

class ReadingLogResult {
  final List<ReadingLogDay> days;
  final int currentStreak;
  final int longestStreak;

  const ReadingLogResult({
    required this.days,
    required this.currentStreak,
    required this.longestStreak,
  });

  factory ReadingLogResult.fromJson(Map<String, dynamic> json) =>
      ReadingLogResult(
        days: (json['days'] as List? ?? [])
            .map((d) =>
                ReadingLogDay.fromJson((d as Map).cast<String, dynamic>()))
            .toList(),
        currentStreak: (json['current_streak'] as int?) ?? 0,
        longestStreak: (json['longest_streak'] as int?) ?? 0,
      );
}

class AchievementItem {
  final String id;
  final String label;
  final String description;
  final bool unlocked;

  const AchievementItem({
    required this.id,
    required this.label,
    required this.description,
    required this.unlocked,
  });

  factory AchievementItem.fromJson(Map<String, dynamic> json) =>
      AchievementItem(
        id: json['id'] as String,
        label: (json['label'] as String?) ?? '',
        description: (json['description'] as String?) ?? '',
        unlocked: (json['unlocked'] as bool?) ?? false,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'label': label,
        'description': description,
        'unlocked': unlocked,
      };
}

class AchievementsResult {
  final List<AchievementItem> achievements;
  final int currentStreak;
  final int longestStreak;

  const AchievementsResult({
    required this.achievements,
    required this.currentStreak,
    required this.longestStreak,
  });

  factory AchievementsResult.fromJson(Map<String, dynamic> json) =>
      AchievementsResult(
        achievements: (json['achievements'] as List? ?? [])
            .map((a) =>
                AchievementItem.fromJson((a as Map).cast<String, dynamic>()))
            .toList(),
        currentStreak: (json['current_streak'] as int?) ?? 0,
        longestStreak: (json['longest_streak'] as int?) ?? 0,
      );
}
