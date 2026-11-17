import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/features/reading/application/reading_session.dart';
import 'package:english_day/features/reading/data/reading_models.dart';
import 'package:english_day/features/reading/data/reading_repository.dart';

import '../../support/fake_backend.dart';
import '../../support/reading_fixtures.dart';
import '../../support/writing_fixtures.dart' show jobJson;

void main() {
  late FakeBackend backend;
  late ReadingRepository repo;

  setUp(() {
    backend = FakeBackend();
    repo = ReadingRepository(ApiClient(
      storage: MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')),
      baseUrl: 'http://test/api/v1',
      adapter: backend,
    ));
  });

  ReadingSession session({String? topic = 'Budaya'}) => ReadingSession(repo,
      request: ReadingRequest(level: ReadingLevel.all[2], topic: topic));

  test('load generates the story for the chosen level and catalog topic, then starts', () async {
    readingHappyPath(backend);

    final story = await session().load();

    final create = backend.sent.firstWhere((r) => r.path == '/reading/exercises');
    expect(create.body, {
      'difficulty': 'advanced',
      'topic': {'mode': 'catalog', 'topic_id': 'topic-budaya'},
      'question_count': 5,
      'question_types': ['multiple_choice'],
    });
    expect(create.headers['Idempotency-Key'], isNotNull);
    expect(backend.count('POST /exercises/$readingExerciseId/attempts'), 1);
    expect(story.title, 'The Blue Kite');
    expect(story.meta, 'Medium · Budaya'); // level of the generated exercise
    expect(story.questions.map((q) => q.text), ['What colour was the kite?', 'What pulled the string?']);
  });

  test('"Acak" asks for a random topic without reading the catalog', () async {
    readingHappyPath(backend);
    await session(topic: randomTopic).load();
    expect(backend.sent.firstWhere((r) => r.path == '/reading/exercises').body,
        containsPair('topic', {'mode': 'random'}));
    expect(backend.count('GET /topics'), 0);
  });

  test('vocabulary spans (code points, after an emoji) land on the right words', () async {
    readingHappyPath(backend);
    final story = await session().load();

    expect(story.paragraphs, hasLength(2));
    final second = story.paragraphs[1];
    expect([for (final h in second.highlights) second.text.substring(h.start, h.end)],
        ['gust', 'grateful']);
    expect(second.highlights.first.vocab.meaning, 'hembusan angin');
  });

  test('each answer is graded by the server; finish returns the quiz summary', () async {
    readingHappyPath(backend);
    final s = session();
    final story = await s.load();

    final first = await s.answer(story.questions[0], 'q1-o1');
    final second = await s.answer(story.questions[1], 'q2-o2');

    expect(first.isCorrect, isTrue);
    expect(second.isCorrect, isFalse);
    expect(second.correctOptionId, 'q2-o0');
    final submits = backend.sent.where((r) => r.path.endsWith('/submit')).toList();
    expect([for (final r in submits) (r.body as Map)['revision']], [1, 2]); // revision follows
    expect(s.nextQuestionIndex, 1);

    final summary = await s.finish();
    expect((summary.correct, summary.total), (1, 2));
    expect((backend.sent.last.body as Map)['revision'], 3);
  });

  test('a failed story generation surfaces, then retry generates a new one', () async {
    readingHappyPath(backend);
    backend.on('GET /jobs/$readingJobId',
        (_) => Reply(200, jobJson(readingJobId, 'generate_exercise', 'failed', error: 'AI_ERROR')));
    final s = session();

    await expectLater(s.load(), throwsA(isA<JobFailedException>()));
    backend.on('GET /jobs/$readingJobId',
        (_) => Reply(200, jobJson(readingJobId, 'generate_exercise', 'succeeded')));
    await s.load();

    expect(backend.count('POST /reading/exercises'), 2);
    final keys = backend.sent
        .where((r) => r.path == '/reading/exercises')
        .map((r) => r.headers['Idempotency-Key'])
        .toSet();
    expect(keys, hasLength(2));
  });

  test('resume loads the story and the answers already graded', () async {
    readingHappyPath(backend);
    backend.on('GET /attempts/$readingAttemptId', (_) => Reply(200, {
          'attempt': readingAttemptJson(revision: 2),
          'exercise': readingExerciseJson(),
          'draft': null,
          'answers': [
            {
              'answer_id': 'ans-q1',
              'question_id': 'q1',
              'selected_option_id': 'q1-o0',
              'response_text': null,
              'revision': 1,
              'submitted_at': '2026-11-17T09:00:00Z',
              'grading_status': 'graded',
              'feedback_available': true,
            },
          ],
          'conversation': null,
          'active_jobs': <Object>[],
          'evaluation': null,
        }));
    backend.on('GET /attempts/$readingAttemptId/answers/q1/feedback',
        (_) => Reply(200, feedbackJson('q1', 'q1-o0')));
    final s = ReadingSession(repo, resumeAttemptId: readingAttemptId);

    await s.load();

    expect(backend.count('POST /reading/exercises'), 0);
    expect(s.answers['q1']!.isCorrect, isFalse);
    expect(s.nextQuestionIndex, 1); // continue at question 2
  });
}
