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
