import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/features/listening/application/listening_session.dart';
import 'package:english_day/features/listening/data/listening_repository.dart';

import '../../support/fake_backend.dart';
import '../../support/listening_fixtures.dart';

void main() {
  late FakeBackend backend;
  late ListeningRepository repo;
  late FakeAudioLoader loader;

  setUp(() {
    backend = FakeBackend();
    loader = FakeAudioLoader();
    repo = ListeningRepository(ApiClient(
      storage: MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')),
      baseUrl: 'http://test/api/v1',
      adapter: backend,
    ));
  });

  test('load generates the exercise, starts the attempt and plays the downloaded audio', () async {
    listeningHappyPath(backend);
    final session = ListeningSession(repo, loader.call);

    await session.load();

    expect(backend.sent.firstWhere((r) => r.path == '/listening/exercises').body, {
      'difficulty': 'intermediate',
      'topic': {'mode': 'random'},
      'question_count': 3,
      'question_types': ['multiple_choice'],
    });
    expect(backend.count('POST /exercises/$listeningExerciseId/attempts'), 1);
    final download = backend.sent.firstWhere((r) => r.path == '/media/$mediaId/download');
    expect(download.headers['Authorization'], 'Bearer a'); // private media needs the token
    expect(loader.bytes, audioBytes);
    expect(loader.mimeType, 'audio/wav');
    expect(session.audio!.duration, const Duration(seconds: 30));
    expect(session.meta, 'Medium · Sekolah');
    expect(session.exercise!.questions, hasLength(2));
  });

  test('answers are saved as a draft with the playback position, then submitted', () async {
    final drafts = <Map<String, dynamic>>[];
    listeningHappyPath(backend, drafts: drafts);
    final session = ListeningSession(repo, loader.call);
    await session.load();
    await loader.audio!.seek(const Duration(seconds: 12));

    session.select('q1', 'q1-o0');
    session.select('q2', 'q2-o2');
    final result = await session.submit();

    final draft = drafts.last['draft'] as Map;
    expect(draft['playback_position_ms'], 12000);
    expect(draft['answers'], [
      {'question_id': 'q1', 'selected_option_id': 'q1-o0', 'response_text': null},
      {'question_id': 'q2', 'selected_option_id': 'q2-o2', 'response_text': null},
    ]);
    final submit = backend.sent.firstWhere((r) => r.path.endsWith('/submit'));
    expect((submit.body as Map)['revision'], drafts.last['revision'] + 1);
    expect((result.correct, result.total), (1, 2));
    expect(result.answers['q2']!.isCorrect, isFalse);
    expect(result.answers['q2']!.correctOptionId, 'q2-o1');
  });

  test('the transcript marks the lines that are evidence (code points after an emoji)', () async {
    listeningHappyPath(backend);
    final session = ListeningSession(repo, loader.call);
    await session.load();
    session.select('q1', 'q1-o0');
    session.select('q2', 'q2-o1');

    final result = await session.submit();

    expect([for (final l in result.transcript) l.evidence], [false, true, false, true]);
    expect(result.transcript.first.text, 'Mira: Hello 😀 Andi.');
  });

  test('audio failure keeps the exercise; reloadAudio recovers', () async {
    listeningHappyPath(backend);
    loader.failWith = Exception('decoder');
    final session = ListeningSession(repo, loader.call);

    await expectLater(session.load(), throwsA(isA<ListeningAudioException>()));
    expect(session.exercise, isNotNull);

    loader.failWith = null;
    await session.reloadAudio();
    expect(session.audio, isNotNull);
    expect(backend.count('POST /listening/exercises'), 1);
  });

  test('resume restores answers and playback position from the draft', () async {
    listeningHappyPath(backend);
    backend.on('GET /attempts/$listeningAttemptId', (_) => Reply(200, {
          'attempt': listeningAttemptJson(revision: 4),
          'exercise': listeningExerciseJson(),
          'draft': {
            'skill': 'listening',
            'playback_position_ms': 7000,
            'current_question_id': null,
            'answers': [
              {'question_id': 'q1', 'selected_option_id': 'q1-o0', 'response_text': null},
            ],
          },
          'answers': <Object>[],
          'conversation': null,
          'active_jobs': <Object>[],
          'evaluation': null,
        }));
    final session = ListeningSession(repo, loader.call, resumeAttemptId: listeningAttemptId);

    await session.load();

    expect(backend.count('POST /listening/exercises'), 0);
    expect(session.selections, {'q1': 'q1-o0'});
    expect(session.audio!.position, const Duration(seconds: 7));
  });
}
