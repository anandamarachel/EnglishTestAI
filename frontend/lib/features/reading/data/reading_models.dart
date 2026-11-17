import 'package:english_day/core/text/text_span_offsets.dart';

/// Level chips on the settings screen and the backend difficulty they request.
class ReadingLevel {
  const ReadingLevel(this.name, this.cefr, this.difficulty);
  final String name;
  final String cefr;

  /// beginner | intermediate | advanced
  final String difficulty;

  static const all = [
    ReadingLevel('Easy', 'A2', 'beginner'),
    ReadingLevel('Medium', 'B1', 'intermediate'),
    ReadingLevel('Hard', 'B2', 'advanced'),
  ];

  static ReadingLevel byDifficulty(String difficulty) =>
      all.firstWhere((l) => l.difficulty == difficulty, orElse: () => all[1]);
}

/// Topic chips from the design. Names match the backend topic catalog; "Acak" is random.
const readingTopics = ['Sekolah', 'Olahraga', 'Teknologi', 'Budaya', 'Alam', 'Acak'];
const randomTopic = 'Acak';

/// What the student picked on the settings screen.
class ReadingRequest {
  const ReadingRequest({required this.level, required this.topic});
  final ReadingLevel level;

  /// A [readingTopics] name, or null for random.
  final String? topic;
}

/// One highlighted word in a paragraph: UTF-16 [start, end) and its vocabulary entry.
class VocabHighlight {
  const VocabHighlight(this.start, this.end, this.vocab);
  final int start;
  final int end;
  final VocabEntry vocab;
}

class ReadingParagraph {
  const ReadingParagraph(this.text, [this.highlights = const []]);
  final String text;

  /// Sorted, non-overlapping.
  final List<VocabHighlight> highlights;
}

class VocabEntry {
  const VocabEntry({required this.word, required this.meaning, required this.example});
  final String word;
  final String meaning;
  final String example;
}

class ReadingOption {
  const ReadingOption(this.id, this.text);
  final String id;
  final String text;
}

class ReadingQuestion {
  const ReadingQuestion({required this.id, required this.text, required this.options});
  final String id;
  final String text;
  final List<ReadingOption> options;

  ReadingOption? option(String? id) {
    for (final o in options) {
      if (o.id == id) return o;
    }
    return null;
  }
}

/// A ready Reading exercise: the story (with vocabulary) and its quiz.
class ReadingStory {
  const ReadingStory({
    required this.exerciseId,
    required this.title,
    required this.level,
    required this.topicName,
    required this.paragraphs,
    required this.questions,
  });

  final String exerciseId;
  final String title;
  final ReadingLevel level;
  final String topicName;
  final List<ReadingParagraph> paragraphs;
  final List<ReadingQuestion> questions;

  /// "Medium · Budaya"
  String get meta => '${level.name} · $topicName';

  /// From `GET /exercises/{id}` and `GET /exercises/{id}/vocabulary`.
  factory ReadingStory.fromJson(Map<String, dynamic> exercise, Map<String, dynamic>? vocabulary) {
    final content = exercise['content'] as Map<String, dynamic>;
    final topic = exercise['topic'] as Map<String, dynamic>?;
    return ReadingStory(
      exerciseId: exercise['exercise_id'] as String,
      title: (exercise['title'] as String?) ?? 'Reading',
      level: ReadingLevel.byDifficulty(exercise['difficulty'] as String),
      topicName: (topic?['name'] as String?) ?? randomTopic,
      paragraphs: _splitPassage(content['passage'] as String, [
        for (final item in (vocabulary?['items'] as List?) ?? const [])
          _VocabItem.fromJson(item as Map<String, dynamic>),
      ]),
      questions: [
        for (final q in exercise['questions'] as List)
          if ((q as Map<String, dynamic>)['question_type'] == 'multiple_choice')
            ReadingQuestion(
              id: q['question_id'] as String,
              text: q['question_text'] as String,
              options: [
                for (final o in q['options'] as List)
                  ReadingOption((o as Map<String, dynamic>)['option_id'] as String,
                      o['option_text'] as String),
              ],
            ),
      ],
    );
  }
}

class _VocabItem {
  const _VocabItem(this.entry, this.spans);
  final VocabEntry entry;
  final List<(int, int, String)> spans; // code points start, end, original

  factory _VocabItem.fromJson(Map<String, dynamic> json) => _VocabItem(
        VocabEntry(
          word: json['word_or_phrase'] as String,
          meaning: json['meaning'] as String,
          example: json['example_sentence'] as String,
        ),
        [
          for (final s in (json['occurrences'] as List?) ?? const [])
            (
              (s as Map<String, dynamic>)['start'] as int,
              s['end'] as int,
              s['original'] as String,
            ),
        ],
      );
}

/// Splits the passage into paragraphs (blank lines) and places each vocabulary
/// occurrence (code-point span over the whole passage) inside its paragraph.
/// Spans that do not match the passage or overlap another are ignored.
List<ReadingParagraph> _splitPassage(String passage, List<_VocabItem> vocabulary) {
  final offsets = codePointToUtf16Offsets(passage);
  final marks = <(int, int, VocabEntry)>[];
  for (final item in vocabulary) {
    for (final (start, end, original) in item.spans) {
      if (start < 0 || end <= start || end >= offsets.length) continue;
      final range = (offsets[start], offsets[end]);
      if (passage.substring(range.$1, range.$2) != original) continue;
      marks.add((range.$1, range.$2, item.entry));
    }
  }
  marks.sort((a, b) => a.$1.compareTo(b.$1));

  final paragraphs = <ReadingParagraph>[];
  void addParagraph(int from, int to) {
    final raw = passage.substring(from, to);
    final text = raw.trim();
    if (text.isEmpty) return;
    final start = from + raw.indexOf(text);
    final end = start + text.length;
    final highlights = <VocabHighlight>[];
    var cursor = start;
    for (final (s, e, vocab) in marks) {
      if (s < cursor || e > end) continue;
      highlights.add(VocabHighlight(s - start, e - start, vocab));
      cursor = e;
    }
    paragraphs.add(ReadingParagraph(text, highlights));
  }

  var from = 0;
  for (final gap in RegExp(r'\n\s*\n').allMatches(passage)) {
    addParagraph(from, gap.start);
    from = gap.end;
  }
  addParagraph(from, passage.length);
  return paragraphs;
}

/// The server's grading of one quiz answer (`AnswerFeedback`).
class ReadingAnswer {
  const ReadingAnswer({
    required this.questionId,
    required this.selectedOptionId,
    required this.isCorrect,
    required this.correctOptionId,
    required this.explanation,
  });

  factory ReadingAnswer.fromFeedback(Map<String, dynamic> feedback, String? selectedOptionId) =>
      ReadingAnswer(
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

/// Final quiz result.
class ReadingSummary {
  const ReadingSummary({required this.correct, required this.total});
  final int correct;
  final int total;
}
