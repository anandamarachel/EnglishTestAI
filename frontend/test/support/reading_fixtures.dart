import 'fake_backend.dart';
import 'writing_fixtures.dart' show jobJson;

/// Backend replies for one Reading practice, shaped like the real responses.
const readingExerciseId = 'rex-1';
const readingAttemptId = 'rat-1';
const readingJobId = 'job-reading';

/// Two paragraphs; the emoji makes code-point and UTF-16 offsets differ.
const passage = 'Daeng flew a blue kite 😀 at the festival.\n\n'
    'A strong gust pulled the string. He felt grateful for the help.';

/// Code-point span of [word]'s first occurrence in [passage].
Map<String, dynamic> spanOf(String word) {
  final utf16 = passage.indexOf(word);
  final start = passage.substring(0, utf16).runes.length;
  return {'start': start, 'end': start + word.runes.length, 'original': word};
}

const questions = [
  ('q1', 'What colour was the kite?', ['Red', 'Blue', 'Green'], 1),
  ('q2', 'What pulled the string?', ['A gust', 'A dog', 'A bird'], 0),
];

Map<String, dynamic> readingExerciseJson() => {
      'exercise_id': readingExerciseId,
      'skill': 'reading',
      'difficulty': 'intermediate',
      'content_cefr_level': 'B1',
      'topic': {'mode': 'catalog', 'topic_id': 'topic-budaya', 'name': 'Budaya'},
      'title': 'The Blue Kite',
      'instructions': 'Read the story, then answer the questions.',
      'generation_status': 'ready',
      'created_at': '2026-11-17T09:00:00Z',
      'content': {
        'passage': passage,
        'requested_word_count': null,
        'question_count': questions.length,
        'feedback_mode': 'per_question',
      },
      'questions': [
        for (var i = 0; i < questions.length; i++)
          {
            'question_id': questions[i].$1,
            'position': i + 1,
            'question_type': 'multiple_choice',
            'question_text': questions[i].$2,
            'max_points': 1,
            'options': [
              for (var j = 0; j < questions[i].$3.length; j++)
                {'option_id': '${questions[i].$1}-o$j', 'option_text': questions[i].$3[j], 'position': j + 1},
            ],
          },
      ],
    };

Map<String, dynamic> vocabularyJson() => {
      'items': [
        for (final (i, word, meaning) in [(1, 'gust', 'hembusan angin'), (2, 'grateful', 'bersyukur')])
          {
            'vocabulary_item_id': 'v$i',
            'word_or_phrase': word,
            'meaning': meaning,
            'example_sentence': 'Example with $word.',
            'example_from_passage': '',
            'occurrences': [spanOf(word)],
            'position': i,
          },
      ],
    };

Map<String, dynamic> feedbackJson(String questionId, String selected) {
  final q = questions.firstWhere((q) => q.$1 == questionId);
  final correctId = '$questionId-o${q.$4}';
  return {
    'answer_id': 'ans-$questionId',
    'question_id': questionId,
    'grading_status': 'graded',
    'awarded_points': selected == correctId ? 1 : 0,
    'max_points': 1,
    'is_correct': selected == correctId,
    'correct_option_id': correctId,
    'reference_answer': null,
    'explanation': 'The story says it for $questionId.',
    'evidence_spans': <Object>[],
  };
}

Map<String, dynamic> readingAttemptJson({String status = 'in_progress', int revision = 1}) => {
      'attempt_id': readingAttemptId,
      'exercise_id': readingExerciseId,
      'skill': 'reading',
      'title': 'The Blue Kite',
      'attempt_number': 1,
      'source_attempt_id': null,
      'status': status,
      'current_stage': 'reading',
      'revision': revision,
      'last_activity_at': '2026-11-17T09:00:00Z',
      'last_saved_at': null,
      'started_at': '2026-11-17T09:00:00Z',
      'submitted_at': null,
      'completed_at': null,
      'score': null,
    };

/// Routes for a backend where every step succeeds at once.
void readingHappyPath(FakeBackend backend) {
  var revision = 1;
  backend.on('GET /topics', (_) => const Reply(200, {
        'items': [
          {'topic_id': 'topic-budaya', 'name': 'Budaya', 'description': null},
        ],
        'next_cursor': null,
      }));
  backend.on('POST /reading/exercises', (_) => Reply(202, {
        'exercise_id': readingExerciseId,
        'job': jobJson(readingJobId, 'generate_exercise', 'queued'),
      }));
  backend.on('GET /jobs/$readingJobId',
      (_) => Reply(200, jobJson(readingJobId, 'generate_exercise', 'succeeded')));
  backend.on('GET /exercises/$readingExerciseId', (_) => Reply(200, readingExerciseJson()));
  backend.on('GET /exercises/$readingExerciseId/vocabulary', (_) => Reply(200, vocabularyJson()));
  backend.on('POST /exercises/$readingExerciseId/attempts',
      (_) => Reply(201, {'attempt': readingAttemptJson(), 'conversation': null, 'job': null}));
  for (final q in questions) {
    backend.on('POST /attempts/$readingAttemptId/answers/${q.$1}/submit', (r) {
      final body = r.body as Map;
      revision = (body['revision'] as int) + 1;
      final selected = body['selected_option_id'] as String;
      return Reply(200, {
        'answer': {
          'answer_id': 'ans-${q.$1}',
          'question_id': q.$1,
          'selected_option_id': selected,
          'response_text': null,
          'revision': 1,
          'submitted_at': '2026-11-17T09:00:00Z',
          'grading_status': 'graded',
          'feedback_available': true,
        },
        'feedback': feedbackJson(q.$1, selected),
        'attempt_revision': revision,
      });
    });
  }
  backend.on('POST /attempts/$readingAttemptId/submit', (_) => Reply(200, {
        'attempt': readingAttemptJson(status: 'completed', revision: revision + 1),
        'evaluation': {
          'evaluation_id': 'rev-1',
          'attempt_id': readingAttemptId,
          'status': 'completed',
          'overall_score': 50,
          'max_score': 100,
          'rubric_version': 'reading-quiz-v1',
          'summary': '1 of 2 answers correct.',
          'corrected_text': null,
          'feedback_payload': {'schema_version': 1, 'corrections': <Object>[], 'limitations': <Object>[]},
          'criteria': <Object>[],
          'quiz_summary': {
            'question_count': 2,
            'graded_count': 2,
            'correct_count': 1,
            'awarded_points': 1,
            'max_points': 2,
          },
          'created_at': '2026-11-17T09:00:00Z',
          'completed_at': '2026-11-17T09:00:01Z',
        },
      }));
}
