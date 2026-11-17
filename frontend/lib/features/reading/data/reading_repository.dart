import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/features/reading/data/reading_models.dart';

/// A saved Reading attempt (`GET /attempts/{id}`), used to resume from the dashboard.
class ReadingAttempt {
  const ReadingAttempt({
    required this.attemptId,
    required this.exerciseId,
    required this.status,
    required this.revision,
    required this.answers,
  });

  factory ReadingAttempt.fromJson(Map<String, dynamic> json) {
    final attempt = json['attempt'] as Map<String, dynamic>;
    return ReadingAttempt(
      attemptId: attempt['attempt_id'] as String,
      exerciseId: attempt['exercise_id'] as String,
      status: attempt['status'] as String,
      revision: attempt['revision'] as int,
      answers: [
        for (final a in (json['answers'] as List?) ?? const [])
          (
            questionId: (a as Map<String, dynamic>)['question_id'] as String,
            selectedOptionId: a['selected_option_id'] as String?,
            graded: a['feedback_available'] == true,
          ),
      ],
    );
  }

  final String attemptId;
  final String exerciseId;

  /// in_progress | submitted | evaluating | completed | failed | cancelled
  final String status;
  final int revision;

  /// Submitted answers; feedback can be fetched for the graded ones.
  final List<({String questionId, String? selectedOptionId, bool graded})> answers;
}

/// Reading endpoints. POSTs take the caller's idempotency key so a retried step
/// reuses it.
class ReadingRepository {
  ReadingRepository(this._api);
  final ApiClient _api;

  /// `GET /topics`: catalog topic ids by name.
  Future<Map<String, String>> topicIds() async {
    final body = await _api.get('/topics') as Map<String, dynamic>;
    return {
      for (final t in body['items'] as List)
        (t as Map<String, dynamic>)['name'] as String: t['topic_id'] as String,
    };
  }

  /// `POST /reading/exercises`: 5 multiple-choice questions, as in the design.
  Future<({String exerciseId, String jobId})> createExercise({
    required String difficulty,
    required Map<String, dynamic> topic,
    required String key,
  }) async {
    final body = await _api.post(
      '/reading/exercises',
      data: {
        'difficulty': difficulty,
        'topic': topic,
        'question_count': 5,
        'question_types': ['multiple_choice'],
      },
      idempotencyKey: key,
    ) as Map<String, dynamic>;
    return (
      exerciseId: body['exercise_id'] as String,
      jobId: (body['job'] as Map<String, dynamic>)['job_id'] as String,
    );
  }

  /// The ready exercise with its vocabulary.
  Future<ReadingStory> story(String exerciseId) async {
    final exercise = await _api.get('/exercises/$exerciseId') as Map<String, dynamic>;
    final vocabulary = await _api.get('/exercises/$exerciseId/vocabulary') as Map<String, dynamic>;
    return ReadingStory.fromJson(exercise, vocabulary);
  }

  Future<({String attemptId, int revision})> startAttempt(String exerciseId, String key) async {
    final body = await _api.post('/exercises/$exerciseId/attempts',
        data: <String, dynamic>{}, idempotencyKey: key) as Map<String, dynamic>;
    final attempt = body['attempt'] as Map<String, dynamic>;
    return (attemptId: attempt['attempt_id'] as String, revision: attempt['revision'] as int);
  }

  Future<ReadingAttempt> attempt(String attemptId) async =>
      ReadingAttempt.fromJson(await _api.get('/attempts/$attemptId') as Map<String, dynamic>);

  /// `POST .../answers/{question}/submit`: graded at once (feedback) or queued (job).
  Future<({Map<String, dynamic>? feedback, String? jobId, int revision})> submitAnswer({
    required String attemptId,
    required String questionId,
    required int revision,
    required String optionId,
    required String key,
  }) async {
    final body = await _api.post(
      '/attempts/$attemptId/answers/$questionId/submit',
      data: {'revision': revision, 'selected_option_id': optionId},
      idempotencyKey: key,
    ) as Map<String, dynamic>;
    return (
      feedback: body['feedback'] as Map<String, dynamic>?,
      jobId: (body['job'] as Map<String, dynamic>?)?['job_id'] as String?,
      revision: body['attempt_revision'] as int,
    );
  }

  Future<Map<String, dynamic>> feedback(String attemptId, String questionId) async =>
      await _api.get('/attempts/$attemptId/answers/$questionId/feedback') as Map<String, dynamic>;

  /// `POST /attempts/{id}/submit` once every answer is graded.
  Future<({Map<String, dynamic>? evaluation, String? jobId})> submitAttempt(
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

  Future<void> cancelJob(String jobId) =>
      _api.post('/jobs/$jobId/cancel', idempotencyKey: ApiClient.newIdempotencyKey());

  Future<Job> waitJob(String jobId, {bool Function()? isCancelled}) =>
      waitForJob(_api, jobId, isCancelled: isCancelled);
}

final readingRepositoryProvider =
    Provider<ReadingRepository>((ref) => ReadingRepository(ref.watch(apiClientProvider)));
