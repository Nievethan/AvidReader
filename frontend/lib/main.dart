import 'package:flutter/material.dart';

import 'theme/classic_lit_theme.dart';
import 'screens/reading_dashboard_shell.dart';
import 'api_client.dart';

export 'screens/reading_dashboard_shell.dart';
export 'screens/library_screen.dart';
export 'screens/reader_screen.dart';
export 'screens/ask_ai_screen.dart';
export 'screens/visualize_screen.dart';
export 'screens/progress_screen.dart';

// Not final so tests can swap in an ApiClient backed by a fake server.
ApiClient api = ApiClient();

void main() {
  runApp(const AvidReaderApp());
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
