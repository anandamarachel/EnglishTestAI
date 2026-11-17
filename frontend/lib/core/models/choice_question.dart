/// Multiple-choice questions as Reading and Listening exercises return them
/// (`Question` without answer keys), and the server's grading of an answer.
class ChoiceOption {
  const ChoiceOption(this.id, this.text);
  final String id;
  final String text;
}

class ChoiceQuestion {
  const ChoiceQuestion({required this.id, required this.text, required this.options});

  final String id;
  final String text;
  final List<ChoiceOption> options;

  /// Multiple-choice questions of an exercise (`questions[]`); short answers are skipped.
  static List<ChoiceQuestion> listFromJson(List<dynamic>? questions) => [
        for (final q in questions ?? const [])
          if ((q as Map<String, dynamic>)['question_type'] == 'multiple_choice')
            ChoiceQuestion(
              id: q['question_id'] as String,
              text: q['question_text'] as String,
              options: [
                for (final o in q['options'] as List)
                  ChoiceOption((o as Map<String, dynamic>)['option_id'] as String,
                      o['option_text'] as String),
              ],
            ),
      ];

  ChoiceOption? option(String? id) {
    for (final o in options) {
      if (o.id == id) return o;
    }
    return null;
  }
}

/// A, B, C, ... for option labels as in the design.
String optionLetter(int index) => String.fromCharCode(65 + index);

/// The server's grading of one answer (`AnswerFeedback`).
class GradedAnswer {
  const GradedAnswer({
    required this.questionId,
    required this.selectedOptionId,
    required this.isCorrect,
    required this.correctOptionId,
    required this.explanation,
  });

  factory GradedAnswer.fromFeedback(Map<String, dynamic> feedback, String? selectedOptionId) =>
      GradedAnswer(
        questionId: feedback['question_id'] as String,
        selectedOptionId: selectedOptionId,
        isCorrect: feedback['is_correct'] == true,
        correctOptionId: feedback['correct_option_id'] as String?,
        explanation: (feedback['explanation'] as String?) ?? '',
      );

  final String questionId;
  final String? selectedOptionId;
  final bool isCorrect;
  final String? correctOptionId;
  final String explanation;
}
