import 'dart:typed_data';

import 'package:english_day/core/audio/wav.dart';
import 'package:english_day/features/speaking/application/voice_io.dart';

import 'fake_backend.dart';
import 'writing_fixtures.dart' show jobJson;

/// Backend replies for one Speaking conversation, shaped like the real responses.
const speakingExerciseId = 'sex-1';
const speakingAttemptId = 'sat-1';
const generateSpeakingJob = 'job-sgen';
const greetingJob = 'job-greet';
const turnJob = 'job-turn';
final aiAudio = Uint8List.fromList([1, 2, 3, 4]);

Map<String, dynamic> messageJson(int position, String sender, String text,
        {String delivery = 'ready'}) =>
    {
      'message_id': 'msg-$position',
      'sender': sender,
      'position': position,
      'client_message_key': 'k-$position',
      'reply_to_message_id': null,
      'transcript': text,
      'audio': sender == 'assistant'
          ? {
              'media_id': 'audio-$position',
              'purpose': 'speaking_ai_audio',
              'mime_type': 'audio/wav',
              'size_bytes': 4,
              'duration_ms': 1000,
              'status': 'ready',
              'available': true,
            }
          : null,
      'transcription_status': sender == 'assistant' ? 'not_applicable' : 'completed',
      'delivery_status': delivery,
      'created_at': '2026-11-17T09:00:00Z',
    };

/// A backend conversation: [messages] grows as turns are processed.
class FakeConversation {
  final messages = <Map<String, dynamic>>[];
  int turns = 0;

  /// Error code the next voice-turn job fails with (e.g. NO_SPEECH_DETECTED).
  String? failNextTurn;
}

FakeConversation speakingHappyPath(FakeBackend backend) {
  final conversation = FakeConversation();
  backend.on('GET /personas', (_) => const Reply(200, {
        'items': [
          {'persona_id': 'p-officer', 'name': 'Airport Officer', 'role_description': ''},
          {'persona_id': 'p-friend', 'name': 'Friendly Classmate', 'role_description': ''},
        ],
        'next_cursor': null,
      }));
  backend.on('POST /speaking/exercises', (_) => Reply(202, {
        'exercise_id': speakingExerciseId,
        'job': jobJson(generateSpeakingJob, 'generate_exercise', 'queued'),
      }));
  backend.on('GET /jobs/$generateSpeakingJob',
      (_) => Reply(200, jobJson(generateSpeakingJob, 'generate_exercise', 'succeeded')));
  backend.on('POST /exercises/$speakingExerciseId/attempts', (_) => Reply(201, {
        'attempt': {'attempt_id': speakingAttemptId, 'revision': 1},
        'conversation': null,
        'job': jobJson(greetingJob, 'start_conversation', 'queued'),
      }));
  backend.on('GET /speaking/attempts/$speakingAttemptId/conversation', (_) => const Reply(200, {
        'conversation_session_id': 'c',
        'attempt_id': speakingAttemptId,
        'status': 'active',
        'last_activity_at': '2026-11-17T09:00:00Z',
        'ended_at': null,
        'active_job': null,
      }));
  backend.on('GET /jobs/$greetingJob', (_) {
    if (conversation.messages.isEmpty) {
      conversation.messages.add(messageJson(1, 'assistant', 'Hi! What did you do last weekend?'));
    }
    return Reply(200, jobJson(greetingJob, 'start_conversation', 'succeeded'));
  });
  backend.on('GET /speaking/attempts/$speakingAttemptId/messages',
      (_) => Reply(200, {'items': conversation.messages, 'next_cursor': null}));
  backend.on('POST /speaking/attempts/$speakingAttemptId/turns', (_) {
    conversation.turns++;
    return Reply(202, {
      'message': messageJson(conversation.messages.length + 1, 'user', ''),
      'job': jobJson(turnJob, 'process_voice_turn', 'queued'),
    });
  });
  backend.on('GET /jobs/$turnJob', (_) {
    final fail = conversation.failNextTurn;
    final n = conversation.messages.length;
    if (fail != null) {
      conversation.failNextTurn = null;
      conversation.messages.add(messageJson(n + 1, 'user', '', delivery: 'failed'));
      return Reply(200, jobJson(turnJob, 'process_voice_turn', 'failed', error: fail));
    }
    conversation.messages
      ..add(messageJson(n + 1, 'user', 'I went to the beach.'))
      ..add(messageJson(n + 2, 'assistant', 'Which beach did you visit?'));
    return Reply(200, jobJson(turnJob, 'process_voice_turn', 'succeeded'));
  });
  for (var i = 1; i <= 9; i++) {
    backend.on('GET /media/audio-$i/download', (_) => Reply(200, aiAudio));
  }
  backend.on('POST /speaking/attempts/$speakingAttemptId/finish', (_) => Reply(202, {
        'attempt': {'attempt_id': speakingAttemptId},
        'job': jobJson('job-eval', 'evaluate_attempt', 'queued'),
      }));
  return conversation;
}

/// Records [seconds] of silence-free audio without a microphone.
class FakeRecorder implements VoiceRecorder {
  bool permission = true;
  Duration length = const Duration(seconds: 2);
  bool recording = false;
  bool disposed = false;

  @override
  Future<bool> hasPermission() async => permission;
  @override
  Future<void> start() async => recording = true;
  @override
  Future<Uint8List> stop() async {
    recording = false;
    final bytes = 16000 * 2 * length.inMilliseconds ~/ 1000;
    return wavFromPcm16(Uint8List(bytes), sampleRate: 16000);
  }

  @override
  Future<void> cancel() async => recording = false;
  @override
  void dispose() => disposed = true;
}

/// Plays nothing; remembers what it was given. Finishes at once.
class FakePlayer implements VoicePlayer {
  final played = <Uint8List>[];
  @override
  Future<void> play(Uint8List bytes, String mimeType) async => played.add(bytes);
  @override
  Future<void> stop() async {}
  @override
  void dispose() {}
}
