import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/features/writing/data/writing_result.dart';

/// A saved Writing attempt (`GET /attempts/{id}`), used to resume from the dashboard.
class WritingAttempt {
  const WritingAttempt({
    required this.attemptId,
    required this.exerciseId,
    required this.status,
    required this.revision,
    required this.text,
    required this.activeJobIds,
    required this.evaluation,
  });

  factory WritingAttempt.fromJson(Map<String, dynamic> json) {
    final attempt = json['attempt'] as Map<String, dynamic>;
    final draft = json['draft'] as Map<String, dynamic>?;
    return WritingAttempt(
      attemptId: attempt['attempt_id'] as String,
      exerciseId: attempt['exercise_id'] as String,
      status: attempt['status'] as String,
      revision: attempt['revision'] as int,
      text: (draft?['response_text'] as String?) ?? '',
      activeJobIds: [
        for (final j in (json['active_jobs'] as List?) ?? const [])
          (j as Map<String, dynamic>)['job_id'] as String,
      ],
      evaluation: json['evaluation'] as Map<String, dynamic>?,
    );
  }

  final String attemptId;
  final String exerciseId;

  /// in_progress | submitted | evaluating | completed | failed | cancelled
  final String status;
  final int revision;
  final String text;
  final List<String> activeJobIds;
  final Map<String, dynamic>? evaluation;

  bool get isEditable => status == 'in_progress';
  bool get isEvaluating => status == 'submitted' || status == 'evaluating';

  WritingResult? get result => status == 'completed' && evaluation != null
      ? WritingResult.fromEvaluation(text, evaluation!)
      : null;
}

/// Writing endpoints. Every POST takes the caller's [ApiClient.newIdempotencyKey]
/// so a retried step reuses its key and the backend does not repeat the work.
class WritingRepository {
  WritingRepository(this._api);
  final ApiClient _api;

  /// `POST /writing/exercises` with a random topic. Returns the exercise id and
  /// the generation job to wait for.
  Future<({String exerciseId, String jobId})> createExercise(String key) async {
    final body = await _api.post(
      '/writing/exercises',
      data: {
        'difficulty': 'intermediate',
        'topic': {'mode': 'random'},
      },
      idempotencyKey: key,
    ) as Map<String, dynamic>;
    return (
      exerciseId: body['exercise_id'] as String,
      jobId: (body['job'] as Map<String, dynamic>)['job_id'] as String,
    );
  }

  /// `POST /exercises/{id}/attempts`: a blank attempt.
  Future<({String attemptId, int revision})> startAttempt(String exerciseId, String key) async {
    final body = await _api.post('/exercises/$exerciseId/attempts',
        data: <String, dynamic>{}, idempotencyKey: key) as Map<String, dynamic>;
    final attempt = body['attempt'] as Map<String, dynamic>;
    return (attemptId: attempt['attempt_id'] as String, revision: attempt['revision'] as int);
  }

  /// `PATCH /attempts/{id}/draft`. Returns the new revision.
  Future<int> saveDraft(String attemptId, int revision, String text) async {
    final body = await _api.patch('/attempts/$attemptId/draft', data: {
      'revision': revision,
      'draft': {'skill': 'writing', 'response_text': text},
    }) as Map<String, dynamic>;
    return body['revision'] as int;
  }

  /// `POST /attempts/{id}/submit`: either graded at once (evaluation) or queued (job).
  Future<({Map<String, dynamic>? evaluation, String? jobId})> submit(
      String attemptId, int revision, String key) async {
    final body = await _api.post('/attempts/$attemptId/submit',
        data: {'revision': revision}, idempotencyKey: key) as Map<String, dynamic>;
    return (
      evaluation: body['evaluation'] as Map<String, dynamic>?,
      jobId: (body['job'] as Map<String, dynamic>?)?['job_id'] as String?,
    );
  }

  Future<Map<String, dynamic>> evaluation(String attemptId) async =>
      await _api.get('/attempts/$attemptId/evaluation') as Map<String, dynamic>;

  Future<WritingAttempt> attempt(String attemptId) async => WritingAttempt.fromJson(
      await _api.get('/attempts/$attemptId') as Map<String, dynamic>);

  /// `POST /attempts/{id}/cancel`: stops the attempt and its pending AI work.
  Future<void> cancelAttempt(String attemptId) =>
      _api.post('/attempts/$attemptId/cancel', idempotencyKey: ApiClient.newIdempotencyKey());

  /// `POST /jobs/{id}/cancel`.
  Future<void> cancelJob(String jobId) =>
      _api.post('/jobs/$jobId/cancel', idempotencyKey: ApiClient.newIdempotencyKey());

  Future<Job> waitJob(String jobId, {bool Function()? isCancelled}) =>
      waitForJob(_api, jobId, isCancelled: isCancelled);
}

final writingRepositoryProvider =
    Provider<WritingRepository>((ref) => WritingRepository(ref.watch(apiClientProvider)));
