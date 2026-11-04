import 'package:flutter/material.dart';

class CharacterVisual {
  final String name;
  final String role;
  final String description;
  final List<String> citations;
  final IconData icon;

  const CharacterVisual({
    required this.name,
    required this.role,
    required this.description,
    required this.citations,
    required this.icon,
  });
}
