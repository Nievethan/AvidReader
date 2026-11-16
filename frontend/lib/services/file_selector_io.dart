import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'file_selector_stub.dart';

export 'file_selector_stub.dart';

Future<SelectedFile?> pickBookFile() async {
  // 1. Try standard FilePicker
  try {
    final file = await FilePicker.pickFile(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'epub'],
    );
    if (file != null) {
      final bytes = await file.readAsBytes();
      return SelectedFile(name: file.name, bytes: bytes);
    }
    return null; // User cancelled
  } catch (portalError) {
    // 2. Fallback on Linux: Try Zenity directly (common for WSLg / minimal Linux where XDG portal is absent)
    if (Platform.isLinux) {
      try {
        final res = await Process.run('zenity', [
          '--file-selection',
          '--title=Select Book (PDF or EPUB)',
          '--file-filter=Books (pdf, epub) | *.pdf *.epub *.PDF *.EPUB',
        ]);
        if (res.exitCode == 0) {
          final path = res.stdout.toString().trim();
          if (path.isNotEmpty) {
            final f = File(path);
            if (await f.exists()) {
              final bytes = await f.readAsBytes();
              final name = path.split(Platform.pathSeparator).last;
              return SelectedFile(name: name, bytes: bytes);
            }
          }
        } else if (res.exitCode == 1) {
          // User clicked Cancel in zenity
          return null;
        }
      } catch (_) {
        // Zenity also failed; rethrow portalError to trigger manual path entry
      }
    }
    rethrow;
  }
}

Future<SelectedFile?> loadFileFromPath(String path) async {
  final trimmed = path.trim();
  final f = File(trimmed);
  if (await f.exists()) {
    final bytes = await f.readAsBytes();
    final name = trimmed.split(Platform.pathSeparator).last;
    return SelectedFile(name: name, bytes: bytes);
  }
  throw Exception('No file found at: $trimmed');
}
