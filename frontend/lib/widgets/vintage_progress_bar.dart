import 'package:flutter/material.dart';

import '../theme/classic_lit_theme.dart';

class VintageProgressBar extends StatelessWidget {
  final double value; // 0.0 to 1.0
  final Color fillColor;
  final double height;

  const VintageProgressBar({
    super.key,
    required this.value,
    this.fillColor = ClassicLitTheme.oxbloodPrimary,
    this.height = 8,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      width: double.infinity,
      decoration: BoxDecoration(
        color: ClassicLitTheme.elevatedPaper,
        borderRadius: BorderRadius.circular(3),
        border: Border.all(color: ClassicLitTheme.deckleBorder),
      ),
      child: FractionallySizedBox(
        alignment: Alignment.centerLeft,
        widthFactor: value.clamp(0.0, 1.0),
        child: Container(
          decoration: BoxDecoration(
            color: fillColor,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      ),
    );
  }
}
