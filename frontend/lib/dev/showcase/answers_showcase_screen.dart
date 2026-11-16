import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/answer_widgets.dart';
import 'package:english_day/core/widgets/common.dart';

// ------------------------------------ Komponen: jawaban & percakapan
class AnswersShowcaseScreen extends StatelessWidget {
  const AnswersShowcaseScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Komponen',
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text('Pilihan jawaban', style: AppText.h3),
          const SizedBox(height: 12),
          const AnswerOption(label: 'A. To fix the roof'),
          const AnswerOption(label: 'B. To get his kite back', state: OptionState.selected),
          const AnswerOption(label: 'B. To get his kite back', state: OptionState.correct),
          const AnswerOption(label: 'C. To watch the festival', state: OptionState.wrong),
          const AnswerFeedback(
            correct: true,
            message: 'Benar, Daeng mengambil kembali layang-layangnya.',
          ),
          const SizedBox(height: 16),
          Text('Percakapan', style: AppText.h3),
          const SizedBox(height: 12),
          ChatBubble(text: 'What did you do last weekend?', fromAi: true, onSpeaker: () {}),
          const ChatBubble(text: 'I went to the beach.', fromAi: false),
        ],
      ),
    );
  }
}
