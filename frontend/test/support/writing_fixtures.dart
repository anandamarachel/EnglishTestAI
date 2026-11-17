import 'fake_backend.dart';

/// Backend replies for one Writing check (exercise → attempt → draft → submit →
/// evaluation), shaped like the real responses. IDs are fixed so routes match.
const exerciseId = 'ex-1';
const attemptId = 'at-1';
const generateJobId = 'job-generate';
const evaluateJobId = 'job-evaluate';

Map<String, dynamic> jobJson(String id, String type, String status, {String? error}) => {
      'job_id': id,
      'job_type': type,
      'status': status,
      'target': {'type': 'exercise', 'id': exerciseId},
      'created_at': '2026-11-17T09:00:00Z',
      'started_at': null,
      'finished_at': null,
      'error': error == null ? null : {'code': error, 'retryable': true},
      'result_refs': <String, String>{},
      'can_cancel': status == 'queued' || status == 'running',
      'can_retry': status == 'failed',
    };

Map<String, dynamic> attemptJson({String status = 'in_progress', int revision = 1}) => {
      'attempt_id': attemptId,
      'exercise_id': exerciseId,
      'skill': 'writing',
      'title': 'Writing about Alam',
      'attempt_number': 1,
      'source_attempt_id': null,
      'status': status,
      'current_stage': status == 'in_progress' ? 'writing' : 'results',
      'revision': revision,
      'last_activity_at': '2026-11-17T09:00:00Z',
      'last_saved_at': null,
      'started_at': '2026-11-17T09:00:00Z',
      'submitted_at': null,
      'completed_at': null,
      'score': null,
    };

const sampleText = 'Yesterday I go to school and we was late.';

Map<String, dynamic> correctionJson(String id, int start, int end, String original,
        String replacement, String title) =>
    {
      'correction_id': id,
      'start': start,
      'end': end,
      'original': original,
      'replacement': replacement,
      'category': 'grammar',
      'title': title,
      'explanation': 'Explanation of $title.',
      'example': 'Example of $title.',
    };

Map<String, dynamic> evaluationJson({
  String status = 'completed',
  List<Map<String, dynamic>>? corrections,
  String? correctedText = 'Yesterday I went to school and we were late.',
}) =>
    {
      'evaluation_id': 'ev-1',
      'attempt_id': attemptId,
      'status': status,
      'overall_score': 4,
      'max_score': 9,
      'rubric_version': 'writing-ielts-practice-v1',
      'summary': null,
      'corrected_text': correctedText,
      'feedback_payload': {
        'schema_version': 1,
        'corrections': corrections ??
            [
              correctionJson('c1', 12, 14, 'go', 'went', 'Past tense'),
              correctionJson('c2', 32, 35, 'was', 'were', 'Subject-verb agreement'),
            ],
        'limitations': <String>[],
      },
      'criteria': <Object>[],
      'quiz_summary': null,
      'created_at': '2026-11-17T09:00:00Z',
      'completed_at': '2026-11-17T09:00:01Z',
    };

/// Routes for a backend where every step succeeds at once.
void writingHappyPath(FakeBackend backend, {Map<String, dynamic>? evaluation}) {
  backend.on('POST /writing/exercises', (_) => Reply(202, {
        'exercise_id': exerciseId,
        'job': jobJson(generateJobId, 'generate_exercise', 'queued'),
      }));
  backend.on('GET /jobs/$generateJobId',
      (_) => Reply(200, jobJson(generateJobId, 'generate_exercise', 'succeeded')));
  backend.on('POST /exercises/$exerciseId/attempts',
      (_) => Reply(201, {'attempt': attemptJson(), 'conversation': null, 'job': null}));
  backend.on('PATCH /attempts/$attemptId/draft', (r) {
    final revision = (r.body as Map)['revision'] as int;
    return Reply(200, {
      'attempt_id': attemptId,
      'revision': revision + 1,
      'last_saved_at': '2026-11-17T09:00:00Z',
      'last_activity_at': '2026-11-17T09:00:00Z',
    });
  });
  backend.on('POST /attempts/$attemptId/submit', (_) => Reply(202, {
        'attempt': attemptJson(status: 'submitted', revision: 3),
        'job': jobJson(evaluateJobId, 'evaluate_attempt', 'queued'),
      }));
  backend.on('GET /jobs/$evaluateJobId',
      (_) => Reply(200, jobJson(evaluateJobId, 'evaluate_attempt', 'succeeded')));
  backend.on('GET /attempts/$attemptId/evaluation', (_) => Reply(200, evaluation ?? evaluationJson()));
}
