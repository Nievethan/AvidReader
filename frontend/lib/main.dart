import 'package:device_preview/device_preview.dart';
import 'package:device_preview/presets.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

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

class AvidReaderApp extends StatelessWidget {
  const AvidReaderApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AvidReader',
      debugShowCheckedModeBanner: false,
      theme: ClassicLitTheme.themeData,
      home: Scaffold(
        body: Center(
          child: Text(
            'AvidReader Theme Initialized',
            style: ClassicLitTheme.themeData.textTheme.headlineSmall,
          ),
        ),
      ),
    );
  }
}
