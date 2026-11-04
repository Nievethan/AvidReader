import 'package:flutter/material.dart';

import '../theme/classic_lit_theme.dart';

class FilterPillRow extends StatelessWidget {
  final List<String> options;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  const FilterPillRow({
    super.key,
    required this.options,
    required this.selectedIndex,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      children: List.generate(options.length, (index) {
        final isSelected = index == selectedIndex;
        return GestureDetector(
          onTap: () => onSelected(index),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(
              color: isSelected
                  ? ClassicLitTheme.oxbloodPrimary
                  : ClassicLitTheme.elevatedPaper,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: isSelected
                    ? ClassicLitTheme.oxbloodPrimary
                    : ClassicLitTheme.deckleBorder,
                width: 1.2,
              ),
            ),
            child: Text(
              options[index],
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: isSelected
                    ? ClassicLitTheme.inkOnPrimary
                    : ClassicLitTheme.inkPrimary,
              ),
            ),
          ),
        );
      }),
    );
  }
}
