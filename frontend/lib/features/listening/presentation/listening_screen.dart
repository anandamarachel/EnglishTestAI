import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/models/choice_question.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/answer_widgets.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/listening/application/listening_audio.dart';
import 'package:english_day/features/listening/application/listening_session.dart';
import 'package:english_day/features/listening/data/listening_repository.dart';

enum ListeningPhase { intro, loading, slow, practice, audioError, result }

enum ResultFocus { top, review, transcript }

/// Listen to one AI conversation, answer its questions, then see the grading and
/// the transcript (unlocked after submitting).
class ListeningScreen extends ConsumerStatefulWidget {
  const ListeningScreen({
    super.key,
    this.practice,
    this.resumeAttemptId,
    this.initialPhase,
    this.autoPlay = false,
    this.focus = ResultFocus.top,
    this.scrollToLast = false,
    this.freeze = false,
  });

  /// Default: a new [ListeningSession] against the backend. The gallery passes a demo.
  final ListeningPractice? practice;

  /// Continue this saved attempt (dashboard "Lanjutkan").
  final String? resumeAttemptId;

  /// Default: intro, or loading when resuming. The gallery sets any phase directly.
  final ListeningPhase? initialPhase;
  final bool autoPlay;
  final ResultFocus focus;

  /// Scroll to the last question ("locked" state).
  final bool scrollToLast;

  /// Gallery: stay in the loading state.
  final bool freeze;

  @override
  ConsumerState<ListeningScreen> createState() => _ListeningScreenState();
}

class _ListeningScreenState extends ConsumerState<ListeningScreen> {
  static const _slowAfter = Duration(seconds: 10);

  late final ListeningPractice _practice = widget.practice ??
      ListeningSession(
        ref.read(listeningRepositoryProvider),
        ref.read(listeningAudioLoaderProvider),
        resumeAttemptId: widget.resumeAttemptId,
      );
  late ListeningPhase _phase = widget.initialPhase ??
      (widget.resumeAttemptId != null ? ListeningPhase.loading : ListeningPhase.intro);

  final _scroll = ScrollController();
  final _reviewKey = GlobalKey();
  final _transcriptKey = GlobalKey();
  final _lastQuestionKey = GlobalKey();

  ListeningAudio? _audio;
  Timer? _slowTimer;
  bool _submitting = false;
  int _run = 0;

  @override
  void initState() {
    super.initState();
    _attachAudio();
    if (_phase == ListeningPhase.loading && !widget.freeze) _load();
    if (widget.autoPlay) _audio?.play();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final key = switch (widget.focus) {
        ResultFocus.review => _reviewKey,
        ResultFocus.transcript => _transcriptKey,
        ResultFocus.top => widget.scrollToLast ? _lastQuestionKey : null,
      };
      final ctx = key?.currentContext;
      if (ctx != null) Scrollable.ensureVisible(ctx, alignment: 0.02);
    });
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    _audio?.removeListener(_onAudio);
    _practice.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _attachAudio() {
    final audio = _practice.audio;
    if (identical(audio, _audio)) return;
    _audio?.removeListener(_onAudio);
    _audio = audio?..addListener(_onAudio);
  }

  void _onAudio() {
    if (mounted) setState(() {});
  }

  // ------------------------------------------------------------- loading
  Future<void> _load() async {
    final run = ++_run;
    setState(() => _phase = ListeningPhase.loading);
    _slowTimer?.cancel();
    _slowTimer = Timer(_slowAfter, () {
      if (mounted && _phase == ListeningPhase.loading) {
        setState(() => _phase = ListeningPhase.slow);
      }
    });
    try {
      await _practice.load();
      if (!mounted || run != _run) return;
      _slowTimer?.cancel();
      _attachAudio();
      if (_practice.result != null) {
        setState(() => _phase = ListeningPhase.result);
        return;
      }
      setState(() => _phase = ListeningPhase.practice);
      _autoPlay();
    } on OperationCancelledException {
      return;
    } on ListeningAudioException {
      if (!mounted || run != _run) return;
      _slowTimer?.cancel();
      setState(() => _phase = ListeningPhase.audioError);
    } catch (e) {
      if (!mounted || run != _run) return;
      _slowTimer?.cancel();
      setState(() => _phase = ListeningPhase.intro);
      if (e is ApiException && e.isSessionEnded) return; // the app-wide sheet shows
      showAppSnack(
          context,
          e is ApiException && e.code == ApiException.network
              ? e.userMessage
              : 'Latihan belum bisa dibuat. Coba lagi dalam beberapa saat.');
    }
  }

  /// Browsers may block playback that did not start from a tap: then stay paused.
  Future<void> _autoPlay() async {
    try {
      await _audio?.play();
    } catch (_) {}
  }

  void _cancelLoad() {
    _run++;
    _slowTimer?.cancel();
    _practice.cancel();
    setState(() => _phase = ListeningPhase.intro);
  }

  Future<void> _retryAudio() async {
    try {
      await _practice.reloadAudio();
      if (!mounted) return;
      _attachAudio();
      setState(() => _phase = ListeningPhase.practice);
      _autoPlay();
    } catch (_) {
      if (mounted) showAppSnack(context, 'Audio masih belum bisa dimuat. Coba lagi sebentar lagi.');
    }
  }

  // --------------------------------------------------------------- player
  Future<void> _togglePlay() async {
    final audio = _audio;
    if (audio == null) return;
    try {
      audio.playing ? await audio.pause() : await audio.play();
    } catch (_) {
      if (mounted) setState(() => _phase = ListeningPhase.audioError);
    }
  }

  Future<void> _replay() async {
    await _audio?.seek(Duration.zero);
    if (!(_audio?.playing ?? true)) await _togglePlay();
  }

  // --------------------------------------------------------------- answers
  Future<void> _submit() async {
    final questions = _practice.exercise?.questions ?? const <ChoiceQuestion>[];
    if (questions.any((q) => !_practice.selections.containsKey(q.id))) {
      showAppSnack(context, 'Jawab semua pertanyaan dulu, ya.');
      return;
    }
    setState(() => _submitting = true);
    try {
      await _practice.submit();
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _phase = ListeningPhase.result;
      });
      if (_scroll.hasClients) _scroll.jumpTo(0);
    } catch (e) {
      if (!mounted) return;
      setState(() => _submitting = false);
      if (e is ApiException && e.isSessionEnded) return;
      showAppSnack(
          context,
          e is ApiException && e.code == ApiException.network
              ? e.userMessage
              : 'Jawaban belum terkirim. Coba lagi.');
    }
  }

  void _restart() => Navigator.of(context)
      .pushReplacement(MaterialPageRoute(builder: (_) => const ListeningScreen()));

  String _fmt(Duration d) {
    final sec = d.inSeconds;
    return '${sec ~/ 60}:${(sec % 60).toString().padLeft(2, '0')}';
  }

  // ------------------------------------------------------------- build
  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Listening',
      bottom: _buildBottom(),
      body: _phase == ListeningPhase.intro
          ? _buildIntro()
          : ListView(
              controller: _scroll,
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              children: [
                MetaLabel(_practice.meta),
                const SizedBox(height: 24),
                ..._phase == ListeningPhase.result ? _buildResult() : _buildPractice(),
              ],
            ),
    );
  }

  Widget _buildBottom() {
    switch (_phase) {
      case ListeningPhase.intro:
        return AppButton(label: 'Mulai latihan', onPressed: _load);
      case ListeningPhase.loading:
      case ListeningPhase.slow:
        return const _DisabledLoadingButton(label: 'Menyiapkan audio…');
      case ListeningPhase.practice:
      case ListeningPhase.audioError:
        return AppButton(
          label: 'Kirim jawaban',
          loading: _submitting,
          loadingLabel: 'Memeriksa jawaban…',
          onPressed: _submit,
        );
      case ListeningPhase.result:
        return AppButton(label: 'Latihan baru', onPressed: _restart);
    }
  }

  Widget _buildIntro() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        MetaLabel(_practice.meta),
        const SizedBox(height: 80),
        const Align(
          alignment: Alignment.centerLeft,
          child: Icon(Icons.headphones_outlined, color: AppColors.primary, size: 48),
        ),
        const SizedBox(height: 20),
        Text('Latih telingamu, satu percakapan dulu.', style: AppText.h2.copyWith(height: 1.35)),
        const SizedBox(height: 20),
        Text(
          'Dengarkan percakapan singkat, lalu jawab 3 pertanyaan. '
          'Kamu bisa memutar ulang audio.',
          style: AppText.body,
        ),
      ],
    );
  }

  List<Widget> _buildPractice() {
    final loading = _phase == ListeningPhase.loading || _phase == ListeningPhase.slow;
    final questions = _practice.exercise?.questions ?? const <ChoiceQuestion>[];
    return [
      if (_phase == ListeningPhase.slow) ...[
        StatusBanner.slow(onAction: _cancelLoad),
        const SizedBox(height: 24),
      ],
      if (_phase == ListeningPhase.audioError) ...[
        StatusBanner(
          type: BannerType.error,
          message: 'Audio gagal dimuat karena koneksi terputus. Jawaban kamu tetap tersimpan.',
          actionLabel: 'Coba lagi',
          onAction: _retryAudio,
        ),
        const SizedBox(height: 24),
      ],
      _buildPlayer(loading),
      const SizedBox(height: 28),
      if (loading) ...[
        Text('Menyiapkan pertanyaan untuk kamu…',
            style: AppText.sans(size: 15, weight: FontWeight.w500, color: AppColors.textSecondary)),
        const SizedBox(height: 24),
        const SkeletonParagraph(groups: 2, withTitle: false),
      ] else ...[
        for (var q = 0; q < questions.length; q++)
          _QuestionBlock(
            key: q == questions.length - 1 ? _lastQuestionKey : null,
            number: q + 1,
            question: questions[q],
            selected: _practice.selections[questions[q].id],
            onSelect: _submitting
                ? null
                : (optionId) => setState(() => _practice.select(questions[q].id, optionId)),
          ),
        const SizedBox(height: 8),
        Row(
          children: [
            const Icon(Icons.lock_outline, color: AppColors.textSecondary),
            const SizedBox(width: 10),
            Text('Transkrip', style: AppText.h3),
          ],
        ),
        const SizedBox(height: 10),
        Text('Jawab semua pertanyaan untuk membuka transkrip.',
            style: AppText.sans(size: 15, color: AppColors.textSecondary, height: 1.45)),
      ],
    ];
  }

  Widget _buildPlayer(bool loading) {
    final audio = _audio;
    final ready = !loading && audio != null && _phase != ListeningPhase.audioError;
    final duration = audio?.duration ?? _practice.exercise?.duration ?? Duration.zero;
    final position = audio?.position ?? Duration.zero;
    final progress = !ready || duration == Duration.zero
        ? 0.0
        : (position.inMilliseconds / duration.inMilliseconds).clamp(0.0, 1.0);
    final playing = audio?.playing ?? false;
    final speed = audio?.speed ?? 1.0;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_practice.exercise?.title ?? 'Listening', style: AppText.h3.copyWith(fontSize: 20)),
          const SizedBox(height: 16),
          Row(
            children: [
              Material(
                color: ready ? AppColors.primary : AppColors.disabled,
                shape: const CircleBorder(),
                child: InkWell(
                  customBorder: const CircleBorder(),
                  onTap: ready ? _togglePlay : null,
                  child: SizedBox(
                    width: 56,
                    height: 56,
                    child: Center(
                      child: loading
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: AppColors.textSecondary),
                            )
                          : Icon(
                              playing ? Icons.pause_rounded : Icons.play_arrow_outlined,
                              color: Colors.white,
                              size: 34,
                            ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: progress,
                        minHeight: 4,
                        backgroundColor: AppColors.divider,
                        color: AppColors.progressPurple,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      loading ? 'Menyiapkan audio…' : '${_fmt(position)} / ${_fmt(duration)}',
                      style: AppText.small,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              IconButton(
                onPressed: ready ? _replay : null,
                icon: const Icon(Icons.replay, color: AppColors.primary),
              ),
              const SizedBox(width: 8),
              Text('Kecepatan', style: AppText.small),
              const Spacer(),
              _SpeedChip(
                label: '0,75×',
                selected: speed == 0.75,
                onTap: () => audio?.setSpeed(0.75),
              ),
              const SizedBox(width: 8),
              _SpeedChip(
                label: '1×',
                selected: speed == 1.0,
                onTap: () => audio?.setSpeed(1.0),
              ),
            ],
          ),
        ],
      ),
    );
  }

  List<Widget> _buildResult() {
    final result = _practice.result;
    final exercise = _practice.exercise;
    if (result == null || exercise == null) return const [];
    final score = result.correct;
    final wrong = result.total - score;
    final questions = exercise.questions;
    return [
      Text('Hasil latihan', style: AppText.h3.copyWith(fontSize: 20)),
      const SizedBox(height: 8),
      Align(alignment: Alignment.centerLeft, child: ScoreBadge('$score/${result.total}')),
      const SizedBox(height: 12),
      Text(
        wrong == 0
            ? 'Semua jawaban benar. Hebat!'
            : '$score jawaban benar. Yuk, pahami $wrong bagian lagi.',
        style: AppText.body,
      ),
      const SizedBox(height: 20),
      for (var q = 0; q < questions.length; q++)
        if (result.answers[questions[q].id] case final answer?)
          _ReviewBlock(
            key: q == 1 ? _reviewKey : null,
            number: q + 1,
            question: questions[q],
            answer: answer,
          ),
      const SizedBox(height: 8),
      Row(
        key: _transcriptKey,
        children: [
          const Icon(Icons.lock_open_outlined, color: AppColors.primary),
          const SizedBox(width: 10),
          Text('Transkrip', style: AppText.h3),
        ],
      ),
      const SizedBox(height: 6),
      Text('${exercise.title} · Kalimat bukti diberi stabilo.', style: AppText.small),
      const SizedBox(height: 12),
      for (final line in result.transcript)
        Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.symmetric(vertical: 2),
          color: line.evidence ? AppColors.highlight : null,
          child: Text(line.text, style: AppText.serif(size: 18, height: 1.55)),
        ),
    ];
  }
}

/// Tombol loading dengan tampilan nonaktif (abu-abu) seperti desain.
class _DisabledLoadingButton extends StatelessWidget {
  const _DisabledLoadingButton({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) => Container(
        height: 52,
        decoration: BoxDecoration(
          color: AppColors.disabled,
          borderRadius: BorderRadius.circular(14),
        ),
        alignment: Alignment.center,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.textSecondary),
            ),
            const SizedBox(width: 12),
            Text(label,
                style: AppText.sans(
                    size: 17, weight: FontWeight.w500, color: AppColors.textSecondary)),
          ],
        ),
      );
}

class _SpeedChip extends StatelessWidget {
  const _SpeedChip({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? AppColors.primarySoft : AppColors.surface,
      shape: StadiumBorder(
        side: BorderSide(color: selected ? AppColors.primary : AppColors.border),
      ),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onTap,
        child: SizedBox(
          width: 72,
          height: 48,
          child: Center(
            child: Text(label,
                style: AppText.sans(
                  size: 15,
                  weight: FontWeight.w600,
                  color: selected ? AppColors.primary : AppColors.textPrimary,
                )),
          ),
        ),
      ),
    );
  }
}

class _QuestionBlock extends StatelessWidget {
  const _QuestionBlock({
    super.key,
    required this.number,
    required this.question,
    required this.selected,
    required this.onSelect,
  });

  final int number;
  final ChoiceQuestion question;

  /// Selected option id.
  final String? selected;
  final ValueChanged<String>? onSelect;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Pertanyaan $number', style: AppText.small),
          const SizedBox(height: 8),
          Text(question.text, style: AppText.h3),
          const SizedBox(height: 12),
          for (var i = 0; i < question.options.length; i++)
            AnswerOption(
              label: '${optionLetter(i)}. ${question.options[i].text}',
              state: selected == question.options[i].id
                  ? OptionState.selected
                  : OptionState.normal,
              onTap: onSelect == null ? null : () => onSelect!(question.options[i].id),
            ),
        ],
      ),
    );
  }
}

class _ReviewBlock extends StatelessWidget {
  const _ReviewBlock({
    super.key,
    required this.number,
    required this.question,
    required this.answer,
  });

  final int number;
  final ChoiceQuestion question;
  final GradedAnswer answer;

  String _label(String? optionId) {
    final i = question.options.indexWhere((o) => o.id == optionId);
    return i < 0 ? '' : '${optionLetter(i)}. ${question.options[i].text}';
  }

  @override
  Widget build(BuildContext context) {
    final correct = answer.isCorrect;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Pertanyaan $number', style: AppText.small),
          const SizedBox(height: 8),
          Text(question.text, style: AppText.h3),
          const SizedBox(height: 12),
          AnswerOption(label: _label(answer.correctOptionId), state: OptionState.correct),
          if (!correct && answer.selectedOptionId != null)
            AnswerOption(label: _label(answer.selectedOptionId), state: OptionState.wrong),
          AnswerFeedback(correct: correct, message: answer.explanation),
        ],
      ),
    );
  }
}
