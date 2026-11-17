import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/audio/wav.dart';
import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/features/speaking/application/speaking_session.dart';
import 'package:english_day/features/speaking/data/speaking_repository.dart';

import '../../support/fake_backend.dart';
import '../../support/speaking_fixtures.dart';

void main() {
  late FakeBackend backend;
  late FakeRecorder recorder;
  late FakePlayer player;
  late SpeakingRepository repo;

  setUp(() {
    backend = FakeBackend();
    recorder = FakeRecorder();
    player = FakePlayer();
    repo = SpeakingRepository(ApiClient(
      storage: MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')),
      baseUrl: 'http://test/api/v1',
      adapter: backend,
    ));
  });

  test('WAV header describes 16-bit mono PCM', () {
    final wav = wavFromPcm16(Uint8List(32000), sampleRate: 16000);
    final header = ByteData.sublistView(wav, 0, 44);
    expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
    expect(String.fromCharCodes(wav.sublist(8, 12)), 'WAVE');
    expect(header.getUint16(22, Endian.little), 1); // channels
    expect(header.getUint32(24, Endian.little), 16000); // sample rate
    expect(header.getUint16(34, Endian.little), 16); // bits
    expect(header.getUint32(40, Endian.little), 32000); // data size
    expect(pcm16Duration(32000, sampleRate: 16000), const Duration(seconds: 1));
  });

  test('start creates the exercise with the friendly persona and waits for the greeting',
      () async {
    speakingHappyPath(backend);
    final session = SpeakingSession(repo, recorder, player);

    await session.start();

    expect(backend.sent.firstWhere((r) => r.path == '/speaking/exercises').body,
        containsPair('persona_id', 'p-friend'));
    expect(session.messages.single.text, 'Hi! What did you do last weekend?');
    expect(session.messages.single.fromAi, isTrue);
    expect(session.started, isTrue);
  });

  test('a turn uploads the WAV (multipart) and returns the AI reply with audio', () async {
    final conversation = speakingHappyPath(backend);
    final session = SpeakingSession(repo, recorder, player);
    await session.start();

    await session.startRecording();
    final reply = await session.stopAndSend();

    final upload = backend.sent.firstWhere((r) => r.path.endsWith('/turns'));
    final form = upload.body as FormData;
    expect(form.fields.single.key, 'client_message_key');
    expect(form.files.single.key, 'audio');
    expect(form.files.single.value.contentType.toString(), 'audio/wav');
    expect(form.files.single.value.length, 44 + 64000); // 2 s of 16 kHz 16-bit mono
    expect(upload.headers['Idempotency-Key'], isNotNull);
    expect(conversation.turns, 1);
    expect(reply!.text, 'Which beach did you visit?');
    expect(session.messages.map((m) => m.text), [
      'Hi! What did you do last weekend?',
      'I went to the beach.',
      'Which beach did you visit?',
    ]);

    await session.play(reply);
    expect(player.played.single, aiAudio);
  });

  test('too-short recordings and NO_SPEECH_DETECTED become NoSpeechException', () async {
    final conversation = speakingHappyPath(backend);
    final session = SpeakingSession(repo, recorder, player);
    await session.start();

    recorder.length = const Duration(milliseconds: 200);
    await session.startRecording();
    await expectLater(session.stopAndSend(), throwsA(isA<NoSpeechException>()));
    expect(conversation.turns, 0); // not even uploaded

    recorder.length = const Duration(seconds: 2);
    conversation.failNextTurn = 'NO_SPEECH_DETECTED';
    await session.startRecording();
    await expectLater(session.stopAndSend(), throwsA(isA<NoSpeechException>()));
    expect(session.messages, hasLength(1)); // the failed turn is not shown
  });

  test('microphone refused', () async {
    speakingHappyPath(backend);
    recorder.permission = false;
    final session = SpeakingSession(repo, recorder, player);
    await session.start();

    await expectLater(session.startRecording(), throwsA(isA<MicPermissionDeniedException>()));
    expect(recorder.recording, isFalse);
  });

  test('finish only after the student spoke', () async {
    speakingHappyPath(backend);
    final session = SpeakingSession(repo, recorder, player);
    await session.start();

    await session.finish();
    expect(backend.count('POST /speaking/attempts/$speakingAttemptId/finish'), 0);

    await session.startRecording();
    await session.stopAndSend();
    await session.finish();
    expect(backend.count('POST /speaking/attempts/$speakingAttemptId/finish'), 1);
  });

  test('resume loads the existing conversation without creating anything', () async {
    final conversation = speakingHappyPath(backend);
    conversation.messages
      ..add(messageJson(1, 'assistant', 'Hello again!'))
      ..add(messageJson(2, 'user', 'Hi.'));
    final session = SpeakingSession(repo, recorder, player, resumeAttemptId: speakingAttemptId);

    await session.start();

    expect(backend.count('POST /speaking/exercises'), 0);
    expect(session.messages.map((m) => m.text), ['Hello again!', 'Hi.']);
  });
}
