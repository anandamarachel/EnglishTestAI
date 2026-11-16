import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/answer_widgets.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/reading/presentation/reading_result_screen.dart';

// -------------------------------------------------------------------- Quiz
class ReadingQuizScreen extends StatefulWidget {
  const ReadingQuizScreen({
    super.key,
    this.initialIndex = 0,
    this.initialSelected,
    this.initialSubmitted = false,
  });

  final int initialIndex;
  final int? initialSelected;
  final bool initialSubmitted;

  @override
  State<ReadingQuizScreen> createState() => _ReadingQuizScreenState();
}

class _ReadingQuizScreenState extends State<ReadingQuizScreen> {
  late int _index = widget.initialIndex;
  late int? _selected = widget.initialSelected;
  late bool _submitted = widget.initialSubmitted;
  late final List<int?> _answers = List.filled(ReadingDummy.quiz.length, null);

  QuizQuestion get _q => ReadingDummy.quiz[_index];
  int get _total => ReadingDummy.quiz.length;

  void _submit() => setState(() {
        _submitted = true;
        _answers[_index] = _selected;
      });

  void _next() {
    if (_index == _total - 1) {
      // Isi jawaban kosong (jika dibuka dari galeri) dengan jawaban dummy.
      final answers = [
        for (var i = 0; i < _total; i++)
          _answers[i] ?? (i == 3 ? 0 : ReadingDummy.quiz[i].correctIndex),
      ];
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => ReadingResultScreen(answers: answers)),
      );
      return;
    }
    setState(() {
      _index++;
      _selected = null;
      _submitted = false;
    });
  }

  OptionState _optionState(int i) {
    if (!_submitted) return _selected == i ? OptionState.selected : OptionState.normal;
    if (i == _q.correctIndex) return OptionState.correct;
    if (i == _selected) return OptionState.wrong;
    return OptionState.normal;
  }

  @override
  Widget build(BuildContext context) {
    final correct = _selected == _q.correctIndex;
    return AppScaffold(
      title: 'Kuis',
      leadingIcon: Icons.close,
      bottom: _submitted
          ? AppButton(
              label: _index == _total - 1 ? 'Lihat hasil' : 'Soal berikutnya',
              onPressed: _next,
            )
          : AppButton(
              label: 'Kirim jawaban',
              onPressed: _selected == null ? null : _submit,
            ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Soal ${_index + 1} dari $_total',
                    style: AppText.sans(size: 14, weight: FontWeight.w600)),
              ),
              Text(ReadingDummy.storyTitle,
                  style: AppText.sans(size: 13, color: AppColors.textSecondary)),
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
          Text(_q.question, style: AppText.h2.copyWith(height: 1.35)),
          const SizedBox(height: 20),
          for (var i = 0; i < _q.options.length; i++)
            AnswerOption(
              label: _q.options[i],
              state: _optionState(i),
              onTap: _submitted ? null : () => setState(() => _selected = i),
            ),
          if (_submitted) ...[
            const SizedBox(height: 12),
            AnswerFeedback(
              correct: correct,
              message: correct ? _q.explanation : (_q.wrongHint ?? _q.explanation),
            ),
          ],
        ],
      ),
    );
  }
}
