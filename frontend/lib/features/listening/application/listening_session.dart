import 'dart:async';

import 'package:english_day/core/models/choice_question.dart';
import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/features/listening/application/listening_audio.dart';
import 'package:english_day/features/listening/data/listening_models.dart';
import 'package:english_day/features/listening/data/listening_repository.dart';

/// The exercise is ready but its audio could not be downloaded or opened.
class ListeningAudioException implements Exception {
  const ListeningAudioException(this.cause);
  final Object cause;

  @override
  String toString() => 'ListeningAudioException($cause)';
}

/// What the Listening screen needs. [ListeningSession] talks to the backend; the
/// design gallery uses a demo version.
abstract interface class ListeningPractice {
  /// "Medium · Sekolah"; the topic is known once the exercise is ready.
  String get meta;
  ListeningExercise? get exercise;

  /// Null until the audio is loaded.
  ListeningAudio? get audio;

  /// Selected option id by question id.
  Map<String, String> get selections;

  /// Set once submitted (or when reopening a finished attempt).
  ListeningResult? get result;

  /// Prepares the exercise, the attempt and the audio. Throws
  /// [ListeningAudioException] when only the audio failed (retry with [reloadAudio]).
  Future<void> load();
  Future<void> reloadAudio();

  /// Remembers the answer and saves it to the server in the background.
  void select(String questionId, String optionId);

  /// Sends every answer, then fetches the grading and the unlocked transcript.
  Future<ListeningResult> submit();

  /// Stops waiting for the exercise (and cancels its generation on the server).
  Future<void> cancel();
  void dispose();
}

/// Listening against the backend: generate exercise (AI job, including the audio)
/// → start attempt → download the private audio → save answers and playback
/// position as a draft → submit all answers → feedback per question + transcript.
class ListeningSession implements ListeningPractice {
  ListeningSession(this._repo, this._loadAudio, {String? resumeAttemptId})
      : _resumeAttemptId = resumeAttemptId;

  static const _saveDelay = Duration(milliseconds: 600);

  final ListeningRepository _repo;
  final ListeningAudioLoader _loadAudio;
  final String? _resumeAttemptId;

  String? _exerciseId;
  String? _generateJobId;
  String? _exerciseKey;
  String? _attemptKey;
  String? _attemptId;
  int _revision = 0;
  bool _submitted = false;
  Duration _resumePosition = Duration.zero;
  ListeningExercise? _exercise;
  ListeningAudio? _audio;
  ListeningResult? _result;
  final _selections = <String, String>{};
  Timer? _saveTimer;
  Future<void> _saving = Future.value();
  (int, String)? _submitKey; // revision, key
  int _run = 0;

  @override
  String get meta => _exercise?.meta ?? 'Medium · Acak';
  @override
  ListeningExercise? get exercise => _exercise;
  @override
  ListeningAudio? get audio => _audio;
  @override
  Map<String, String> get selections => Map.unmodifiable(_selections);
  @override
  ListeningResult? get result => _result;

  @override
  Future<void> load() async {
    final run = ++_run;
    bool cancelled() => run != _run;
    if (_exercise == null) {
      final resumeId = _resumeAttemptId;
      if (resumeId != null) {
        await _resume(resumeId);
        if (_result != null) return;
      } else {
        await _generate(cancelled);
      }
    }
    if (_audio == null) await reloadAudio();
  }

  Future<void> _generate(bool Function() cancelled) async {
    if (_exerciseId == null) {
      final created = await _repo.createExercise(_exerciseKey ??= ApiClient.newIdempotencyKey());
      _exerciseKey = null;
      _exerciseId = created.exerciseId;
      _generateJobId = created.jobId;
    }
    final jobId = _generateJobId;
    if (jobId != null) {
      try {
        await _repo.waitJob(jobId, isCancelled: cancelled);
      } on JobFailedException {
        _exerciseId = null; // generate a new one next time
        _generateJobId = null;
        rethrow;
      }
      _generateJobId = null;
    }
    final exercise = await _repo.exercise(_exerciseId!);
    final started =
        await _repo.startAttempt(exercise.exerciseId, _attemptKey ??= ApiClient.newIdempotencyKey());
    _attemptKey = null;
    _attemptId = started.attemptId;
    _revision = started.revision;
    _exercise = exercise;
  }

  Future<void> _resume(String attemptId) async {
    final attempt = await _repo.attempt(attemptId);
    _attemptId = attempt.attemptId;
    _revision = attempt.revision;
    _selections.addAll(attempt.selections);
    _resumePosition = Duration(milliseconds: attempt.playbackPositionMs);
    _exercise = attempt.exercise;
    if (!attempt.isEditable) {
      _submitted = true;
      if (attempt.status == 'completed') _result = await _fetchResult(attempt.evaluation);
    }
  }

  @override
  Future<void> reloadAudio() async {
    final exercise = _exercise!;
    try {
      final bytes = await _repo.audio(exercise.audioMediaId);
      final audio = await _loadAudio(bytes, exercise.audioMimeType, exercise.duration);
      if (_resumePosition > Duration.zero) await audio.seek(_resumePosition);
      _audio?.dispose();
      _audio = audio;
    } on ApiException catch (e) {
      if (e.isSessionEnded) rethrow;
      throw ListeningAudioException(e);
    } catch (e) {
      throw ListeningAudioException(e);
    }
  }

  @override
  void select(String questionId, String optionId) {
    _selections[questionId] = optionId;
    _saveTimer?.cancel();
    _saveTimer = Timer(_saveDelay, _queueSave);
  }

  /// Saves are chained so two never use the same revision.
  Future<void> _queueSave() => _saving = _saving.then((_) => _save()).catchError((Object _) {
        // Best effort in the background; submit saves again and reports errors.
      });

  Future<void> _save() async {
    if (_submitted) return;
    final attemptId = _attemptId!;
    Future<int> send() => _repo.saveDraft(
          attemptId: attemptId,
          revision: _revision,
          playbackPositionMs: (_audio?.position ?? _resumePosition).inMilliseconds,
          selections: _selections,
        );
    try {
      _revision = await send();
    } on ApiException catch (e) {
      if (e.statusCode != 409) rethrow;
      // Stale revision, or already submitted (e.g. a lost submit response).
      final current = await _repo.attempt(attemptId);
      if (!current.isEditable) {
        _submitted = true;
        return;
      }
      _revision = current.revision;
      _revision = await send();
    }
  }

  @override
  Future<ListeningResult> submit() async {
    final attemptId = _attemptId!;
    _saveTimer?.cancel();
    await _saving;
    await _save();
    Map<String, dynamic>? evaluation;
    if (!_submitted) {
      final key = _submitKey?.$1 == _revision ? _submitKey!.$2 : ApiClient.newIdempotencyKey();
      _submitKey = (_revision, key);
      final out = await _repo.submit(attemptId, _revision, key);
      _submitted = true;
      evaluation = out.evaluation;
      final jobId = out.jobId;
      if (jobId != null) await _repo.waitJob(jobId);
    }
    await _audio?.pause();
    return _result = await _fetchResult(evaluation);
  }

  Future<ListeningResult> _fetchResult(Map<String, dynamic>? evaluation) async {
    final attemptId = _attemptId!;
    if (evaluation == null || evaluation['status'] != 'completed') {
      evaluation = await _repo.evaluation(attemptId);
    }
    final questions = _exercise!.questions;
    final feedback = await Future.wait([
      for (final q in questions) _repo.feedback(attemptId, q.id),
    ]);
    final answers = {
      for (final f in feedback)
        f['question_id'] as String: GradedAnswer.fromFeedback(f, _selections[f['question_id']]),
    };
    final quiz = evaluation['quiz_summary'] as Map<String, dynamic>?;
    return ListeningResult(
      correct: (quiz?['correct_count'] as int?) ?? answers.values.where((a) => a.isCorrect).length,
      total: (quiz?['question_count'] as int?) ?? questions.length,
      answers: answers,
      transcript: transcriptLines(await _repo.transcript(attemptId)),
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

  @override
  void dispose() {
    // Keep the latest answers and position for "Lanjutkan" (best effort).
    if (_saveTimer?.isActive ?? false) {
      _saveTimer!.cancel();
      _queueSave();
    }
    _audio?.dispose();
  }
}
