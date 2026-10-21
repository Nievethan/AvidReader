import 'package:device_preview/device_preview.dart';
import 'package:device_preview/presets.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

void main() {
  runApp(const AvidReaderApp());
}

class ClassicLitTheme {
  // Core Palette: Inspired by Oxford libraries, aged parchment, and leather bindings
  static const Color parchmentBg = Color(0xFFF6F1E7); // Warm cream paper
  static const Color linenCard = Color(0xFFEFE8D8); // Pressed rag paper surface
  static const Color elevatedPaper = Color(
    0xFFFAF7F0,
  ); // Lighter highlight sheet
  static const Color deckleBorder = Color(0xFFD5C7B2); // Muted bookplate rule

  // Brand & Accent Colors
  static const Color oxbloodPrimary = Color(
    0xFF6E262E,
  ); // Moroccan leather burgundy
  static const Color libraryGreen = Color(0xFF2D4A3E); // Banker's lamp green
  static const Color antiqueGold = Color(
    0xFFC59B27,
  ); // Gilded page edge highlight
  static const Color goldHighlightWash = Color(
    0x33C59B27,
  ); // 20% translucent gold

  // Typography Ink Colors (WCAG AAA/AA contrast against parchmentBg)
  static const Color inkPrimary = Color(0xFF231F1D); // Iron gall dark charcoal
  static const Color inkSecondary = Color(0xFF645951); // Aged sepia subtext
  static const Color inkOnPrimary = Color(
    0xFFFDFBF7,
  ); // Cream text on dark buttons

  static const String serifFont = 'Georgia';

  static ThemeData get themeData {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: parchmentBg,
      colorScheme: const ColorScheme.light(
        primary: oxbloodPrimary,
        onPrimary: inkOnPrimary,
        secondary: libraryGreen,
        onSecondary: inkOnPrimary,
        surface: parchmentBg,
        onSurface: inkPrimary,
        outline: deckleBorder,
      ),
      fontFamily: serifFont,
      textTheme: const TextTheme(
        headlineSmall: TextStyle(
          fontFamily: serifFont,
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: inkPrimary,
          letterSpacing: -0.2,
        ),
        titleMedium: TextStyle(
          fontFamily: serifFont,
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: inkPrimary,
        ),
        bodyLarge: TextStyle(
          fontFamily: serifFont,
          fontSize: 16,
          height: 1.65,
          color: inkPrimary,
        ),
        bodyMedium: TextStyle(fontSize: 14, height: 1.45, color: inkPrimary),
        labelSmall: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.8,
          color: inkSecondary,
        ),
      ),
      dividerColor: deckleBorder,
    );
  }
}

class BookItem {
  final String id;
  final String title;
  final String author;
  final int currentChapter;
  final int currentPage;
  final int totalPages;
  final Color spineColor;

  const BookItem({
    required this.id,
    required this.title,
    required this.author,
    required this.currentChapter,
    required this.currentPage,
    required this.totalPages,
    required this.spineColor,
  });

  double get progress => currentPage / totalPages;
  int get progressPercent => (progress * 100).round();
}

class ChatMessage {
  final String text;
  final bool isUser;
  final List<String> citations;
  final String? footerNote;

  const ChatMessage({
    required this.text,
    required this.isUser,
    this.citations = const [],
    this.footerNote,
  });
}

class CharacterVisual {
  final String name;
  final String role;
  final String description;
  final List<String> citations;
  final IconData icon;

  const CharacterVisual({
    required this.name,
    required this.role,
    required this.description,
    required this.citations,
    required this.icon,
  });
}

class PaperCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color backgroundColor;

  const PaperCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(14),
    this.backgroundColor = ClassicLitTheme.linenCard,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: ClassicLitTheme.deckleBorder, width: 1.2),
      ),
      child: child,
    );
  }
}

class VintageProgressBar extends StatelessWidget {
  final double value; // 0.0 to 1.0
  final Color fillColor;
  final double height;

  const VintageProgressBar({
    super.key,
    required this.value,
    this.fillColor = ClassicLitTheme.oxbloodPrimary,
    this.height = 8,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      width: double.infinity,
      decoration: BoxDecoration(
        color: ClassicLitTheme.elevatedPaper,
        borderRadius: BorderRadius.circular(3),
        border: Border.all(color: ClassicLitTheme.deckleBorder),
      ),
      child: FractionallySizedBox(
        alignment: Alignment.centerLeft,
        widthFactor: value.clamp(0.0, 1.0),
        child: Container(
          decoration: BoxDecoration(
            color: fillColor,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      ),
    );
  }
}

class FilterPillRow extends StatelessWidget {
  final List<String> options;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  const FilterPillRow({
    super.key,
    required this.options,
    required this.selectedIndex,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      children: List.generate(options.length, (index) {
        final isSelected = index == selectedIndex;
        return GestureDetector(
          onTap: () => onSelected(index),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(
              color: isSelected
                  ? ClassicLitTheme.oxbloodPrimary
                  : ClassicLitTheme.elevatedPaper,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: isSelected
                    ? ClassicLitTheme.oxbloodPrimary
                    : ClassicLitTheme.deckleBorder,
                width: 1.2,
              ),
            ),
            child: Text(
              options[index],
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: isSelected
                    ? ClassicLitTheme.inkOnPrimary
                    : ClassicLitTheme.inkPrimary,
              ),
            ),
          ),
        );
      }),
    );
  }
}

class BookCoverThumbnail extends StatelessWidget {
  final String title;
  final Color spineColor;
  final double width;
  final double height;

  const BookCoverThumbnail({
    super.key,
    required this.title,
    this.spineColor = ClassicLitTheme.oxbloodPrimary,
    this.width = 68,
    this.height = 96,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: ClassicLitTheme.elevatedPaper,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: ClassicLitTheme.deckleBorder, width: 1.2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 3,
            offset: const Offset(1, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: double.infinity,
            decoration: BoxDecoration(
              color: spineColor,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(3),
                bottomLeft: Radius.circular(3),
              ),
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(6),
              child: Center(
                child: Text(
                  title,
                  textAlign: TextAlign.center,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: ClassicLitTheme.serifFont,
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AvidReaderApp extends StatelessWidget {
  const AvidReaderApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AvidReader',
      debugShowCheckedModeBanner: false,
      theme: ClassicLitTheme.themeData,
      home: const ReadingDashboardShell(),
    );
  }
}

class ReadingDashboardShell extends StatefulWidget {
  const ReadingDashboardShell({super.key});

  @override
  State<ReadingDashboardShell> createState() => _ReadingDashboardShellState();
}

class _ReadingDashboardShellState extends State<ReadingDashboardShell> {
  int _selectedIndex = 0;

  final BookItem _activeBook = const BookItem(
    id: 'book-1',
    title: 'Crime and Punishment',
    author: 'Fyodor Dostoevsky',
    currentChapter: 7,
    currentPage: 112,
    totalPages: 320,
    spineColor: ClassicLitTheme.oxbloodPrimary,
  );

  final List<BookItem> _libraryBooks = const [
    BookItem(
      id: 'book-2',
      title: 'Jane Eyre',
      author: 'Charlotte Brontë',
      currentChapter: 4,
      currentPage: 64,
      totalPages: 410,
      spineColor: ClassicLitTheme.libraryGreen,
    ),
    BookItem(
      id: 'book-3',
      title: 'The Odyssey',
      author: 'Homer',
      currentChapter: 1,
      currentPage: 12,
      totalPages: 380,
      spineColor: Color(0xFF4A3B32),
    ),
    BookItem(
      id: 'book-4',
      title: 'Middlemarch',
      author: 'George Eliot',
      currentChapter: 12,
      currentPage: 215,
      totalPages: 520,
      spineColor: Color(0xFF5B3246),
    ),
  ];

  void _navigateToTab(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    // In Commit 3, tabs use temporary placeholders that we replace in Commits 4–7
    final List<Widget> screens = [
      const Center(child: Text('1. Library Screen Placeholder')),
      const Center(child: Text('2. Reader Screen Placeholder')),
      const Center(child: Text('3. Ask AI Screen Placeholder')),
      const Center(child: Text('4. Visualize Screen Placeholder')),
      const Center(child: Text('5. Progress Screen Placeholder')),
    ];

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: IndexedStack(index: _selectedIndex, children: screens),
          ),
        ),
      ),
      bottomNavigationBar: _buildBottomNavBar(),
    );
  }

  Widget _buildBottomNavBar() {
    const items = [
      (
        icon: Icons.local_library_outlined,
        activeIcon: Icons.local_library,
        label: 'Library',
      ),
      (
        icon: Icons.menu_book_outlined,
        activeIcon: Icons.menu_book,
        label: 'Reader',
      ),
      (
        icon: Icons.auto_awesome_outlined,
        activeIcon: Icons.auto_awesome,
        label: 'Ask AI',
      ),
      (
        icon: Icons.palette_outlined,
        activeIcon: Icons.palette,
        label: 'Visualize',
      ),
      (
        icon: Icons.insights_outlined,
        activeIcon: Icons.insights,
        label: 'Progress',
      ),
    ];

    return Container(
      decoration: const BoxDecoration(
        color: ClassicLitTheme.linenCard,
        border: Border(
          top: BorderSide(color: ClassicLitTheme.deckleBorder, width: 1.2),
        ),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 62,
          child: Row(
            children: List.generate(items.length, (index) {
              final item = items[index];
              final isSelected = _selectedIndex == index;
              return Expanded(
                child: InkWell(
                  onTap: () => _navigateToTab(index),
                  child: Container(
                    color: isSelected
                        ? ClassicLitTheme.oxbloodPrimary.withValues(alpha: 0.10)
                        : Colors.transparent,
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          isSelected ? item.activeIcon : item.icon,
                          size: 20,
                          color: isSelected
                              ? ClassicLitTheme.oxbloodPrimary
                              : ClassicLitTheme.inkSecondary,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          item.label,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: isSelected
                                ? FontWeight.w700
                                : FontWeight.w500,
                            color: isSelected
                                ? ClassicLitTheme.oxbloodPrimary
                                : ClassicLitTheme.inkSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            }),
          ),
        ),
      ),
    );
  }
}
