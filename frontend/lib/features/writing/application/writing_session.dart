import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/features/writing/data/writing_repository.dart';
import 'package:english_day/features/writing/data/writing_result.dart';

/// The AI evaluation finished with status failed/cancelled.
class WritingEvaluationFailed implements Exception {
  const WritingEvaluationFailed(this.status);
  final String status;
}

/// Runs "Cek grammar" against the backend, which needs several steps:
/// generate a Writing exercise (AI job) → start an attempt → save the text as the
/// draft → submit → wait for the AI evaluation job → fetch the evaluation.
///
/// One session lives as long as the Writing screen. It remembers how far it got,
/// so "Coba lagi" after an error continues from the failed step (re-sending the same
/// Idempotency-Key, so nothing is created twice), and later checks reuse the
/// exercise with a new attempt.
class WritingSession {
  WritingSession(this._repo);
  final WritingRepository _repo;

  String? _exerciseId;
  String? _exerciseJobId; // generation not yet confirmed finished
  String? _exerciseKey;
  String? _attemptKey;

  String? _attemptId; // editable attempt
  int _revision = 0;

  _Submit? _submit; // submit sent but no response yet (retry with the same key)
  _Evaluating? _evaluating; // submitted, waiting for the AI

  int _run = 0;

  /// Continue a saved attempt (dashboard "Lanjutkan").
  void resumeFrom(WritingAttempt attempt) {
    _exerciseId = attempt.exerciseId;
    if (attempt.isEditable) {
      _attemptId = attempt.attemptId;
      _revision = attempt.revision;
    } else if (attempt.isEvaluating) {
      final jobId = attempt.activeJobIds.isEmpty ? null : attempt.activeJobIds.first;
      _evaluating = _Evaluating(attempt.attemptId, attempt.text, jobId);
    }
  }

  /// Checks [text] and returns the AI corrections.
  ///
  /// Throws [ApiException] (network/server), [JobFailedException] /
  /// [WritingEvaluationFailed] (AI failed), [JobTimeoutException] (AI still busy;
  /// calling again keeps waiting) or [OperationCancelledException] after [cancel].
  Future<WritingResult> check(String text) async {
    final run = ++_run;
    bool cancelled() => run != _run;

    // The text changed after an unfinished submit/evaluation: start a new attempt.
    if (_evaluating != null && _evaluating!.text != text) _evaluating = null;
    if (_submit != null && _submit!.text != text) _submit = null;

    if (_evaluating == null) {
      if (_submit == null) {
        await _ensureExercise(cancelled);
        await _ensureAttempt();
        await _saveDraft(text);
        _submit = _Submit(_attemptId!, _revision, text, ApiClient.newIdempotencyKey());
      }
      final submit = _submit!;
      final out = await _repo.submit(submit.attemptId, submit.revision, submit.key);
      _submit = null;
      _attemptId = null; // submitted: the next check needs a new attempt
      _evaluating = _Evaluating(submit.attemptId, text, out.jobId, out.evaluation);
    }
    return _awaitEvaluation(cancelled);
  }

  /// Stops waiting and cancels the pending AI work on the server (best effort).
  Future<void> cancel() async {
    _run++;
    final evaluating = _evaluating;
    final generating = _exerciseJobId;
    _evaluating = null;
    _submit = null;
    try {
      if (evaluating != null) {
        await _repo.cancelAttempt(evaluating.attemptId);
      } else if (generating != null) {
        _exerciseId = null;
        _exerciseJobId = null;
        await _repo.cancelJob(generating);
      }
    } on ApiException {
      // Already finished or unreachable: nothing else to do.
    }
  }

  Future<void> _ensureExercise(bool Function() cancelled) async {
    if (_exerciseId == null) {
      final created = await _repo.createExercise(_exerciseKey ??= ApiClient.newIdempotencyKey());
      _exerciseKey = null;
      _exerciseId = created.exerciseId;
      _exerciseJobId = created.jobId;
    }
    final jobId = _exerciseJobId;
    if (jobId == null) return;
    try {
      await _repo.waitJob(jobId, isCancelled: cancelled);
    } on JobFailedException {
      _exerciseId = null; // generate a new one next time
      _exerciseJobId = null;
      rethrow;
    }
    _exerciseJobId = null;
  }

  Future<void> _ensureAttempt() async {
    if (_attemptId != null) return;
    final started =
        await _repo.startAttempt(_exerciseId!, _attemptKey ??= ApiClient.newIdempotencyKey());
    _attemptKey = null;
    _attemptId = started.attemptId;
    _revision = started.revision;
  }

  Future<void> _saveDraft(String text) async {
    try {
      _revision = await _repo.saveDraft(_attemptId!, _revision, text);
    } on ApiException catch (e) {
      if (e.statusCode != 409) rethrow;
      // Stale revision (an earlier save's response was lost) or the attempt is no
      // longer editable: re-read it, then save again or start a fresh attempt.
      final current = await _repo.attempt(_attemptId!);
      if (current.isEditable) {
        _revision = current.revision;
      } else {
        _attemptId = null;
        await _ensureAttempt();
      }
      _revision = await _repo.saveDraft(_attemptId!, _revision, text);
    }
  }

  Future<WritingResult> _awaitEvaluation(bool Function() cancelled) async {
    final evaluating = _evaluating!;
    var evaluation = evaluating.evaluation;
    if (evaluation == null || !_isFinal(evaluation)) {
      final jobId = evaluating.jobId;
      if (jobId != null) {
        try {
          await _repo.waitJob(jobId, isCancelled: cancelled);
        } on JobFailedException {
          _evaluating = null;
          rethrow;
        }
      }
      evaluation = await _repo.evaluation(evaluating.attemptId);
    }
    final status = evaluation['status'] as String?;
    if (status != 'completed') {
      if (_isFinal(evaluation)) {
        _evaluating = null;
        throw WritingEvaluationFailed(status ?? 'failed');
      }
      throw JobTimeoutException(evaluating.jobId ?? evaluating.attemptId);
    }
    _evaluating = null;
    return WritingResult.fromEvaluation(evaluating.text, evaluation);
  }

  static bool _isFinal(Map<String, dynamic> evaluation) =>
      const {'completed', 'failed', 'cancelled'}.contains(evaluation['status']);
}

class _Submit {
  const _Submit(this.attemptId, this.revision, this.text, this.key);
  final String attemptId;
  final int revision;
  final String text;
  final String key;
}

class _Evaluating {
  const _Evaluating(this.attemptId, this.text, this.jobId, [this.evaluation]);
  final String attemptId;
  final String text;
  final String? jobId;
  final Map<String, dynamic>? evaluation;
}
