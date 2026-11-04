import 'package:flutter/material.dart';

import '../theme/classic_lit_theme.dart';

class PaperCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color backgroundColor;

  const PaperCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(14),
    this.backgroundColor = ClassicLitTheme.linenCard,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: ClassicLitTheme.deckleBorder, width: 1.2),
      ),
      child: child,
    );
  }
}
