import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'api_client.dart';

// Not final so tests can swap in an ApiClient backed by a fake server.
ApiClient api = ApiClient();

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
  // Null until the backend's parser knows the real page count.
  final int? totalPages;
  final double? percentComplete;
  final String processingStatus;
  final Color spineColor;

  const BookItem({
    required this.id,
    required this.title,
    required this.author,
    required this.currentChapter,
    required this.currentPage,
    required this.totalPages,
    required this.spineColor,
    this.percentComplete,
    this.processingStatus = 'ready',
  });

  static const List<Color> _spinePalette = [
    ClassicLitTheme.oxbloodPrimary,
    ClassicLitTheme.libraryGreen,
    Color(0xFF4A3B32),
    Color(0xFF5B3246),
  ];

  factory BookItem.fromApi(ApiBook b) => BookItem(
    id: b.id,
    title: b.title,
    author: b.author ?? 'Unknown author',
    currentChapter: b.currentChapter ?? 1,
    currentPage: b.currentPage ?? 0,
    totalPages: b.totalPages,
    percentComplete: b.percentComplete,
    processingStatus: b.processingStatus,
    spineColor:
        _spinePalette[b.id.hashCode.abs() % _spinePalette.length],
  );

  BookItem copyWith({int? currentPage, double? percentComplete}) => BookItem(
    id: id,
    title: title,
    author: author,
    currentChapter: currentChapter,
    currentPage: currentPage ?? this.currentPage,
    totalPages: totalPages,
    percentComplete: percentComplete ?? this.percentComplete,
    processingStatus: processingStatus,
    spineColor: spineColor,
  );

  bool get isProcessed => processingStatus == 'ready';

  double get progress {
    if (percentComplete != null) return (percentComplete! / 100).clamp(0, 1).toDouble();
    final total = totalPages;
    if (total == null || total == 0) return 0;
    return (currentPage / total).clamp(0, 1).toDouble();
  }

  int get progressPercent => (progress * 100).round();
  String get pagesLabel => 'p. $currentPage / ${totalPages ?? '?'}';
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

  List<BookItem> _books = [];
  String? _activeBookId;
  bool _loading = true;
  bool _uploading = false;
  String? _error;

  BookItem? get _activeBook {
    if (_books.isEmpty) return null;
    return _books.firstWhere(
      (b) => b.id == _activeBookId,
      orElse: () => _books.first,
    );
  }

  @override
  void initState() {
    super.initState();
    _loadBooks();
  }

  Future<void> _loadBooks() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final apiBooks = await api.listBooks();
      setState(() {
        _books = apiBooks.map(BookItem.fromApi).toList();
        _loading = false;
      });
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  void _showSnack(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _uploadBook() async {
        final file = await FilePicker.pickFile(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'epub'],
    );
    if (file == null) return; // user cancelled

    setState(() => _uploading = true);
    try {
      final bytes = await file.readAsBytes();
      final uploaded = await api.uploadBook(
        bytes: bytes,
        filename: file.name,
        title: file.name.replaceAll(RegExp(r'\.(pdf|epub)$', caseSensitive: false), ''),
      );
      _activeBookId = uploaded.id;
      await _loadBooks();
      _showSnack('Uploaded "${uploaded.title}"');
    } on ApiException catch (e) {
      _showSnack('Upload failed: ${e.message}');
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  void _selectBook(String id) {
    setState(() => _activeBookId = id);
    _navigateToTab(1);
  }

  Future<void> _changePage(int delta) async {
    final book = _activeBook;
    if (book == null) return;
    final newPage = (book.currentPage + delta).clamp(0, book.totalPages ?? 1 << 30).toInt();
    final total = book.totalPages;
    final percent = (total != null && total > 0) ? newPage / total * 100 : null;

    // Optimistic update so the UI feels instant; reverted on failure.
    final before = _books;
    setState(() {
      _books = _books
          .map((b) => b.id == book.id
              ? b.copyWith(currentPage: newPage, percentComplete: percent)
              : b)
          .toList();
    });
    try {
      await api.updateProgress(
        book.id,
        currentPage: newPage,
        percentComplete: percent,
      );
    } on ApiException catch (e) {
      setState(() => _books = before);
      _showSnack('Could not save progress: ${e.message}');
    }
  }

  void _navigateToTab(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  Widget _needsBook(Widget Function(BookItem book) builder) {
    final book = _activeBook;
    if (book != null) return builder(book);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.menu_book_outlined,
              size: 40,
              color: ClassicLitTheme.inkSecondary,
            ),
            const SizedBox(height: 12),
            const Text(
              'Upload a book in the Library tab to get started.',
              textAlign: TextAlign.center,
              style: TextStyle(color: ClassicLitTheme.inkSecondary),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: () => _navigateToTab(0),
              child: const Text('Go to Library'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> screens = [
      LibraryScreen(
        activeBook: _activeBook,
        libraryBooks: _books,
        isLoading: _loading,
        isUploading: _uploading,
        error: _error,
        onRetry: _loadBooks,
        onUploadTap: _uploadBook,
        onBookTap: _selectBook,
        onResumeTap: () => _navigateToTab(1),
      ),
      _needsBook(
        (book) => ReaderScreen(
          book: book,
          onBackTap: () => _navigateToTab(0),
          onAskAiTap: () => _navigateToTab(2),
          onVisualizeTap: () => _navigateToTab(3),
          onPageChange: _changePage,
        ),
      ),
      _needsBook((book) => AskAiScreen(book: book)),
      _needsBook((book) => VisualizeScreen(book: book)),
      _needsBook((book) => ProgressScreen(book: book)),
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

class LibraryScreen extends StatelessWidget {
  final BookItem? activeBook;
  final List<BookItem> libraryBooks;
  final bool isLoading;
  final bool isUploading;
  final String? error;
  final VoidCallback onRetry;
  final VoidCallback onUploadTap;
  final ValueChanged<String> onBookTap;
  final VoidCallback onResumeTap;

  const LibraryScreen({
    super.key,
    required this.activeBook,
    required this.libraryBooks,
    required this.isLoading,
    required this.isUploading,
    required this.error,
    required this.onRetry,
    required this.onUploadTap,
    required this.onBookTap,
    required this.onResumeTap,
  });

  Widget _buildBody(BuildContext context) {
    if (isLoading) {
      return const Center(
        child: CircularProgressIndicator(color: ClassicLitTheme.oxbloodPrimary),
      );
    }
    if (error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 36, color: ClassicLitTheme.oxbloodPrimary),
              const SizedBox(height: 10),
              Text(error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    final book = activeBook;
    if (book == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'No books yet. Tap Upload to add a PDF or EPUB.',
            textAlign: TextAlign.center,
            style: TextStyle(color: ClassicLitTheme.inkSecondary),
          ),
        ),
      );
    }
    return _buildLibrary(context, book);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Top Header Bar
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
                'My Library',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              OutlinedButton.icon(
                onPressed: isUploading ? null : onUploadTap,
                icon: isUploading
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.add, size: 16),
                label: Text(isUploading ? 'Uploading…' : 'Upload'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: ClassicLitTheme.inkPrimary,
                  side: const BorderSide(
                    color: ClassicLitTheme.inkPrimary,
                    width: 1.2,
                  ),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
            ],
          ),
        ),

        // Scrollable Body
        Expanded(child: _buildBody(context)),
      ],
    );
  }

  Widget _buildLibrary(BuildContext context, BookItem activeBook) {
    return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'CONTINUE READING',
                style: Theme.of(context).textTheme.labelSmall,
              ),
              const SizedBox(height: 8),

              // Active Book Card
              PaperCard(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    BookCoverThumbnail(
                      title: activeBook.title,
                      spineColor: activeBook.spineColor,
                      width: 72,
                      height: 106,
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            activeBook.title,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${activeBook.author} • Ch. ${activeBook.currentChapter}',
                            style: const TextStyle(
                              fontSize: 12,
                              color: ClassicLitTheme.inkSecondary,
                            ),
                          ),
                          const SizedBox(height: 10),
                          VintageProgressBar(value: activeBook.progress),
                          const SizedBox(height: 6),
                          Text(
                            '${activeBook.progressPercent}% • ${activeBook.pagesLabel}',
                            style: const TextStyle(
                              fontSize: 11,
                              color: ClassicLitTheme.inkSecondary,
                            ),
                          ),
                          const SizedBox(height: 10),
                          SizedBox(
                            width: double.infinity,
                            height: 36,
                            child: ElevatedButton(
                              onPressed: onResumeTap,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: ClassicLitTheme.oxbloodPrimary,
                                foregroundColor: ClassicLitTheme.inkOnPrimary,
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(4),
                                ),
                              ),
                              child: const Text(
                                'Resume',
                                style: TextStyle(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 14),

              // Ingestion status card: only shown while the book isn't
              // processed. Status text comes straight from the backend.
              if (!activeBook.isProcessed)
                PaperCard(
                  backgroundColor: ClassicLitTheme.elevatedPaper,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '"${activeBook.title}" is ${activeBook.processingStatus}',
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'Text parsing and the knowledge graph aren\'t connected yet, so AI answers are placeholders for now.',
                        style: TextStyle(
                          fontSize: 11,
                          color: ClassicLitTheme.inkSecondary,
                        ),
                      ),
                    ],
                  ),
                ),

              const SizedBox(height: 20),
              Text('YOUR BOOKS', style: Theme.of(context).textTheme.labelSmall),
              const SizedBox(height: 10),

              // 3-Column Book Grid (wraps onto new rows as books are added)
              GridView.count(
                crossAxisCount: 3,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 8,
                mainAxisSpacing: 8,
                childAspectRatio: 0.62,
                children: libraryBooks.map((book) {
                  final isActive = book.id == activeBook.id;
                  return GestureDetector(
                    onTap: () => onBookTap(book.id),
                    child: Container(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: isActive
                              ? ClassicLitTheme.antiqueGold
                              : Colors.transparent,
                          width: 2,
                        ),
                      ),
                      child: BookCoverThumbnail(
                        title: book.title,
                        spineColor: book.spineColor,
                        width: double.infinity,
                        height: double.infinity,
                      ),
                    ),
                  );
                }).toList(),
              ),

              const SizedBox(height: 16),
              const Text(
                'Supports PDF and EPUB. Tap a book to open it.',
                style: TextStyle(
                  fontSize: 11,
                  color: ClassicLitTheme.inkSecondary,
                  height: 1.4,
                ),
              ),
            ],
    );
  }
}

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
      setState(() => _activeExplanation = 'Couldn\'t get an explanation: ${e.message}');
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

class AskAiScreen extends StatefulWidget {
  final BookItem book;

  const AskAiScreen({super.key, required this.book});

  @override
  State<AskAiScreen> createState() => _AskAiScreenState();
}

class _AskAiScreenState extends State<AskAiScreen> {
  int _selectedModeIndex = 0;
  final TextEditingController _promptController = TextEditingController();

  static const List<String> _modes = ['study', 'research', 'creative'];

  final List<ChatMessage> _messages = [];
  String? _conversationId;
  bool _sending = false;

  @override
  void didUpdateWidget(covariant AskAiScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    // New book, new conversation: the backend rejects a conversation_id
    // that belongs to a different book.
    if (oldWidget.book.id != widget.book.id) {
      _messages.clear();
      _conversationId = null;
    }
  }

  Future<void> _handleSend() async {
    final text = _promptController.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() {
      _messages.add(ChatMessage(text: text, isUser: true));
      _promptController.clear();
      _sending = true;
    });

    final lower = text.toLowerCase();
    final interactionType = lower.startsWith('what if')
        ? 'what_if'
        : (lower.startsWith('what happens next') ? 'story_continues' : 'question');

    try {
      final result = await api.chat(
        bookId: widget.book.id,
        conversationId: _conversationId,
        question: text,
        mode: _modes[_selectedModeIndex],
        interactionType: interactionType,
        currentPage: widget.book.currentPage,
        currentChapter: widget.book.currentChapter,
      );
      final notes = [
        if (result.isHypothetical) 'Hypothetical: not what happens in the book.',
        if (result.providerStatus == 'mock')
          'Mock AI: real retrieval isn\'t connected yet.',
      ];
      setState(() {
        _conversationId = result.conversationId;
        _messages.add(
          ChatMessage(
            text: result.answer,
            isUser: false,
            citations: result.citations,
            footerNote: notes.isEmpty ? null : notes.join(' '),
          ),
        );
      });
    } on ApiException catch (e) {
      setState(() {
        _messages.add(
          ChatMessage(text: 'Something went wrong: ${e.message}', isUser: false),
        );
      });
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  void dispose() {
    _promptController.dispose();
    super.dispose();
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
              Text('Ask AI', style: Theme.of(context).textTheme.headlineSmall),
              Text(
                widget.book.title,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: ClassicLitTheme.inkSecondary,
                ),
              ),
            ],
          ),
        ),

        // Mode Filter Pills + Chat History
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              FilterPillRow(
                options: const ['Study', 'Research', 'Creative'],
                selectedIndex: _selectedModeIndex,
                onSelected: (index) =>
                    setState(() => _selectedModeIndex = index),
              ),
              const SizedBox(height: 16),

              // Message Bubbles
              ..._messages.map((msg) => _buildChatBubble(msg)),

              if (_messages.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text(
                    'Ask anything about this book. Start with "What if…" for a hypothetical.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: ClassicLitTheme.inkSecondary),
                  ),
                ),

              // Retrieval Status Indicator Box (only while waiting)
              if (_sending)
              Align(
                alignment: Alignment.centerLeft,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 260),
                  child: const PaperCard(
                    backgroundColor: ClassicLitTheme.elevatedPaper,
                    padding: EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Retrieving from text...',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: ClassicLitTheme.inkSecondary,
                          ),
                        ),
                        SizedBox(height: 8),
                        VintageProgressBar(
                          value: 0.55,
                          fillColor: ClassicLitTheme.libraryGreen,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),

        // Bottom Grounded Prompt Composer
        Container(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          decoration: const BoxDecoration(
            color: ClassicLitTheme.parchmentBg,
            border: Border(
              top: BorderSide(color: ClassicLitTheme.deckleBorder),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Answers are limited to your uploaded book.',
                style: TextStyle(
                  fontSize: 11,
                  color: ClassicLitTheme.inkSecondary,
                ),
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 40,
                      child: TextField(
                        controller: _promptController,
                        onSubmitted: (_) => _handleSend(),
                        style: const TextStyle(fontSize: 13),
                        decoration: InputDecoration(
                          hintText: 'Ask about this book...',
                          hintStyle: const TextStyle(
                            fontSize: 13,
                            color: ClassicLitTheme.inkSecondary,
                          ),
                          filled: true,
                          fillColor: ClassicLitTheme.elevatedPaper,
                          contentPadding: const EdgeInsets.symmetric(
                            horizontal: 12,
                          ),
                          enabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(4),
                            borderSide: const BorderSide(
                              color: ClassicLitTheme.inkPrimary,
                            ),
                          ),
                          focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(4),
                            borderSide: const BorderSide(
                              color: ClassicLitTheme.oxbloodPrimary,
                              width: 1.5,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  SizedBox(
                    height: 40,
                    child: ElevatedButton(
                      onPressed: _handleSend,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: ClassicLitTheme.oxbloodPrimary,
                        foregroundColor: ClassicLitTheme.inkOnPrimary,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      child: const Text(
                        'Send',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildChatBubble(ChatMessage msg) {
    if (msg.isUser) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 12, left: 48),
        child: Align(
          alignment: Alignment.centerRight,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: ClassicLitTheme.elevatedPaper,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: ClassicLitTheme.inkPrimary, width: 1.1),
            ),
            child: Text(
              msg.text,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 12, right: 24),
      child: PaperCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(msg.text, style: const TextStyle(fontSize: 13.5, height: 1.5)),
            if (msg.citations.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                children: msg.citations.map((cite) {
                  return Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: ClassicLitTheme.elevatedPaper,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: ClassicLitTheme.libraryGreen),
                    ),
                    child: Text(
                      cite,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: ClassicLitTheme.libraryGreen,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
            if (msg.footerNote != null) ...[
              const SizedBox(height: 8),
              Text(
                msg.footerNote!,
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
  }
}

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
