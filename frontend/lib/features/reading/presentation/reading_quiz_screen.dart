import 'package:flutter/material.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/answer_widgets.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/reading/application/reading_session.dart';
import 'package:english_day/features/reading/data/reading_models.dart';
import 'package:english_day/features/reading/presentation/reading_result_screen.dart';

// -------------------------------------------------------------------- Quiz
/// One question at a time; the server grades each answer when it is sent.
class ReadingQuizScreen extends StatefulWidget {
  const ReadingQuizScreen({
    super.key,
    required this.practice,
    this.initialIndex,
    this.initialSelected,
    this.initialSubmitted = false,
  });

  /// Must have a loaded story.
  final ReadingPractice practice;

  /// Design gallery only: question index / selected option index / already sent.
  final int? initialIndex;
  final int? initialSelected;
  final bool initialSubmitted;

  @override
  State<ReadingQuizScreen> createState() => _ReadingQuizScreenState();
}

class _ReadingQuizScreenState extends State<ReadingQuizScreen> {
  late final ReadingStory _story = widget.practice.story!;
  late int _index = widget.initialIndex ?? widget.practice.nextQuestionIndex;
  String? _selected;
  ReadingAnswer? _answer;
  bool _sending = false;

  ReadingQuestion get _q => _story.questions[_index];
  int get _total => _story.questions.length;

  @override
  void initState() {
    super.initState();
    final i = widget.initialSelected;
    if (i != null) _selected = _q.options[i].id;
    _answer = widget.practice.answers[_q.id];
    if (widget.initialSubmitted && _answer == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _submit());
    }
  }

  Future<void> _submit() async {
    final selected = _selected;
    if (selected == null) return;
    setState(() => _sending = true);
    try {
      final answer = await widget.practice.answer(_q, selected);
      if (!mounted) return;
      setState(() {
        _answer = answer;
        _sending = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      _showError(e, 'Jawaban belum terkirim. Coba lagi.');
    }
  }

  Future<void> _next() async {
    if (_index < _total - 1) {
      setState(() {
        _index++;
        _answer = widget.practice.answers[_q.id];
        _selected = _answer?.selectedOptionId;
      });
      return;
    }
    setState(() => _sending = true);
    try {
      final summary = await widget.practice.finish();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ReadingResultScreen(
          story: _story,
          answers: widget.practice.answers,
          summary: summary,
        ),
      ));
    } catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      _showError(e, 'Hasil belum bisa dibuat. Coba lagi.');
    }
  }

  void _showError(Object error, String fallback) {
    if (error is ApiException && error.isSessionEnded) return; // the app-wide sheet shows
    showAppSnack(context,
        error is ApiException && error.code == ApiException.network ? error.userMessage : fallback);
  }

  OptionState _optionState(ReadingOption option) {
    final answer = _answer;
    if (answer == null) {
      return _selected == option.id ? OptionState.selected : OptionState.normal;
    }
    if (option.id == answer.correctOptionId) return OptionState.correct;
    if (option.id == answer.selectedOptionId) return OptionState.wrong;
    return OptionState.normal;
  }

  @override
  Widget build(BuildContext context) {
    final answer = _answer;
    return AppScaffold(
      title: 'Kuis',
      leadingIcon: Icons.close,
      bottom: answer != null
          ? AppButton(
              label: _index == _total - 1 ? 'Lihat hasil' : 'Soal berikutnya',
              loading: _sending,
              loadingLabel: 'Menghitung hasil…',
              onPressed: _next,
            )
          : AppButton(
              label: 'Kirim jawaban',
              loading: _sending,
              loadingLabel: 'Memeriksa…',
              onPressed: _selected == null ? null : _submit,
            ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Row(
            children: [
              Text('Soal ${_index + 1} dari $_total',
                  style: AppText.sans(size: 14, weight: FontWeight.w600)),
              const SizedBox(width: 12),
              Expanded(
                child: Text(_story.title,
                    textAlign: TextAlign.right,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.sans(size: 13, color: AppColors.textSecondary)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (_index + 1) / _total,
              minHeight: 4,
              backgroundColor: AppColors.divider,
              color: AppColors.progressBrown,
            ),
          ),
          const SizedBox(height: 24),
          Text(_q.text, style: AppText.h2.copyWith(height: 1.35)),
          const SizedBox(height: 20),
          for (var i = 0; i < _q.options.length; i++)
            AnswerOption(
              label: '${optionLetter(i)}. ${_q.options[i].text}',
              state: _optionState(_q.options[i]),
              onTap: answer != null || _sending
                  ? null
                  : () => setState(() => _selected = _q.options[i].id),
            ),
          if (answer != null) ...[
            const SizedBox(height: 12),
            AnswerFeedback(correct: answer.isCorrect, message: answer.explanation),
          ],
        ],
      ),
    );
  }
}

/// A, B, C, ... for option labels as in the design.
String optionLetter(int index) => String.fromCharCode(65 + index);
