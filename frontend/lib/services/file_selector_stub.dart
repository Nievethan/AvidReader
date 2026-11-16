import 'dart:typed_data';

class SelectedFile {
  final String name;
  final Uint8List bytes;

  const SelectedFile({required this.name, required this.bytes});
}

Future<SelectedFile?> pickBookFile() async {
  throw UnsupportedError('Cannot pick file without platform implementation');
}

Future<SelectedFile?> loadFileFromPath(String path) async {
  throw UnsupportedError('Cannot load file path without platform implementation');
}
