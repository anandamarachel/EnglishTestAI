import 'dart:async';

import 'package:flutter/material.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/reading/application/reading_session.dart';
import 'package:english_day/features/reading/data/reading_models.dart';
import 'package:english_day/features/reading/presentation/reading_quiz_screen.dart';

// ------------------------------------------------------------------- Story
enum StoryState { loading, slow, error, story }

class ReadingStoryScreen extends StatefulWidget {
  const ReadingStoryScreen({
    super.key,
    required this.practice,
    this.initialState,
    this.autoLoad = true,
    this.openVocab,
    this.scrollToEnd = false,
  });

  final ReadingPractice practice;

  /// Default: the story if it is already loaded, otherwise loading.
  /// The design gallery sets loading/slow/error directly.
  final StoryState? initialState;

  /// Start generating the story when the screen opens in the loading state.
  final bool autoLoad;
  final String? openVocab;
  final bool scrollToEnd;

  @override
  State<ReadingStoryScreen> createState() => _ReadingStoryScreenState();
}

class _ReadingStoryScreenState extends State<ReadingStoryScreen> {
  static const _slowAfter = Duration(seconds: 10);

  late StoryState _state = widget.initialState ??
      (widget.practice.story != null ? StoryState.story : StoryState.loading);
  final _scroll = ScrollController();
  Timer? _slowTimer;
  int _run = 0;

  ReadingStory? get _story => widget.practice.story;

  @override
  void initState() {
    super.initState();
    if (_state == StoryState.loading && widget.autoLoad) _load();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final word = widget.openVocab;
      if (word != null) {
        for (final p in _story?.paragraphs ?? const <ReadingParagraph>[]) {
          for (final h in p.highlights) {
            if (h.vocab.word == word) return _showVocab(h.vocab);
          }
        }
      }
      if (widget.scrollToEnd && _scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final run = ++_run;
    setState(() => _state = StoryState.loading);
    _slowTimer?.cancel();
    _slowTimer = Timer(_slowAfter, () {
      if (mounted && _state == StoryState.loading) setState(() => _state = StoryState.slow);
    });
    try {
      await widget.practice.load();
      if (!mounted || run != _run) return;
      _slowTimer?.cancel();
      setState(() => _state = StoryState.story);
    } on OperationCancelledException {
      return;
    } catch (e) {
      if (!mounted || run != _run) return;
      _slowTimer?.cancel();
      setState(() => _state = StoryState.error);
      if (e is ApiException && !e.retryable && !e.isSessionEnded) {
        showAppSnack(context, e.userMessage);
      }
    }
  }

  void _cancel() {
    _run++;
    _slowTimer?.cancel();
    widget.practice.cancel();
    Navigator.maybePop(context);
  }

  void _showVocab(VocabEntry item) {
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
                Expanded(child: Text(item.word, style: AppText.h2)),
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
    final story = _story;
    final ready = _state == StoryState.story && story != null;
    return AppScaffold(
      title: story?.title ?? 'Reading',
      bottom: ready
          ? AppButton(
              label: 'Mulai kuis',
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => ReadingQuizScreen(practice: widget.practice))),
            )
          : AppButton(
              label: 'Buat cerita',
              loading: busy,
              loadingLabel: 'Membuat cerita…',
              onPressed: _load,
            ),
      body: ready ? _buildStory(story) : _buildPending(),
    );
  }

  Widget _buildPending() {
    final meta = widget.practice.meta;
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        MetaLabel(meta),
        const SizedBox(height: 24),
        if (_state == StoryState.slow) ...[
          StatusBanner.slow(onAction: _cancel),
          const SizedBox(height: 28),
        ],
        if (_state == StoryState.error) ...[
          StatusBanner.timeout(onAction: _load),
          const SizedBox(height: 28),
        ],
        Text(_state == StoryState.error ? 'Cerita belum tersedia' : 'Membuat cerita…',
            style: AppText.h3),
        const SizedBox(height: 20),
        Text('Pilihan kamu tersimpan: $meta', style: AppText.small),
        const SizedBox(height: 20),
        const SkeletonParagraph(groups: 2),
        const SkeletonBlock(),
        const SizedBox(height: 16),
        const SkeletonBlock(),
      ],
    );
  }

  Widget _buildStory(ReadingStory story) {
    final base = AppText.serif(size: 18, height: 1.6);
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        MetaLabel(story.meta),
        const SizedBox(height: 20),
        for (final p in story.paragraphs) ...[
          Text.rich(TextSpan(style: base, children: _spans(p, base))),
          const SizedBox(height: 22),
        ],
        Text('Ketuk kata berstabilo untuk melihat artinya.', style: AppText.small),
      ],
    );
  }

  List<InlineSpan> _spans(ReadingParagraph paragraph, TextStyle base) {
    final text = paragraph.text;
    final spans = <InlineSpan>[];
    var last = 0;
    for (final h in paragraph.highlights) {
      spans.add(TextSpan(text: text.substring(last, h.start)));
      spans.add(WidgetSpan(
        alignment: PlaceholderAlignment.baseline,
        baseline: TextBaseline.alphabetic,
        child: GestureDetector(
          onTap: () => _showVocab(h.vocab),
          child: Container(
            color: AppColors.highlight,
            padding: const EdgeInsets.symmetric(horizontal: 1),
            child: Text(text.substring(h.start, h.end), style: base),
          ),
        ),
      ));
      last = h.end;
    }
    spans.add(TextSpan(text: text.substring(last)));
    return spans;
  }
}
