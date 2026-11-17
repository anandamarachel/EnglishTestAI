import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/features/reading/data/reading_models.dart';
import 'package:english_day/features/reading/data/reading_repository.dart';

/// What the Reading screens need: a story, answering its quiz one question at a
/// time (graded by the server), and the final score.
///
/// [ReadingSession] talks to the backend; the design gallery uses a demo version.
abstract interface class ReadingPractice {
  /// "Medium · Budaya", known before the story is ready.
  String get meta;

  /// Null until [load] finished.
  ReadingStory? get story;

  /// Generates a new story or reopens a saved attempt.
  Future<ReadingStory> load();

  /// Graded answers by question id.
  Map<String, ReadingAnswer> get answers;

  /// Where the quiz starts: the first question without an answer.
  int get nextQuestionIndex;

  Future<ReadingAnswer> answer(ReadingQuestion question, String optionId);

  /// Submits the attempt once every question is answered.
  Future<ReadingSummary> finish();

  /// Stops waiting for the story (and cancels its generation on the server).
  Future<void> cancel();
}

/// Reading against the backend: generate exercise (AI job) → fetch story and
/// vocabulary → start attempt → submit each answer (server grades it) → submit
/// the attempt for the quiz summary.
///
/// Remembers how far it got, so "Coba lagi" continues from the failed step with
/// the same Idempotency-Key and nothing is created twice.
class ReadingSession implements ReadingPractice {
  ReadingSession(this._repo, {ReadingRequest? request, String? resumeAttemptId})
      : _request = request,
        _resumeAttemptId = resumeAttemptId;

  final ReadingRepository _repo;
  final ReadingRequest? _request;
  final String? _resumeAttemptId;

  String? _exerciseId;
  String? _generateJobId;
  String? _exerciseKey;
  String? _attemptKey;
  String? _attemptId;
  int _revision = 0;
  ReadingStory? _story;
  final _answers = <String, ReadingAnswer>{};
  final _answerKeys = <String, (String optionId, int revision, String key)>{};
  String? _finishKey;
  int _run = 0;

  @override
  String get meta =>
      _story?.meta ??
      '${(_request?.level ?? ReadingLevel.all[1]).name} · ${_request?.topic ?? randomTopic}';

  @override
  ReadingStory? get story => _story;

  @override
  Map<String, ReadingAnswer> get answers => Map.unmodifiable(_answers);

  @override
  int get nextQuestionIndex {
    final questions = _story?.questions ?? const <ReadingQuestion>[];
    final i = questions.indexWhere((q) => !_answers.containsKey(q.id));
    return i < 0 ? (questions.isEmpty ? 0 : questions.length - 1) : i;
  }

  @override
  Future<ReadingStory> load() async {
    final run = ++_run;
    bool cancelled() => run != _run;
    if (_story != null) return _story!;
    final resumeId = _resumeAttemptId;
    if (resumeId != null) return _resume(resumeId);

    if (_exerciseId == null) {
      final created = await _repo.createExercise(
        difficulty: (_request?.level ?? ReadingLevel.all[1]).difficulty,
        topic: await _topicSelection(),
        key: _exerciseKey ??= ApiClient.newIdempotencyKey(),
      );
      _exerciseKey = null;
      _exerciseId = created.exerciseId;
      _generateJobId = created.jobId;
    }
    final jobId = _generateJobId;
    if (jobId != null) {
      try {
        await _repo.waitJob(jobId, isCancelled: cancelled);
      } on JobFailedException {
        _exerciseId = null; // generate a new story next time
        _generateJobId = null;
        rethrow;
      }
      _generateJobId = null;
    }
    final story = await _repo.story(_exerciseId!);
    final started =
        await _repo.startAttempt(story.exerciseId, _attemptKey ??= ApiClient.newIdempotencyKey());
    _attemptKey = null;
    _attemptId = started.attemptId;
    _revision = started.revision;
    return _story = story;
  }

  Future<Map<String, dynamic>> _topicSelection() async {
    final topic = _request?.topic;
    if (topic == null || topic == randomTopic) return {'mode': 'random'};
    final id = (await _repo.topicIds())[topic];
    return id == null ? {'mode': 'custom', 'text': topic} : {'mode': 'catalog', 'topic_id': id};
  }

  Future<ReadingStory> _resume(String attemptId) async {
    final attempt = await _repo.attempt(attemptId);
    final story = await _repo.story(attempt.exerciseId);
    _attemptId = attempt.attemptId;
    _revision = attempt.revision;
    for (final a in attempt.answers) {
      if (!a.graded) continue;
      final feedback = await _repo.feedback(attemptId, a.questionId);
      _answers[a.questionId] = ReadingAnswer.fromFeedback(feedback, a.selectedOptionId);
    }
    return _story = story;
  }

  @override
  Future<ReadingAnswer> answer(ReadingQuestion question, String optionId) async {
    final attemptId = _attemptId!;
    var pending = _answerKeys[question.id];
    if (pending == null || pending.$1 != optionId) {
      pending = (optionId, _revision, ApiClient.newIdempotencyKey());
      _answerKeys[question.id] = pending;
    }
    ({Map<String, dynamic>? feedback, String? jobId, int revision}) out;
    try {
      out = await _repo.submitAnswer(
        attemptId: attemptId,
        questionId: question.id,
        revision: pending.$2,
        optionId: optionId,
        key: pending.$3,
      );
    } on ApiException catch (e) {
      if (e.code != 'REVISION_CONFLICT') rethrow;
      // Another save moved the attempt on: re-read the revision and send again.
      _revision = (await _repo.attempt(attemptId)).revision;
      pending = (optionId, _revision, ApiClient.newIdempotencyKey());
      _answerKeys[question.id] = pending;
      out = await _repo.submitAnswer(
        attemptId: attemptId,
        questionId: question.id,
        revision: pending.$2,
        optionId: optionId,
        key: pending.$3,
      );
    }
    _answerKeys.remove(question.id);
    _revision = out.revision;
    var feedback = out.feedback;
    if (feedback == null || feedback['grading_status'] != 'graded') {
      final jobId = out.jobId;
      if (jobId != null) await _repo.waitJob(jobId);
      feedback = await _repo.feedback(attemptId, question.id);
    }
    return _answers[question.id] = ReadingAnswer.fromFeedback(feedback, optionId);
  }

  @override
  Future<ReadingSummary> finish() async {
    final attemptId = _attemptId!;
    final out =
        await _repo.submitAttempt(attemptId, _revision, _finishKey ??= ApiClient.newIdempotencyKey());
    var evaluation = out.evaluation;
    if (evaluation == null || evaluation['status'] != 'completed') {
      final jobId = out.jobId;
      if (jobId != null) await _repo.waitJob(jobId);
      evaluation = await _repo.evaluation(attemptId);
    }
    _finishKey = null;
    final quiz = evaluation['quiz_summary'] as Map<String, dynamic>?;
    final total = _story?.questions.length ?? _answers.length;
    return ReadingSummary(
      correct: (quiz?['correct_count'] as int?) ?? _answers.values.where((a) => a.isCorrect).length,
      total: (quiz?['question_count'] as int?) ?? total,
    );
  }

  @override
  Future<void> cancel() async {
    _run++;
    final jobId = _generateJobId;
    if (jobId == null) return;
    _exerciseId = null;
    _generateJobId = null;
    try {
      await _repo.cancelJob(jobId);
    } on ApiException {
      // Already finished or unreachable.
    }
  }
}
