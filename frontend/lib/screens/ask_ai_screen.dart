import 'package:flutter/material.dart';
import 'package:frontend/main.dart';

import '../models/book_item.dart';
import '../models/chat_message.dart';
import '../theme/classic_lit_theme.dart';
import '../widgets/filter_pill_row.dart';
import '../widgets/paper_card.dart';
import '../widgets/vintage_progress_bar.dart';
import '../api_client.dart';

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
        : (lower.startsWith('what happens next')
              ? 'story_continues'
              : 'question');

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
        if (result.isHypothetical)
          'Hypothetical: not what happens in the book.',
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
          ChatMessage(
            text: 'Something went wrong: ${e.message}',
            isUser: false,
          ),
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
