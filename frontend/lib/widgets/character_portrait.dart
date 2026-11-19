import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';
import '../theme/classic_lit_theme.dart';

/// A character's AI portrait, or a fallback:
/// - ready   -> the generated image (falls back to the icon if it fails to load)
/// - pending -> a soft pulsing placeholder while it's being painted
/// - none / failed -> the role icon (the pre-portrait behaviour)
class CharacterPortrait extends StatelessWidget {
  final CharacterNode node;
  final double size;
  final IconData fallbackIcon;
  final bool circular;
  final Color iconColor;

  const CharacterPortrait({
    super.key,
    required this.node,
    required this.size,
    required this.fallbackIcon,
    this.circular = false,
    this.iconColor = ClassicLitTheme.oxbloodPrimary,
  });

  @override
  Widget build(BuildContext context) {
    final radius = circular ? size / 2 : 6.0;
    Widget child;
    if (node.hasPortrait) {
      child = Image.network(
        api.absoluteUrl(node.portraitUrl!),
        width: size,
        height: size,
        fit: BoxFit.cover,
        gaplessPlayback: true,
        frameBuilder: (context, child, frame, wasSyncLoaded) {
          if (wasSyncLoaded) return child;
          return AnimatedOpacity(
            opacity: frame == null ? 0 : 1,
            duration: const Duration(milliseconds: 350),
            curve: Curves.easeOut,
            child: child,
          );
        },
        errorBuilder: (_, _, _) => _icon(),
      );
    } else if (node.portraitPending) {
      child = _PulsingPlaceholder(size: size, icon: fallbackIcon);
    } else {
      return SizedBox(
        width: size,
        height: size,
        child: Center(child: _icon()),
      );
    }

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: ClassicLitTheme.deckleBorder),
        color: ClassicLitTheme.elevatedPaper,
      ),
      clipBehavior: Clip.antiAlias,
      child: child,
    );
  }

  Widget _icon() => Icon(fallbackIcon, size: size * 0.45, color: iconColor);
}

class _PulsingPlaceholder extends StatefulWidget {
  final double size;
  final IconData icon;

  const _PulsingPlaceholder({required this.size, required this.icon});

  @override
  State<_PulsingPlaceholder> createState() => _PulsingPlaceholderState();
}

class _PulsingPlaceholderState extends State<_PulsingPlaceholder>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) => Container(
        color: Color.lerp(
          ClassicLitTheme.linenCard,
          ClassicLitTheme.goldHighlightWash,
          _controller.value,
        ),
        child: Center(
          child: Icon(
            widget.icon,
            size: widget.size * 0.4,
            color: ClassicLitTheme.inkSecondary.withValues(alpha: 0.35),
          ),
        ),
      ),
    );
  }
}
