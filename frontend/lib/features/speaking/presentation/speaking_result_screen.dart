import 'package:flutter/material.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/speaking/data/speaking_repository.dart';
import 'package:english_day/features/speaking/presentation/speaking_screen.dart';

/// The AI's evaluation of a finished conversation. There is no design for it yet,
/// so it reuses the result patterns of Listening/Reading (score badge, cards).
class SpeakingResultScreen extends StatefulWidget {
  const SpeakingResultScreen({super.key, required this.load});

  /// Waits for and fetches the evaluation (it is computed after "Akhiri").
  final Future<SpeakingEvaluation> Function() load;

  @override
  State<SpeakingResultScreen> createState() => _SpeakingResultScreenState();
}

class _SpeakingResultScreenState extends State<SpeakingResultScreen> {
  SpeakingEvaluation? _evaluation;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _failed = false);
    try {
      final evaluation = await widget.load();
      if (mounted) setState(() => _evaluation = evaluation);
    } catch (e) {
      if (!mounted || (e is ApiException && e.isSessionEnded)) return;
      setState(() => _failed = true);
    }
  }

  /// 4.5 -> "4,5", 6.0 -> "6".
  static String _number(double value) => value == value.roundToDouble()
      ? value.toInt().toString()
      : value.toString().replaceAll('.', ',');

  @override
  Widget build(BuildContext context) {
    final evaluation = _evaluation;
    return AppScaffold(
      title: 'Hasil Speaking',
      bottom: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppButton(
            label: 'Latihan lagi',
            onPressed: () => Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => const SpeakingScreen())),
          ),
          const SizedBox(height: 8),
          AppButton.secondary(
            label: 'Kembali ke dashboard',
            onPressed: () => Navigator.of(context).popUntil((route) => route.isFirst),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          if (_failed) ...[
            StatusBanner.timeout(onAction: _load),
            const SizedBox(height: 24),
          ],
          if (evaluation == null && !_failed) ...[
            Text('Menilai percakapanmu…', style: AppText.h3),
            const SizedBox(height: 20),
            const SkeletonParagraph(groups: 2),
          ],
          if (evaluation != null) ..._buildResult(evaluation),
        ],
      ),
    );
  }

  List<Widget> _buildResult(SpeakingEvaluation evaluation) {
    final overall = evaluation.overallScore;
    final max = evaluation.maxScore;
    return [
      Text('Hasil latihan', style: AppText.h3.copyWith(fontSize: 20)),
      const SizedBox(height: 8),
      if (overall != null && max != null)
        Align(
          alignment: Alignment.centerLeft,
          child: ScoreBadge('${_number(overall)}/${_number(max)}'),
        )
      else
        Text('Nilai keseluruhan muncul setelah semua aspek bisa dinilai.', style: AppText.body),
      if (evaluation.summary case final summary? when summary.isNotEmpty) ...[
        const SizedBox(height: 12),
        Text(summary, style: AppText.body),
      ],
      const SizedBox(height: 20),
      for (final c in evaluation.criteria)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(c.label, style: AppText.sans(size: 16, weight: FontWeight.w600)),
                    ),
                    if (c.assessed && c.maxScore != null)
                      Text('${_number(c.score!)}/${_number(c.maxScore!)}',
                          style: AppText.sans(
                              size: 16, weight: FontWeight.w700, color: AppColors.primary))
                    else
                      Text('Belum dinilai', style: AppText.small),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  c.assessed
                      ? c.feedback
                      : 'Aspek ini butuh penilaian dari rekaman suara, yang belum tersedia.',
                  style: AppText.sans(size: 14, color: AppColors.textSecondary, height: 1.45),
                ),
              ],
            ),
          ),
        ),
      const SizedBox(height: 4),
      Text('Nilai latihan untuk belajar, bukan skor IELTS resmi.', style: AppText.small),
    ];
  }
}
