import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/features/listening/data/listening_models.dart';

/// A saved Listening attempt (`GET /attempts/{id}`), used to resume from the dashboard.
class ListeningAttempt {
  const ListeningAttempt({
    required this.attemptId,
    required this.exercise,
    required this.status,
    required this.revision,
    required this.playbackPositionMs,
    required this.selections,
    required this.evaluation,
  });

  factory ListeningAttempt.fromJson(Map<String, dynamic> json) {
    final attempt = json['attempt'] as Map<String, dynamic>;
    final draft = json['draft'] as Map<String, dynamic>?;
    final selections = <String, String>{
      for (final a in (draft?['answers'] as List?) ?? const [])
        if ((a as Map<String, dynamic>)['selected_option_id'] != null)
          a['question_id'] as String: a['selected_option_id'] as String,
    };
    // Submitted answers are no longer in the draft but in `answers`.
    for (final a in (json['answers'] as List?) ?? const []) {
      final answer = a as Map<String, dynamic>;
      final option = answer['selected_option_id'] as String?;
      if (option != null) selections[answer['question_id'] as String] = option;
    }
    return ListeningAttempt(
      attemptId: attempt['attempt_id'] as String,
      exercise: ListeningExercise.fromJson(json['exercise'] as Map<String, dynamic>),
      status: attempt['status'] as String,
      revision: attempt['revision'] as int,
      playbackPositionMs: (draft?['playback_position_ms'] as int?) ?? 0,
      selections: selections,
      evaluation: json['evaluation'] as Map<String, dynamic>?,
    );
  }

  final String attemptId;
  final ListeningExercise exercise;

  /// in_progress | submitted | evaluating | completed | failed | cancelled
  final String status;
  final int revision;
  final int playbackPositionMs;

  /// Selected option id by question id.
  final Map<String, String> selections;
  final Map<String, dynamic>? evaluation;

  bool get isEditable => status == 'in_progress';
}

/// Listening endpoints. POSTs take the caller's idempotency key so a retried step
/// reuses it.
class ListeningRepository {
  ListeningRepository(this._api);
  final ApiClient _api;

  /// `POST /listening/exercises`: 3 multiple-choice questions, as in the design.
  Future<({String exerciseId, String jobId})> createExercise(String key) async {
    final body = await _api.post(
      '/listening/exercises',
      data: {
        'difficulty': 'intermediate',
        'topic': {'mode': 'random'},
        'question_count': 3,
        'question_types': ['multiple_choice'],
      },
      idempotencyKey: key,
    ) as Map<String, dynamic>;
    return (
      exerciseId: body['exercise_id'] as String,
      jobId: (body['job'] as Map<String, dynamic>)['job_id'] as String,
    );
  }

  Future<ListeningExercise> exercise(String exerciseId) async => ListeningExercise.fromJson(
      await _api.get('/exercises/$exerciseId') as Map<String, dynamic>);

  /// The private audio file (`GET /media/{id}/download`).
  Future<Uint8List> audio(String mediaId) => _api.getBytes('/media/$mediaId/download');

  Future<({String attemptId, int revision})> startAttempt(String exerciseId, String key) async {
    final body = await _api.post('/exercises/$exerciseId/attempts',
        data: <String, dynamic>{}, idempotencyKey: key) as Map<String, dynamic>;
    final attempt = body['attempt'] as Map<String, dynamic>;
    return (attemptId: attempt['attempt_id'] as String, revision: attempt['revision'] as int);
  }

  Future<ListeningAttempt> attempt(String attemptId) async =>
      ListeningAttempt.fromJson(await _api.get('/attempts/$attemptId') as Map<String, dynamic>);

  /// `PATCH /attempts/{id}/draft`: selected answers and playback position. Returns
  /// the new revision.
  Future<int> saveDraft({
    required String attemptId,
    required int revision,
    required int playbackPositionMs,
    required Map<String, String> selections,
  }) async {
    final body = await _api.patch('/attempts/$attemptId/draft', data: {
      'revision': revision,
      'draft': {
        'skill': 'listening',
        'playback_position_ms': playbackPositionMs,
        'current_question_id': null,
        'answers': [
          for (final e in selections.entries)
            {'question_id': e.key, 'selected_option_id': e.value, 'response_text': null},
        ],
      },
    }) as Map<String, dynamic>;
    return body['revision'] as int;
  }

  /// `POST /attempts/{id}/submit`: every answer at once.
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

  Future<Map<String, dynamic>> feedback(String attemptId, String questionId) async =>
      await _api.get('/attempts/$attemptId/answers/$questionId/feedback') as Map<String, dynamic>;

  /// Unlocked after submitting.
  Future<Map<String, dynamic>> transcript(String attemptId) async =>
      await _api.get('/attempts/$attemptId/transcript') as Map<String, dynamic>;

  Future<void> cancelJob(String jobId) =>
      _api.post('/jobs/$jobId/cancel', idempotencyKey: ApiClient.newIdempotencyKey());

  Future<Job> waitJob(String jobId, {bool Function()? isCancelled}) =>
      waitForJob(_api, jobId, isCancelled: isCancelled);
}

final listeningRepositoryProvider =
    Provider<ListeningRepository>((ref) => ListeningRepository(ref.watch(apiClientProvider)));
