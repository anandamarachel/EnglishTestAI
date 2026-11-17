import 'package:english_day/core/models/choice_question.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/listening/application/listening_audio.dart';
import 'package:english_day/features/listening/application/listening_session.dart';
import 'package:english_day/features/listening/data/listening_models.dart';

/// Listening without a backend or sound, for the design gallery: the dummy
/// conversation, a simulated player and local grading with the dummy keys.
class DemoListeningPractice implements ListeningPractice {
  DemoListeningPractice({bool loaded = true, List<int?> answers = const [], bool submitted = false})
      : _loaded = loaded {
    for (var i = 0; i < answers.length; i++) {
      final a = answers[i];
      if (a != null) _selections['q$i'] = 'q$i-o$a';
    }
    if (loaded) {
      _audio = SimulatedListeningAudio(
        duration: const Duration(seconds: ListeningDummy.durationSec),
        position: const Duration(seconds: 42),
      );
    }
    if (submitted) _result = _grade();
  }

  bool _loaded;
  ListeningAudio? _audio;
  ListeningResult? _result;
  final _selections = <String, String>{};

  static final demoExercise = ListeningExercise(
    exerciseId: 'demo',
    title: ListeningDummy.title,
    level: 'Medium',
    topicName: 'Sekolah',
    audioMediaId: 'demo',
    audioMimeType: 'audio/wav',
    duration: const Duration(seconds: ListeningDummy.durationSec),
    questions: [
      for (var i = 0; i < ListeningDummy.questions.length; i++)
        ChoiceQuestion(
          id: 'q$i',
          text: ListeningDummy.questions[i].question,
          options: [
            for (var j = 0; j < ListeningDummy.questions[i].options.length; j++)
              // The dummy options carry their own "A. " prefix; the API's do not.
              ChoiceOption('q$i-o$j', ListeningDummy.questions[i].options[j].substring(3)),
          ],
        ),
    ],
  );

  ListeningResult _grade() {
    final answers = <String, GradedAnswer>{};
    for (var i = 0; i < ListeningDummy.questions.length; i++) {
      final q = ListeningDummy.questions[i];
      final correctId = 'q$i-o${q.correctIndex}';
      answers['q$i'] = GradedAnswer(
        questionId: 'q$i',
        selectedOptionId: _selections['q$i'],
        isCorrect: _selections['q$i'] == correctId,
        correctOptionId: correctId,
        explanation: q.explanation,
      );
    }
    return ListeningResult(
      correct: answers.values.where((a) => a.isCorrect).length,
      total: answers.length,
      answers: answers,
      transcript: [
        for (final (line, evidence) in ListeningDummy.transcript)
          TranscriptLine(line, evidence: evidence),
      ],
    );
  }

  @override
  String get meta => demoExercise.meta;
  @override
  ListeningExercise? get exercise => _loaded ? demoExercise : null;
  @override
  ListeningAudio? get audio => _audio;
  @override
  Map<String, String> get selections => _selections;
  @override
  ListeningResult? get result => _result;

  @override
  Future<void> load() async {
    _loaded = true;
    _audio ??= SimulatedListeningAudio(
        duration: const Duration(seconds: ListeningDummy.durationSec));
  }

  @override
  Future<void> reloadAudio() async {}

  @override
  void select(String questionId, String optionId) => _selections[questionId] = optionId;

  @override
  Future<ListeningResult> submit() async => _result = _grade();

  @override
  Future<void> cancel() async {}

  @override
  void dispose() => _audio?.dispose();
}
