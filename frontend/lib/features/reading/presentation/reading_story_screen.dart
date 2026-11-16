import 'dart:async';

import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/reading/presentation/reading_quiz_screen.dart';

// ------------------------------------------------------------------- Story
enum StoryState { loading, slow, error, story }

class ReadingStoryScreen extends StatefulWidget {
  const ReadingStoryScreen({
    super.key,
    this.level = 'Medium',
    this.topic = 'Budaya',
    this.initialState = StoryState.story,
    this.autoLoad = true,
    this.openVocab,
    this.scrollToEnd = false,
  });

  final String level;
  final String topic;
  final StoryState initialState;

  /// Jika true, state loading otomatis berlanjut ke cerita.
  final bool autoLoad;
  final String? openVocab;
  final bool scrollToEnd;

  @override
  State<ReadingStoryScreen> createState() => _ReadingStoryScreenState();
}

class _ReadingStoryScreenState extends State<ReadingStoryScreen> {
  late StoryState _state = widget.initialState;
  final _scroll = ScrollController();
  Timer? _slowTimer;
  Timer? _doneTimer;

  String get _meta => '${widget.level} · ${widget.topic}';

  @override
  void initState() {
    super.initState();
    if (_state == StoryState.loading && widget.autoLoad) _generate();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.openVocab != null) _showVocab(widget.openVocab!);
      if (widget.scrollToEnd && _scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    _doneTimer?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  void _generate() {
    setState(() => _state = StoryState.loading);
    _slowTimer = Timer(const Duration(seconds: 10), () {
      if (mounted) setState(() => _state = StoryState.slow);
    });
    _doneTimer = Timer(const Duration(milliseconds: 2200), () {
      _slowTimer?.cancel();
      if (mounted) setState(() => _state = StoryState.story);
    });
  }

  void _cancel() {
    _slowTimer?.cancel();
    _doneTimer?.cancel();
    Navigator.maybePop(context);
  }

  void _showVocab(String word) {
    final item = ReadingDummy.vocabulary[word];
    if (item == null) return;
    showModalBottomSheet(
      context: context,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 8, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(word, style: AppText.h2)),
                IconButton(
                  onPressed: () => Navigator.pop(ctx),
                  icon: const Icon(Icons.close, color: AppColors.primary),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 20),
                  Text(item.meaning,
                      style: AppText.sans(size: 16, color: AppColors.primary)),
                  const SizedBox(height: 20),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: Text(item.example,
                        style: AppText.serif(size: 17, style: FontStyle.italic)),
                  ),
                  const SizedBox(height: 24),
                  AppButton.secondary(
                      label: 'Kembali membaca', onPressed: () => Navigator.pop(ctx)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final busy = _state == StoryState.loading || _state == StoryState.slow;
    return AppScaffold(
      title: ReadingDummy.storyTitle,
      bottom: _state == StoryState.story
          ? AppButton(
              label: 'Mulai kuis',
              onPressed: () => Navigator.of(context)
                  .push(MaterialPageRoute(builder: (_) => const ReadingQuizScreen())),
            )
          : AppButton(
              label: 'Buat cerita',
              loading: busy,
              loadingLabel: 'Membuat cerita…',
              onPressed: _generate,
            ),
      body: _state == StoryState.story ? _buildStory() : _buildPending(),
    );
  }

  Widget _buildPending() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        MetaLabel(_meta),
        const SizedBox(height: 24),
        if (_state == StoryState.slow) ...[
          StatusBanner.slow(onAction: _cancel),
          const SizedBox(height: 28),
        ],
        if (_state == StoryState.error) ...[
          StatusBanner.timeout(onAction: _generate),
          const SizedBox(height: 28),
        ],
        Text(_state == StoryState.error ? 'Cerita belum tersedia' : 'Membuat cerita…',
            style: AppText.h3),
        const SizedBox(height: 20),
        Text('Pilihan kamu tersimpan: $_meta', style: AppText.small),
        const SizedBox(height: 20),
        const SkeletonParagraph(groups: 2),
        const SkeletonBlock(),
        const SizedBox(height: 16),
        const SkeletonBlock(),
      ],
    );
  }

  Widget _buildStory() {
    final base = AppText.serif(size: 18, height: 1.6);
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        MetaLabel(_meta),
        const SizedBox(height: 20),
        for (final p in ReadingDummy.paragraphs) ...[
          Text.rich(TextSpan(style: base, children: _spans(p, base))),
          const SizedBox(height: 22),
        ],
        Text('Ketuk kata berstabilo untuk melihat artinya.', style: AppText.small),
      ],
    );
  }

  List<InlineSpan> _spans(String paragraph, TextStyle base) {
    final spans = <InlineSpan>[];
    final regex = RegExp(r'\[(.+?)\]');
    var last = 0;
    for (final m in regex.allMatches(paragraph)) {
      spans.add(TextSpan(text: paragraph.substring(last, m.start)));
      final word = m.group(1)!;
      spans.add(WidgetSpan(
        alignment: PlaceholderAlignment.baseline,
        baseline: TextBaseline.alphabetic,
        child: GestureDetector(
          onTap: () => _showVocab(word),
          child: Container(
            color: AppColors.highlight,
            padding: const EdgeInsets.symmetric(horizontal: 1),
            child: Text(word, style: base),
          ),
        ),
      ));
      last = m.end;
    }
    spans.add(TextSpan(text: paragraph.substring(last)));
    return spans;
  }
}
