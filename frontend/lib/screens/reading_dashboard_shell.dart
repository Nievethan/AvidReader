import 'dart:async';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';
import '../models/book_item.dart';
import '../services/file_selector_service.dart';
import '../theme/classic_lit_theme.dart';

class ReadingDashboardShell extends StatefulWidget {
  const ReadingDashboardShell({super.key});

  @override
  State<ReadingDashboardShell> createState() => _ReadingDashboardShellState();
}

class _ReadingDashboardShellState extends State<ReadingDashboardShell> {
  int _selectedIndex = 0;
  // Which dashboard-level tab is showing while _selectedIndex == 0: 0 =
  // Library (book list), 1 = Reading Journey (Achievements + Reading Log).
  // A separate index because these are a different nav bar from the
  // per-book tabs, not additional entries in that one.
  int _dashboardTabIndex = 0;

  List<BookItem> _books = [];
  String? _activeBookId;
  bool _loading = true;
  bool _uploading = false;
  String? _error;
  final Map<String, Timer> _pollTimers = {};

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

  @override
  void dispose() {
    for (final timer in _pollTimers.values) {
      timer.cancel();
    }
    super.dispose();
  }

  // Covers every book still "processing", not just the one just uploaded:
  // otherwise a refresh (or a second session) while a book is mid-ingestion
  // leaves its Library badge stuck forever since nothing restarts polling.
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
      for (final book in _books) {
        if (book.processingStatus == 'processing' &&
            !_pollTimers.containsKey(book.id)) {
          _pollIngestion(book.id);
        }
      }
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

  Future<void> _processSelectedFile(SelectedFile file) async {
    setState(() => _uploading = true);
    try {
      final uploaded = await api.uploadBook(
        bytes: file.bytes,
        filename: file.name,
        title: file.name.replaceAll(
          RegExp(r'\.(pdf|epub)$', caseSensitive: false),
          '',
        ),
      );
      _activeBookId = uploaded.id;
      await _loadBooks();
      _showSnack('Uploaded "${uploaded.title}"');
      _pollIngestion(uploaded.id);
    } on ApiException catch (e) {
      _showSnack('Upload failed: ${e.message}');
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _uploadBook() async {
    try {
      final file = await pickBookFile();
      if (file == null) return; // user cancelled
      await _processSelectedFile(file);
    } catch (e) {
      _showManualPathDialog(initialError: e.toString());
    }
  }

  void _showManualPathDialog({String? initialError}) {
    final controller = TextEditingController(
      text: '/home/nievethan/AvidReader/SplitPDF.pdf',
    );
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ClassicLitTheme.parchmentBg,
        title: const Text(
          'Select Book File',
          style: TextStyle(
            fontFamily: ClassicLitTheme.serifFont,
            fontWeight: FontWeight.w700,
            color: ClassicLitTheme.oxbloodPrimary,
          ),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Enter the absolute path to your PDF or EPUB file on disk:',
              style: TextStyle(fontSize: 12.5),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                labelText: 'File Path',
                hintText: '/path/to/book.pdf',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final path = controller.text.trim();
              if (path.isEmpty) return;
              Navigator.pop(ctx);
              try {
                final file = await loadFileFromPath(path);
                if (file != null) {
                  await _processSelectedFile(file);
                }
              } catch (err) {
                _showSnack('Could not load file: $err');
              }
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: ClassicLitTheme.oxbloodPrimary,
              foregroundColor: ClassicLitTheme.inkOnPrimary,
            ),
            child: const Text('Upload'),
          ),
        ],
      ),
    );
  }

  // The book list isn't re-fetched on its own once ingestion finishes in the
  // background, so without this the Library/Reader keep showing
  // "processing" forever even after the real status has moved on. Keyed by
  // book id so more than one book can be polled at once.
  void _pollIngestion(String bookId) {
    _pollTimers[bookId]?.cancel();
    _pollTimers[bookId] = Timer(const Duration(seconds: 2), () async {
      try {
        final status = await api.getIngestionStatus(bookId);
        if (!mounted) return;
        if (status.status == 'processing') {
          _pollIngestion(bookId);
        } else {
          _pollTimers.remove(bookId);
          await _loadBooks();
        }
      } on ApiException {
        // Give up quietly; the user can still pull-to-refresh via onRetry.
        _pollTimers.remove(bookId);
      }
    });
  }

  void _selectBook(String id) {
    setState(() => _activeBookId = id);
    _navigateToTab(1);
  }

  Future<void> _deleteBook(String bookId) async {
    try {
      await api.deleteBook(bookId);
      if (_activeBookId == bookId) {
        _activeBookId = null;
      }
      await _loadBooks();
      _showSnack('Book removed from library');
    } on ApiException catch (e) {
      _showSnack('Could not remove book: ${e.message}');
    }
  }

  Future<void> _setPage(int targetPage) async {
    final book = _activeBook;
    if (book == null) return;
    final total = book.totalPages;
    // currentPage is 0-based, and /content only has pages 1..totalPages,
    // so the last valid 0-based page is (totalPages - 1).
    final maxPage = (total != null && total > 0) ? total - 1 : 1 << 30;
    final newPage = targetPage.clamp(0, maxPage).toInt();
    final percent = (total != null && total > 0) ? newPage / total * 100 : null;

    // Optimistic update so the UI feels instant; reverted on failure.
    final before = _books;
    setState(() {
      _books = _books
          .map(
            (b) => b.id == book.id
                ? b.copyWith(currentPage: newPage, percentComplete: percent)
                : b,
          )
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

  Future<void> _changePage(int delta) async {
    final book = _activeBook;
    if (book == null) return;
    await _setPage(book.currentPage + delta);
  }

  // Jumps straight to a 0-based page instead of stepping by one, so the
  // reader isn't stuck clicking "Next" dozens of times to skip ahead.
  Future<void> _goToPage(int page) => _setPage(page);

  void _navigateToTab(int index) {
    setState(() {
      _selectedIndex = index;
      // Leaving book mode always lands back on the book list, not wherever
      // the dashboard tab happened to be left on.
      if (index == 0) _dashboardTabIndex = 0;
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
      IndexedStack(
        index: _dashboardTabIndex,
        children: [
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
            onDeleteTap: _deleteBook,
          ),
          const ReadingJourneyScreen(),
        ],
      ),
      _needsBook(
        (book) => ReaderScreen(
          book: book,
          onBackTap: () => _navigateToTab(0),
          onAskAiTap: () => _navigateToTab(2),
          onVisualizeTap: () => _navigateToTab(3),
          onPageChange: _changePage,
          onGoToPage: _goToPage,
        ),
      ),
      _needsBook((book) => AskAiScreen(
            book: book,
            onBackToReaderTap: () => _navigateToTab(1),
          )),
      _needsBook((book) => VisualizeScreen(
            book: book,
            onBackToReaderTap: () => _navigateToTab(1),
          )),
      _needsBook((book) => ProgressScreen(
            book: book,
            onBackToReaderTap: () => _navigateToTab(1),
          )),
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
      // Two different nav bars, never mixed into one list: the dashboard
      // bar (Library / Reading Journey) while no book is open, and the
      // book bar (Reader / Ask AI / Visualize / Progress + a Library exit)
      // once one is. Keeping them separate is the whole point -- Library
      // was never a peer of the book-view tabs, and Reading Journey is
      // cross-book data, so neither belongs mixed into the other bar.
      bottomNavigationBar:
          _selectedIndex == 0 ? _buildDashboardNavBar() : _buildBookNavBar(),
    );
  }

  Widget _buildDashboardNavBar() {
    const dashboardTabs = [
      (
        icon: Icons.local_library_outlined,
        activeIcon: Icons.local_library,
        label: 'Library',
      ),
      (
        icon: Icons.emoji_events_outlined,
        activeIcon: Icons.emoji_events,
        label: 'Journey',
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
            children: List.generate(dashboardTabs.length, (i) {
              final item = dashboardTabs[i];
              final isSelected = _dashboardTabIndex == i;
              return Expanded(
                child: InkWell(
                  onTap: () => setState(() => _dashboardTabIndex = i),
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

  Widget _buildBookNavBar() {
    const bookViewTabs = [
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
            children: [
              // Exits book mode entirely -- set apart from the tabs below
              // (divider, back-style icon) so it doesn't read as "just
              // another view of this book".
              InkWell(
                onTap: () => _navigateToTab(0),
                child: Container(
                  width: 68,
                  height: double.infinity,
                  decoration: const BoxDecoration(
                    border: Border(
                      right: BorderSide(
                        color: ClassicLitTheme.deckleBorder,
                        width: 1.2,
                      ),
                    ),
                  ),
                  child: const Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.arrow_back_ios_new,
                        size: 16,
                        color: ClassicLitTheme.oxbloodPrimary,
                      ),
                      SizedBox(height: 4),
                      Text(
                        'Library',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: ClassicLitTheme.oxbloodPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              ...List.generate(bookViewTabs.length, (i) {
                final tabIndex = i + 1; // tabs 1-4; 0 is Library
                final item = bookViewTabs[i];
                final isSelected = _selectedIndex == tabIndex;
                return Expanded(
                  child: InkWell(
                    onTap: () => _navigateToTab(tabIndex),
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
            ],
          ),
        ),
      ),
    );
  }
}
