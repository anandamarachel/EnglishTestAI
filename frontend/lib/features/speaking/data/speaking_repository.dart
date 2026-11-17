import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/network/providers.dart';

/// One chat bubble (`Message`): the AI's line or the student's transcribed turn.
class SpeakingMessage {
  const SpeakingMessage({
    required this.id,
    required this.fromAi,
    required this.text,
    this.audioMediaId,
    this.audioMimeType = 'audio/wav',
  });

  factory SpeakingMessage.fromJson(Map<String, dynamic> json) {
    final audio = json['audio'] as Map<String, dynamic>?;
    final playable = audio != null && audio['available'] == true;
    return SpeakingMessage(
      id: json['message_id'] as String,
      fromAi: json['sender'] == 'assistant',
      text: (json['transcript'] as String?) ?? '',
      audioMediaId: playable ? audio['media_id'] as String : null,
      audioMimeType: (audio?['mime_type'] as String?) ?? 'audio/wav',
    );
  }

  /// Failed or cancelled turns stay in the backend history but are not shown.
  static bool isShown(Map<String, dynamic> json) =>
      json['delivery_status'] != 'failed' && json['delivery_status'] != 'cancelled';

  final String id;
  final bool fromAi;
  final String text;

  /// AI replies have audio; null when it is not (yet) available.
  final String? audioMediaId;
  final String audioMimeType;
}

/// Speaking endpoints. POSTs take the caller's idempotency key so a retried step
/// reuses it.
class SpeakingRepository {
  SpeakingRepository(this._api);
  final ApiClient _api;

  /// `GET /personas`: (id, name).
  Future<List<({String id, String name})>> personas() async {
    final body = await _api.get('/personas', query: {'limit': 100}) as Map<String, dynamic>;
    return [
      for (final p in body['items'] as List)
        (id: (p as Map<String, dynamic>)['persona_id'] as String, name: p['name'] as String),
    ];
  }

  Future<({String exerciseId, String jobId})> createExercise(String personaId, String key) async {
    final body = await _api.post(
      '/speaking/exercises',
      data: {
        'difficulty': 'intermediate',
        'topic': {'mode': 'random'},
        'persona_id': personaId,
      },
      idempotencyKey: key,
    ) as Map<String, dynamic>;
    return (
      exerciseId: body['exercise_id'] as String,
      jobId: (body['job'] as Map<String, dynamic>)['job_id'] as String,
    );
  }

  /// Starts the attempt; the AI's greeting is prepared by the returned job.
  Future<({String attemptId, String? greetingJobId})> startAttempt(
      String exerciseId, String key) async {
    final body = await _api.post('/exercises/$exerciseId/attempts',
        data: <String, dynamic>{}, idempotencyKey: key) as Map<String, dynamic>;
    final attempt = body['attempt'] as Map<String, dynamic>;
    return (
      attemptId: attempt['attempt_id'] as String,
      greetingJobId: (body['job'] as Map<String, dynamic>?)?['job_id'] as String?,
    );
  }

  /// The conversation's job still running (greeting or a voice turn), if any.
  Future<({String status, String? activeJobId})> conversation(String attemptId) async {
    final body =
        await _api.get('/speaking/attempts/$attemptId/conversation') as Map<String, dynamic>;
    return (
      status: body['status'] as String,
      activeJobId: (body['active_job'] as Map<String, dynamic>?)?['job_id'] as String?,
    );
  }

  /// Every shown message, oldest first.
  Future<List<SpeakingMessage>> messages(String attemptId) async {
    final messages = <SpeakingMessage>[];
    String? cursor;
    do {
      final body = await _api.get('/speaking/attempts/$attemptId/messages',
          query: {'limit': 100, if (cursor != null) 'cursor': cursor}) as Map<String, dynamic>;
      for (final m in body['items'] as List) {
        final json = m as Map<String, dynamic>;
        if (SpeakingMessage.isShown(json)) messages.add(SpeakingMessage.fromJson(json));
      }
      cursor = body['next_cursor'] as String?;
    } while (cursor != null);
    return messages;
  }

  /// `POST .../turns` (multipart): the recording; the AI reply comes from the job.
  /// Resending the same [clientMessageKey] with the same audio returns the same turn.
  Future<String> sendTurn({
    required String attemptId,
    required Uint8List wav,
    required String clientMessageKey,
    required String key,
  }) async {
    final form = FormData.fromMap({
      'client_message_key': clientMessageKey,
      'audio': MultipartFile.fromBytes(wav,
          filename: 'turn.wav', contentType: DioMediaType('audio', 'wav')),
    });
    final body = await _api.post('/speaking/attempts/$attemptId/turns',
        data: form, idempotencyKey: key) as Map<String, dynamic>;
    return (body['job'] as Map<String, dynamic>)['job_id'] as String;
  }

  /// Private audio of an AI reply.
  Future<Uint8List> audio(String mediaId) => _api.getBytes('/media/$mediaId/download');

  /// Ends the conversation and queues its evaluation.
  Future<void> finish(String attemptId, String key) =>
      _api.post('/speaking/attempts/$attemptId/finish', idempotencyKey: key);

  Future<void> cancelJob(String jobId) =>
      _api.post('/jobs/$jobId/cancel', idempotencyKey: ApiClient.newIdempotencyKey());

  Future<Job> waitJob(String jobId, {bool Function()? isCancelled}) =>
      waitForJob(_api, jobId, isCancelled: isCancelled);
}

final speakingRepositoryProvider =
    Provider<SpeakingRepository>((ref) => SpeakingRepository(ref.watch(apiClientProvider)));
