import 'package:file_picker/file_picker.dart';
import 'file_selector_stub.dart';

export 'file_selector_stub.dart';

Future<SelectedFile?> pickBookFile() async {
  final file = await FilePicker.pickFile(
    type: FileType.custom,
    allowedExtensions: ['pdf', 'epub'],
  );
  if (file == null) return null;
  final bytes = await file.readAsBytes();
  return SelectedFile(name: file.name, bytes: bytes);
}

Future<SelectedFile?> loadFileFromPath(String path) async {
  throw UnsupportedError('Direct file path loading is not supported in browser');
}
