import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/answer_widgets.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/dashboard/presentation/dashboard_screen.dart';
import 'package:english_day/features/reading/presentation/reading_settings_screen.dart';

// ------------------------------------------------------------------ Result
class ReadingResultScreen extends StatelessWidget {
  const ReadingResultScreen({super.key, required this.answers});
  final List<int> answers;

  @override
  Widget build(BuildContext context) {
    const quiz = ReadingDummy.quiz;
    final score = [for (var i = 0; i < quiz.length; i++) answers[i] == quiz[i].correctIndex]
        .where((e) => e)
        .length;
    return AppScaffold(
      title: 'Hasil kuis',
      bottom: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppButton(
            label: 'Buat cerita baru',
            onPressed: () => Navigator.of(context).pushReplacement(
              MaterialPageRoute(builder: (_) => const ReadingSettingsScreen()),
            ),
          ),
          const SizedBox(height: 8),
          AppButton.secondary(
            label: 'Kembali ke dashboard',
            onPressed: () => Navigator.of(context).pushAndRemoveUntil(
              MaterialPageRoute(builder: (_) => const DashboardScreen()),
              (_) => false,
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          const MetaLabel('${ReadingDummy.storyTitle} · Medium'),
          const SizedBox(height: 8),
          Align(alignment: Alignment.centerLeft, child: ScoreBadge('$score/${quiz.length}')),
          const SizedBox(height: 12),
          Text(
            score == quiz.length
                ? 'Sempurna! Semua jawaban kamu benar.'
                : score >= 3
                    ? 'Bagus! $score jawaban kamu benar.'
                    : '$score jawaban benar. Yuk, baca lagi ceritanya.',
            style: AppText.sans(size: 15, color: AppColors.textSecondary),
          ),
          const SizedBox(height: 12),
          for (var i = 0; i < quiz.length; i++)
            _ResultItem(
              question: quiz[i],
              correct: answers[i] == quiz[i].correctIndex,
            ),
        ],
      ),
    );
  }
}

class _ResultItem extends StatelessWidget {
  const _ResultItem({required this.question, required this.correct});
  final QuizQuestion question;
  final bool correct;

  @override
  Widget build(BuildContext context) {
    final color = correct ? AppColors.success : AppColors.error;
    return InkWell(
      onTap: () => showModalBottomSheet(
        context: context,
        builder: (ctx) => Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(question.question, style: AppText.h3),
              const SizedBox(height: 16),
              AnswerOption(
                label: question.options[question.correctIndex],
                state: OptionState.correct,
              ),
              AnswerFeedback(correct: correct, message: question.explanation),
              const SizedBox(height: 16),
              AppButton.secondary(label: 'Tutup', onPressed: () => Navigator.pop(ctx)),
            ],
          ),
        ),
      ),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: AppColors.divider)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: color, width: 1.4),
              ),
              child: Icon(correct ? Icons.check : Icons.close, size: 13, color: color),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(question.question,
                      style: AppText.sans(size: 15, weight: FontWeight.w600, height: 1.4)),
                  const SizedBox(height: 4),
                  Text('${correct ? 'Benar' : 'Belum tepat'} · ${question.reviewAnswer}',
                      style: AppText.small),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: AppColors.primary, size: 20),
          ],
        ),
      ),
    );
  }
}
