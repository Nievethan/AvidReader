import 'package:flutter/material.dart';
import 'package:frontend/theme/classic_lit_theme.dart';
import 'package:frontend/widgets/book_cover_thumbnail.dart';
import 'package:frontend/widgets/paper_card.dart';
import 'package:frontend/widgets/vintage_progress_bar.dart';
import 'package:frontend/models/book_item.dart';

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
              const Icon(
                Icons.cloud_off,
                size: 36,
                color: ClassicLitTheme.oxbloodPrimary,
              ),
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
        Text('CONTINUE READING', style: Theme.of(context).textTheme.labelSmall),
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
                Text(
                  switch (activeBook.processingStatus) {
                    'failed' => 'Indexing failed. Try uploading it again.',
                    'unsupported' =>
                      'This file format isn\'t supported for AI features yet.',
                    _ => 'Indexing this book for AI features — usually just a few seconds.',
                  },
                  style: const TextStyle(
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
