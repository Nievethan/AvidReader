import 'dart:async';

import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';

import '../main.dart';

import '../models/book_item.dart';
import '../theme/classic_lit_theme.dart';
import '../api_client.dart';

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
  Timer? _ingestionPollTimer;

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
    _ingestionPollTimer?.cancel();
    super.dispose();
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

  // The book list isn't re-fetched on its own once ingestion finishes in the
  // background, so without this the Library/Reader keep showing
  // "processing" forever even after the real status has moved on.
  void _pollIngestion(String bookId) {
    _ingestionPollTimer?.cancel();
    _ingestionPollTimer = Timer(const Duration(seconds: 2), () async {
      try {
        final status = await api.getIngestionStatus(bookId);
        if (!mounted) return;
        if (status.status == 'processing') {
          _pollIngestion(bookId);
        } else {
          await _loadBooks();
        }
      } on ApiException {
        // Give up quietly; the user can still pull-to-refresh via onRetry.
      }
    });
  }

  void _selectBook(String id) {
    setState(() => _activeBookId = id);
    _navigateToTab(1);
  }

  Future<void> _changePage(int delta) async {
    final book = _activeBook;
    if (book == null) return;
    final total = book.totalPages;
    // currentPage is 0-based, and /content only has pages 1..totalPages,
    // so the last valid 0-based page is (totalPages - 1).
    final maxPage = (total != null && total > 0) ? total - 1 : 1 << 30;
    final newPage = (book.currentPage + delta).clamp(0, maxPage).toInt();
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
