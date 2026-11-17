import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/reading/application/reading_session.dart';
import 'package:english_day/features/reading/data/reading_models.dart';

/// Reading without a backend, for the design gallery: the dummy story and quiz,
/// graded locally with the dummy answer keys.
class DemoReadingPractice implements ReadingPractice {
  DemoReadingPractice({this.loaded = true, List<int> answered = const []}) {
    for (var i = 0; i < answered.length; i++) {
      _answers[demoStory.questions[i].id] = _grade(i, demoStory.questions[i].options[answered[i]].id);
    }
  }

  /// False keeps the story "being generated" (loading/slow/error states).
  final bool loaded;
  final _answers = <String, ReadingAnswer>{};

  static final demoStory = ReadingStory(
    exerciseId: 'demo',
    title: ReadingDummy.storyTitle,
    level: ReadingLevel.all[1],
    topicName: 'Budaya',
    paragraphs: [for (final p in ReadingDummy.paragraphs) _paragraph(p)],
    questions: [
      for (var i = 0; i < ReadingDummy.quiz.length; i++)
        ReadingQuestion(
          id: 'q$i',
          text: ReadingDummy.quiz[i].question,
          options: [
            for (var j = 0; j < ReadingDummy.quiz[i].options.length; j++)
              // The dummy options carry their own "A. " prefix; the API's do not.
              ReadingOption('q$i-o$j', ReadingDummy.quiz[i].options[j].substring(3)),
          ],
        ),
    ],
  );

  /// Dummy paragraphs mark vocabulary as [word].
  static ReadingParagraph _paragraph(String marked) {
    final highlights = <VocabHighlight>[];
    final text = StringBuffer();
    var last = 0;
    for (final m in RegExp(r'\[(.+?)\]').allMatches(marked)) {
      text.write(marked.substring(last, m.start));
      final word = m.group(1)!;
      final item = ReadingDummy.vocabulary[word]!;
      highlights.add(VocabHighlight(text.length, text.length + word.length,
          VocabEntry(word: word, meaning: item.meaning, example: item.example)));
      text.write(word);
      last = m.end;
    }
    text.write(marked.substring(last));
    return ReadingParagraph(text.toString(), highlights);
  }

  ReadingAnswer _grade(int index, String optionId) {
    final q = ReadingDummy.quiz[index];
    final correctId = 'q$index-o${q.correctIndex}';
    final correct = optionId == correctId;
    return ReadingAnswer(
      questionId: 'q$index',
      selectedOptionId: optionId,
      isCorrect: correct,
      correctOptionId: correctId,
      explanation: correct ? q.explanation : (q.wrongHint ?? q.explanation),
    );
  }

  @override
  String get meta => demoStory.meta;

  @override
  ReadingStory? get story => loaded ? demoStory : null;

  @override
  Future<ReadingStory> load() async => demoStory;

  @override
  Map<String, ReadingAnswer> get answers => _answers;

  @override
  int get nextQuestionIndex => _answers.length.clamp(0, demoStory.questions.length - 1);

  @override
  Future<ReadingAnswer> answer(ReadingQuestion question, String optionId) async =>
      _answers[question.id] = _grade(demoStory.questions.indexOf(question), optionId);

  ReadingSummary get summary => ReadingSummary(
      correct: _answers.values.where((a) => a.isCorrect).length,
      total: demoStory.questions.length);

  @override
  Future<ReadingSummary> finish() async => summary;

  @override
  Future<void> cancel() async {}
}
