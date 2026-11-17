import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/features/writing/application/writing_session.dart';
import 'package:english_day/features/writing/data/writing_repository.dart';

import '../../support/fake_backend.dart';
import '../../support/writing_fixtures.dart';

void main() {
  late FakeBackend backend;
  late WritingSession session;

  setUp(() {
    backend = FakeBackend();
    final api = ApiClient(
      storage: MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')),
      baseUrl: 'http://test/api/v1',
      adapter: backend,
    );
    session = WritingSession(WritingRepository(api));
  });

  String? keyOf(SentRequest r) => r.headers['Idempotency-Key'] as String?;
  List<String> calls() => [for (final r in backend.sent) '${r.method} ${r.path}'];

  test('one check runs every backend step in order and returns the corrections', () async {
    writingHappyPath(backend);

    final result = await session.check(sampleText);

    expect(calls(), [
      'POST /writing/exercises',
      'GET /jobs/$generateJobId',
      'POST /exercises/$exerciseId/attempts',
      'PATCH /attempts/$attemptId/draft',
      'POST /attempts/$attemptId/submit',
      'GET /jobs/$evaluateJobId',
      'GET /attempts/$attemptId/evaluation',
    ]);
    final draft = backend.sent[3].body as Map;
    expect(draft['revision'], 1);
    expect(draft['draft'], {'skill': 'writing', 'response_text': sampleText});
    expect((backend.sent[4].body as Map)['revision'], 2); // revision from the draft save
    for (final i in [0, 2, 4]) {
      expect(keyOf(backend.sent[i]), isNotNull, reason: calls()[i]);
    }
    expect(result.correctionCount, 2);
    expect(result.tokens.where((t) => t.isWrong).map((t) => '${t.text}->${t.correction}'),
        ['go->went', 'was->were']);
    expect(result.bestText, 'Yesterday I went to school and we were late.');
  });

  test('a second check reuses the exercise and starts a new attempt', () async {
    writingHappyPath(backend);
    await session.check(sampleText);
    backend.sent.clear();

    await session.check('Another text.');

    expect(backend.count('POST /writing/exercises'), 0);
    expect(backend.count('POST /exercises/$exerciseId/attempts'), 1);
  });

  test('retry after a lost submit response resends the SAME idempotency key', () async {
    writingHappyPath(backend);
    var failSubmit = true;
    backend.on('POST /attempts/$attemptId/submit', (_) {
      if (failSubmit) {
        throw DioException.connectionError(
            requestOptions: RequestOptions(), reason: 'connection lost');
      }
      return Reply(202, {
        'attempt': attemptJson(status: 'submitted', revision: 3),
        'job': jobJson(evaluateJobId, 'evaluate_attempt', 'queued'),
      });
    });

    await expectLater(session.check(sampleText),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiException.network)));
    failSubmit = false;
    await session.check(sampleText);

    final submits = backend.sent.where((r) => r.path.endsWith('/submit')).toList();
    expect(submits, hasLength(2));
    expect(keyOf(submits[0]), keyOf(submits[1]));
    expect((submits[1].body as Map)['revision'], (submits[0].body as Map)['revision']);
    expect(backend.count('PATCH /attempts/$attemptId/draft'), 1); // not saved twice
  });

  test('AI evaluation failure surfaces, then "Coba lagi" starts a new attempt', () async {
    writingHappyPath(backend);
    backend.on('GET /jobs/$evaluateJobId',
        (_) => Reply(200, jobJson(evaluateJobId, 'evaluate_attempt', 'failed', error: 'AI_ERROR')));

    await expectLater(session.check(sampleText), throwsA(isA<JobFailedException>()));

    backend.on('GET /jobs/$evaluateJobId',
        (_) => Reply(200, jobJson(evaluateJobId, 'evaluate_attempt', 'succeeded')));
    final result = await session.check(sampleText);
    expect(result.correctionCount, 2);
    expect(backend.count('POST /exercises/$exerciseId/attempts'), 2);
    expect(backend.count('POST /writing/exercises'), 1);
  });

  test('a stale draft revision is re-read and saved again', () async {
    writingHappyPath(backend);
    var conflict = true;
    backend.on('PATCH /attempts/$attemptId/draft', (r) {
      final revision = (r.body as Map)['revision'] as int;
      if (conflict) {
        conflict = false;
        return Reply(409, errorJson('REVISION_CONFLICT'));
      }
      return Reply(200, {
        'attempt_id': attemptId,
        'revision': revision + 1,
        'last_saved_at': '2026-11-17T09:00:00Z',
        'last_activity_at': '2026-11-17T09:00:00Z',
      });
    });
    backend.on('GET /attempts/$attemptId', (_) => Reply(200, {
          'attempt': attemptJson(revision: 5),
          'exercise': <String, dynamic>{},
          'draft': {'skill': 'writing', 'response_text': ''},
          'answers': <Object>[],
          'conversation': null,
          'active_jobs': <Object>[],
          'evaluation': null,
        }));

    await session.check(sampleText);

    final saves = backend.sent.where((r) => r.path.endsWith('/draft')).toList();
    expect([for (final s in saves) (s.body as Map)['revision']], [1, 5]);
  });

  test('resuming a submitted attempt only waits for its evaluation', () async {
    writingHappyPath(backend);
    session.resumeFrom(WritingAttempt.fromJson({
      'attempt': attemptJson(status: 'evaluating', revision: 3),
      'exercise': <String, dynamic>{},
      'draft': {'skill': 'writing', 'response_text': sampleText},
      'answers': <Object>[],
      'conversation': null,
      'active_jobs': [jobJson(evaluateJobId, 'evaluate_attempt', 'running')],
      'evaluation': null,
    }));

    final result = await session.check(sampleText);

    expect(calls(), ['GET /jobs/$evaluateJobId', 'GET /attempts/$attemptId/evaluation']);
    expect(result.correctionCount, 2);
  });

  test('cancel while the AI is evaluating stops waiting and cancels the attempt', () async {
    writingHappyPath(backend);
    backend.on('GET /jobs/$evaluateJobId',
        (_) => Reply(200, jobJson(evaluateJobId, 'evaluate_attempt', 'running')));
    backend.on('POST /attempts/$attemptId/cancel',
        (_) => Reply(200, {'attempt': attemptJson(status: 'cancelled')}));

    final check = session.check(sampleText);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    await session.cancel();

    await expectLater(check, throwsA(isA<OperationCancelledException>()));
    expect(backend.count('POST /attempts/$attemptId/cancel'), 1);
  });
}
