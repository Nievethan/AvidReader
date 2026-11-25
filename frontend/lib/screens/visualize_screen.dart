import 'dart:async';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../main.dart';
import '../models/book_item.dart';
import '../theme/classic_lit_theme.dart';
import '../widgets/character_portrait.dart';
import '../widgets/filter_pill_row.dart';
import '../widgets/paper_card.dart';
import '../widgets/scene_gallery.dart';
import '../widgets/vintage_progress_bar.dart';

class VisualizeScreen extends StatefulWidget {
  final BookItem book;
  final VoidCallback onBackToReaderTap;

  const VisualizeScreen({
    super.key,
    required this.book,
    required this.onBackToReaderTap,
  });

  @override
  State<VisualizeScreen> createState() => _VisualizeScreenState();
}

class _VisualizeScreenState extends State<VisualizeScreen> {
  static const _categories = ['Characters', 'Relationships', 'Concept map', 'Scenes'];
  static const _scenesTab = 3;
  final _sceneGalleryKey = GlobalKey<SceneGalleryState>();

  int _selectedCategoryIndex = 0;
  int _selectedCharacterIndex = 0;

  bool _loading = true;
  bool _generating = false;
  String? _error;
  RelationshipsResult? _result;

  // Portraits are painted in the background after an Update; poll the
  // (free, cached) GET endpoint until none are pending.
  static const _portraitPollInterval = Duration(seconds: 3);
  static const _portraitPollMaxDuration = Duration(minutes: 3);
  Timer? _portraitPollTimer;
  DateTime? _portraitPollStartedAt;

  @override
  void initState() {
    super.initState();
    _loadRelationships();
  }

  @override
  void dispose() {
    _stopPortraitPolling();
    super.dispose();
  }

  bool _hasPendingPortraits(RelationshipsResult? res) =>
      res?.nodes.any((n) => n.portraitPending) ?? false;

  void _syncPortraitPolling() {
    if (!_hasPendingPortraits(_result)) {
      _stopPortraitPolling();
      return;
    }
    if (_portraitPollTimer != null) return;
    _portraitPollStartedAt = DateTime.now();
    _portraitPollTimer =
        Timer.periodic(_portraitPollInterval, (_) => _pollPortraits());
  }

  void _stopPortraitPolling() {
    _portraitPollTimer?.cancel();
    _portraitPollTimer = null;
    _portraitPollStartedAt = null;
  }

  Future<void> _pollPortraits() async {
    final startedAt = _portraitPollStartedAt;
    if (startedAt != null &&
        DateTime.now().difference(startedAt) > _portraitPollMaxDuration) {
      _stopPortraitPolling();
      return;
    }
    final bookId = widget.book.id;
    try {
      final res = await api.getRelationships(bookId);
      if (!mounted || widget.book.id != bookId) return;
      setState(() => _result = res);
      _syncPortraitPolling();
    } on ApiException {
      // Transient: try again on the next tick.
    }
  }

  @override
  void didUpdateWidget(covariant VisualizeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.book.id != widget.book.id) {
      _selectedCharacterIndex = 0;
      _stopPortraitPolling();
      _loadRelationships();
    }
  }

  Future<void> _loadRelationships() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await api.getRelationships(widget.book.id);
      if (!mounted) return;
      setState(() {
        _result = res;
        _loading = false;
        if (_selectedCharacterIndex >= res.nodes.length) {
          _selectedCharacterIndex = 0;
        }
      });
      _syncPortraitPolling();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _generateRelationships() async {
    setState(() {
      _generating = true;
      _error = null;
    });
    try {
      final res = await api.generateRelationships(widget.book.id);
      if (!mounted) return;
      setState(() {
        _result = res;
        _generating = false;
        if (_selectedCharacterIndex >= res.nodes.length) {
          _selectedCharacterIndex = 0;
        }
      });
      _syncPortraitPolling();
      final painting = res.nodes.where((n) => n.portraitPending).length;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          // The backend's message wins: it explains partial progress
          // ("Analyzed through page 120 so far…") or a real error.
          content: Text(
            res.message ??
                (res.isReady && res.nodes.isNotEmpty
                    ? 'Extracted ${res.nodes.length} characters & ${res.edges.length} relationships!'
                        '${painting > 0 ? ' Painting $painting new portrait${painting == 1 ? '' : 's'}…' : ''}'
                    : 'Extraction complete.'),
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _generating = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Extraction failed: ${e.message}')),
      );
    }
  }

  /// The header's Update button acts on whichever tab is open.
  void _onUpdateTap() {
    if (_selectedCategoryIndex == _scenesTab) {
      _sceneGalleryKey.currentState?.reload();
    } else {
      _generateRelationships();
    }
  }

  Widget _categoryPills() => FilterPillRow(
        options: _categories,
        selectedIndex: _selectedCategoryIndex,
        onSelected: (index) => setState(() => _selectedCategoryIndex = index),
      );

  IconData _iconForRole(String? role) {
    final r = (role ?? '').toLowerCase();
    if (r.contains('protagonist') || r.contains('hero')) {
      return Icons.star_border;
    }
    if (r.contains('antagonist') || r.contains('villain') || r.contains('rival')) {
      return Icons.shield_outlined;
    }
    if (r.contains('mentor') || r.contains('magistrate') || r.contains('teacher')) {
      return Icons.balance_outlined;
    }
    if (r.contains('friend') || r.contains('ally') || r.contains('confidante')) {
      return Icons.handshake_outlined;
    }
    return Icons.person_outline;
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Top Header
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: const BoxDecoration(
            border: Border(
              bottom: BorderSide(color: ClassicLitTheme.deckleBorder),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Visualize',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    Text(
                      widget.book.title,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: ClassicLitTheme.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.menu_book_outlined, size: 18),
                    tooltip: 'Back to Reader',
                    onPressed: widget.onBackToReaderTap,
                  ),
                  const SizedBox(width: 4),
                  InkWell(
                    onTap: _generating ? null : _onUpdateTap,
                    borderRadius: BorderRadius.circular(4),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: ClassicLitTheme.elevatedPaper,
                        border: Border.all(
                          color: ClassicLitTheme.oxbloodPrimary,
                          width: 1.1,
                        ),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (_generating)
                            const SizedBox(
                              width: 12,
                              height: 12,
                              child: CircularProgressIndicator(
                                strokeWidth: 1.8,
                                color: ClassicLitTheme.oxbloodPrimary,
                              ),
                            )
                          else
                            const Icon(
                              Icons.refresh,
                              size: 14,
                              color: ClassicLitTheme.oxbloodPrimary,
                            ),
                          const SizedBox(width: 4),
                          Text(
                            _generating ? 'Extracting…' : 'Update',
                            style: const TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: ClassicLitTheme.oxbloodPrimary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),

        Expanded(
          child: _buildContent(),
        ),
      ],
    );
  }

  Widget _buildContent() {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(color: ClassicLitTheme.oxbloodPrimary),
      );
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.error_outline,
                size: 36,
                color: ClassicLitTheme.oxbloodPrimary,
              ),
              const SizedBox(height: 10),
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: _loadRelationships,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    if (_selectedCategoryIndex == _scenesTab) {
      // Scenes don't depend on the character map, so this tab works even
      // before any characters have been extracted.
      return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _categoryPills(),
          const SizedBox(height: 14),
          SceneGallery(key: _sceneGalleryKey, bookId: widget.book.id),
        ],
      );
    }

    final result = _result;
    final nodes = result?.nodes ?? [];
    final edges = result?.edges ?? [];

    if (nodes.isEmpty) {
      return Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
            child: Align(alignment: Alignment.centerLeft, child: _categoryPills()),
          ),
          Expanded(child: _buildEmptyState(result?.message)),
        ],
      );
    }

    final currentIndex = _selectedCharacterIndex.clamp(0, nodes.length - 1);
    final currentCharacter = nodes[currentIndex];
    final characterEdges = edges.where((e) =>
        e.source == currentCharacter.id || e.target == currentCharacter.id).toList();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _categoryPills(),
        const SizedBox(height: 14),

        if (_generating) ...[
          const PaperCard(
            backgroundColor: ClassicLitTheme.elevatedPaper,
            padding: EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Extracting grounded characters up to your current reading position…',
                  style: TextStyle(
                    fontSize: 11.5,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
                SizedBox(height: 6),
                VintageProgressBar(
                  value: 0.65,
                  fillColor: ClassicLitTheme.libraryGreen,
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],

        if (_selectedCategoryIndex == 1)
          // Relationships list view
          _buildAllRelationshipsView(nodes, edges)
        else
          // Characters view
          _buildCharacterProfileView(currentCharacter, characterEdges, nodes, result?.boundaryLabel),

        const SizedBox(height: 16),
        Text(
          'CHARACTERS IN THIS CHAPTER',
          style: Theme.of(context).textTheme.labelSmall,
        ),
        const SizedBox(height: 8),

        // Character Thumbnail Strip
        SizedBox(
          height: 92,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: nodes.length,
            separatorBuilder: (_, __) => const SizedBox(width: 8),
            itemBuilder: (context, index) {
              final char = nodes[index];
              final isSelected = index == currentIndex;
              return GestureDetector(
                onTap: () => setState(() => _selectedCharacterIndex = index),
                child: Container(
                  width: 90,
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? ClassicLitTheme.goldHighlightWash
                        : ClassicLitTheme.elevatedPaper,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(
                      color: isSelected
                          ? ClassicLitTheme.oxbloodPrimary
                          : ClassicLitTheme.deckleBorder,
                      width: isSelected ? 1.6 : 1.1,
                    ),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      CharacterPortrait(
                        node: char,
                        size: 44,
                        circular: true,
                        fallbackIcon: _iconForRole(char.role),
                        iconColor: isSelected
                            ? ClassicLitTheme.oxbloodPrimary
                            : ClassicLitTheme.inkSecondary,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        char.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: isSelected
                              ? FontWeight.w700
                              : FontWeight.w500,
                          color: ClassicLitTheme.inkPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState(String? message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.account_tree_outlined,
              size: 48,
              color: ClassicLitTheme.oxbloodPrimary,
            ),
            const SizedBox(height: 14),
            Text(
              'Character Map',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            Text(
              message ??
                  'No characters extracted yet. Tap Update to analyze what you\'ve read so far and extract characters without spoilers.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 13,
                color: ClassicLitTheme.inkSecondary,
                height: 1.45,
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton.icon(
              onPressed: _generating ? null : _generateRelationships,
              icon: _generating
                  ? const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: ClassicLitTheme.inkOnPrimary,
                      ),
                    )
                  : const Icon(Icons.auto_awesome, size: 16),
              label: Text(
                _generating ? 'Extracting…' : 'Extract Character Map',
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: ClassicLitTheme.oxbloodPrimary,
                foregroundColor: ClassicLitTheme.inkOnPrimary,
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 12,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCharacterProfileView(
    CharacterNode currentCharacter,
    List<CharacterEdge> characterEdges,
    List<CharacterNode> allNodes,
    String? boundaryLabel,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Main Etching / Character Focus Canvas
        Container(
          constraints: const BoxConstraints(minHeight: 180),
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
          width: double.infinity,
          decoration: BoxDecoration(
            color: ClassicLitTheme.linenCard,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: ClassicLitTheme.inkPrimary,
              width: 1.2,
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CharacterPortrait(
                key: ValueKey('hero-${currentCharacter.id}'),
                node: currentCharacter,
                size: currentCharacter.hasPortrait ||
                        currentCharacter.portraitPending ||
                        currentCharacter.portraitWaiting
                    ? 132
                    : 60,
                fallbackIcon: _iconForRole(currentCharacter.role),
                iconColor: ClassicLitTheme.oxbloodPrimary.withValues(
                  alpha: 0.85,
                ),
              ),
              if (currentCharacter.portraitPending) ...[
                const SizedBox(height: 6),
                const Text(
                  'Painting portrait…',
                  style: TextStyle(
                    fontSize: 10.5,
                    fontStyle: FontStyle.italic,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
              ],
              if (currentCharacter.portraitWaiting) ...[
                const SizedBox(height: 6),
                const Text(
                  'Not described yet — portrait comes once the book describes them',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 10.5,
                    fontStyle: FontStyle.italic,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                ),
              ],
              const SizedBox(height: 8),
              Text(
                currentCharacter.name,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: ClassicLitTheme.inkPrimary,
                ),
              ),
              if (currentCharacter.role != null &&
                  currentCharacter.role!.isNotEmpty) ...[
                const SizedBox(height: 4),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: ClassicLitTheme.goldHighlightWash,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: ClassicLitTheme.deckleBorder),
                  ),
                  child: Text(
                    currentCharacter.role!.toUpperCase(),
                    style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: ClassicLitTheme.oxbloodPrimary,
                      letterSpacing: 0.6,
                    ),
                  ),
                ),
              ],
              if (boundaryLabel != null) ...[
                const SizedBox(height: 6),
                Text(
                  'Extracted through $boundaryLabel',
                  style: const TextStyle(
                    fontSize: 11,
                    color: ClassicLitTheme.inkSecondary,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 12),

        // Character Details Card
        PaperCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'About ${currentCharacter.name}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 6),
              Text(
                currentCharacter.description ?? 'No detailed description available.',
                style: const TextStyle(fontSize: 13, height: 1.45),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),

        // Connections Card
        PaperCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Relationships (${characterEdges.length})',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              if (characterEdges.isEmpty)
                const Text(
                  'No direct relationships recorded yet for this character.',
                  style: TextStyle(
                    fontSize: 12,
                    fontStyle: FontStyle.italic,
                    color: ClassicLitTheme.inkSecondary,
                  ),
                )
              else
                ...characterEdges.map((edge) {
                  final isSource = edge.source == currentCharacter.id;
                  final otherId = isSource ? edge.target : edge.source;
                  final otherNode = allNodes.firstWhere(
                    (n) => n.id == otherId,
                    orElse: () => CharacterNode(id: otherId, name: otherId),
                  );
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: ClassicLitTheme.elevatedPaper,
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(color: ClassicLitTheme.deckleBorder),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                isSource
                                    ? Icons.arrow_forward
                                    : Icons.arrow_back,
                                size: 14,
                                color: ClassicLitTheme.oxbloodPrimary,
                              ),
                              const SizedBox(width: 6),
                              // Relationship type as its own badge -- same
                              // treatment as the character role badge above
                              // -- instead of plain text run together with
                              // the name.
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 6,
                                  vertical: 2,
                                ),
                                decoration: BoxDecoration(
                                  color: ClassicLitTheme.goldHighlightWash,
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(
                                    color: ClassicLitTheme.deckleBorder,
                                  ),
                                ),
                                child: Text(
                                  (edge.relationship ?? 'connected to')
                                      .toUpperCase(),
                                  style: const TextStyle(
                                    fontSize: 9.5,
                                    fontWeight: FontWeight.w700,
                                    color: ClassicLitTheme.oxbloodPrimary,
                                    letterSpacing: 0.4,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  otherNode.name,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                    fontSize: 13,
                                    color: ClassicLitTheme.inkPrimary,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          if (edge.label != null && edge.label!.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text(
                              edge.label!,
                              style: const TextStyle(
                                fontSize: 12,
                                color: ClassicLitTheme.inkSecondary,
                              ),
                            ),
                          ],
                          if (edge.evidence != null &&
                              edge.evidence!.isNotEmpty) ...[
                            const SizedBox(height: 6),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 4,
                              ),
                              decoration: const BoxDecoration(
                                border: Border(
                                  left: BorderSide(
                                    color: ClassicLitTheme.libraryGreen,
                                    width: 2.5,
                                  ),
                                ),
                              ),
                              child: Text(
                                '"${edge.evidence}"',
                                style: const TextStyle(
                                  fontSize: 11,
                                  fontStyle: FontStyle.italic,
                                  color: ClassicLitTheme.libraryGreen,
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  );
                }),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAllRelationshipsView(
    List<CharacterNode> nodes,
    List<CharacterEdge> edges,
  ) {
    if (edges.isEmpty) {
      return const PaperCard(
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'No relationships recorded yet. Tap Update above to extract relationships from the text.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontStyle: FontStyle.italic,
                color: ClassicLitTheme.inkSecondary,
              ),
            ),
          ),
        ),
      );
    }

    final nodeMap = {for (var n in nodes) n.id: n};

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: edges.map((edge) {
        final sourceNode = nodeMap[edge.source] ??
            CharacterNode(id: edge.source, name: edge.source);
        final targetNode = nodeMap[edge.target] ??
            CharacterNode(id: edge.target, name: edge.target);

        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: PaperCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Flexible(
                      child: Text(
                        '${sourceNode.name} ➔ ${targetNode.name}',
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13.5,
                          color: ClassicLitTheme.oxbloodPrimary,
                        ),
                      ),
                    ),
                    if (edge.relationship != null)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: ClassicLitTheme.elevatedPaper,
                          borderRadius: BorderRadius.circular(3),
                          border: Border.all(color: ClassicLitTheme.deckleBorder),
                        ),
                        child: Text(
                          edge.relationship!,
                          style: const TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: ClassicLitTheme.inkSecondary,
                          ),
                        ),
                      ),
                  ],
                ),
                if (edge.label != null && edge.label!.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    edge.label!,
                    style: const TextStyle(fontSize: 12.5),
                  ),
                ],
                if (edge.evidence != null && edge.evidence!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: ClassicLitTheme.elevatedPaper,
                      borderRadius: BorderRadius.circular(4),
                      border: const Border(
                        left: BorderSide(
                          color: ClassicLitTheme.libraryGreen,
                          width: 3,
                        ),
                      ),
                    ),
                    child: Text(
                      'Evidence: "${edge.evidence}"',
                      style: const TextStyle(
                        fontSize: 11,
                        fontStyle: FontStyle.italic,
                        color: ClassicLitTheme.libraryGreen,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}
