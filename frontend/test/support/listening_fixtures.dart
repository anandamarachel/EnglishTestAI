import 'dart:typed_data';

import 'package:english_day/features/listening/application/listening_audio.dart';

import 'fake_backend.dart';
import 'writing_fixtures.dart' show jobJson;

/// Backend replies for one Listening practice, shaped like the real responses.
const listeningExerciseId = 'lex-1';
const listeningAttemptId = 'lat-1';
const listeningJobId = 'job-listening';
const mediaId = 'media-1';
final audioBytes = Uint8List.fromList(List.generate(64, (i) => i));

const listeningQuestions = [
  ('q1', 'What does Andi want to buy?', ['A chicken sandwich', 'Noodles', 'Water'], 0),
  ('q2', 'Where will he sit?', ['Outside', 'Near the window', 'In class'], 1),
];

/// One evidence line per question; the emoji shifts code points vs UTF-16.
const transcript = 'Mira: Hello 😀 Andi.\n'
    'Andi: I would like a chicken sandwich.\n'
    'Mira: Sure.\n'
    'Andi: I will sit near the window.';

Map<String, dynamic> evidenceSpan(String text) {
  final utf16 = transcript.indexOf(text);
  final start = transcript.substring(0, utf16).runes.length;
  return {'start': start, 'end': start + text.runes.length, 'original': text};
}

Map<String, dynamic> listeningExerciseJson() => {
      'exercise_id': listeningExerciseId,
      'skill': 'listening',
      'difficulty': 'intermediate',
      'content_cefr_level': 'B1',
      'topic': {'mode': 'random', 'topic_id': 't', 'name': 'Sekolah'},
      'title': 'At the Canteen',
      'instructions': 'Listen, then answer.',
      'generation_status': 'ready',
      'created_at': '2026-11-17T09:00:00Z',
      'content': {
        'audio': {
          'media_id': mediaId,
          'purpose': 'listening_audio',
          'mime_type': 'audio/wav',
          'size_bytes': 64,
          'duration_ms': 30000,
          'status': 'ready',
          'available': true,
        },
        'question_count': listeningQuestions.length,
        'feedback_mode': 'after_submission',
        'transcript_policy': 'after_submission',
      },
      'questions': [
        for (var i = 0; i < listeningQuestions.length; i++)
          {
            'question_id': listeningQuestions[i].$1,
            'position': i + 1,
            'question_type': 'multiple_choice',
            'question_text': listeningQuestions[i].$2,
            'max_points': 1,
            'options': [
              for (var j = 0; j < listeningQuestions[i].$3.length; j++)
                {
                  'option_id': '${listeningQuestions[i].$1}-o$j',
                  'option_text': listeningQuestions[i].$3[j],
                  'position': j + 1,
                },
            ],
          },
      ],
    };

Map<String, dynamic> listeningAttemptJson({String status = 'in_progress', int revision = 1}) => {
      'attempt_id': listeningAttemptId,
      'exercise_id': listeningExerciseId,
      'skill': 'listening',
      'title': 'At the Canteen',
      'attempt_number': 1,
      'source_attempt_id': null,
      'status': status,
      'current_stage': 'listening',
      'revision': revision,
      'last_activity_at': '2026-11-17T09:00:00Z',
      'last_saved_at': null,
      'started_at': '2026-11-17T09:00:00Z',
      'submitted_at': null,
      'completed_at': null,
      'score': null,
    };

/// A player that never moves on its own (no timers), so widget tests can settle.
class SilentAudio extends ListeningAudio {
  SilentAudio(this._duration);
  final Duration _duration;
  Duration _position = Duration.zero;
  bool _playing = false;
  double _speed = 1.0;

  @override
  Duration get duration => _duration;
  @override
  Duration get position => _position;
  @override
  bool get playing => _playing;
  @override
  double get speed => _speed;

  @override
  Future<void> play() async {
    _playing = true;
    notifyListeners();
  }

  @override
  Future<void> pause() async {
    _playing = false;
    notifyListeners();
  }

  @override
  Future<void> seek(Duration position) async {
    _position = position;
    notifyListeners();
  }

  @override
  Future<void> setSpeed(double speed) async {
    _speed = speed;
    notifyListeners();
  }
}

/// Records what the session gave the player; no sound.
class FakeAudioLoader {
  Uint8List? bytes;
  String? mimeType;
  SilentAudio? audio;
  int calls = 0;
  Object? failWith;

  Future<ListeningAudio> call(Uint8List bytes, String mimeType, Duration known) async {
    calls++;
    if (failWith != null) throw failWith!;
    this.bytes = bytes;
    this.mimeType = mimeType;
    return audio = SilentAudio(known);
  }
}

/// Routes where every step succeeds; the last saved draft is kept in [drafts].
void listeningHappyPath(FakeBackend backend, {List<Map<String, dynamic>>? drafts}) {
  var revision = 1;
  final selections = <String, String>{};
  backend.on('POST /listening/exercises', (_) => Reply(202, {
        'exercise_id': listeningExerciseId,
        'job': jobJson(listeningJobId, 'generate_exercise', 'queued'),
      }));
  backend.on('GET /jobs/$listeningJobId',
      (_) => Reply(200, jobJson(listeningJobId, 'generate_exercise', 'succeeded')));
  backend.on('GET /exercises/$listeningExerciseId', (_) => Reply(200, listeningExerciseJson()));
  backend.on('GET /media/$mediaId/download', (_) => Reply(200, audioBytes));
  backend.on('POST /exercises/$listeningExerciseId/attempts',
      (_) => Reply(201, {'attempt': listeningAttemptJson(), 'conversation': null, 'job': null}));
  backend.on('PATCH /attempts/$listeningAttemptId/draft', (r) {
    final body = r.body as Map<String, dynamic>;
    drafts?.add(body);
    for (final a in (body['draft'] as Map)['answers'] as List) {
      selections[(a as Map)['question_id'] as String] = a['selected_option_id'] as String;
    }
    revision = (body['revision'] as int) + 1;
    return Reply(200, {
      'attempt_id': listeningAttemptId,
      'revision': revision,
      'last_saved_at': '2026-11-17T09:00:00Z',
      'last_activity_at': '2026-11-17T09:00:00Z',
    });
  });
  backend.on('POST /attempts/$listeningAttemptId/submit', (r) {
    final correct = listeningQuestions.where((q) => selections[q.$1] == '${q.$1}-o${q.$4}').length;
    return Reply(200, {
      'attempt': listeningAttemptJson(status: 'completed', revision: revision + 1),
      'evaluation': {
        'evaluation_id': 'lev-1',
        'attempt_id': listeningAttemptId,
        'status': 'completed',
        'overall_score': 0,
        'max_score': 100,
        'rubric_version': 'listening-quiz-v1',
        'summary': null,
        'corrected_text': null,
        'feedback_payload': {'schema_version': 1, 'corrections': <Object>[], 'limitations': <Object>[]},
        'criteria': <Object>[],
        'quiz_summary': {
          'question_count': listeningQuestions.length,
          'graded_count': listeningQuestions.length,
          'correct_count': correct,
          'awarded_points': correct,
          'max_points': listeningQuestions.length,
        },
        'created_at': '2026-11-17T09:00:00Z',
        'completed_at': '2026-11-17T09:00:01Z',
      },
    });
  });
  for (final q in listeningQuestions) {
    backend.on('GET /attempts/$listeningAttemptId/answers/${q.$1}/feedback', (_) {
      final correctId = '${q.$1}-o${q.$4}';
      return Reply(200, {
        'answer_id': 'a-${q.$1}',
        'question_id': q.$1,
        'grading_status': 'graded',
        'awarded_points': selections[q.$1] == correctId ? 1 : 0,
        'max_points': 1,
        'is_correct': selections[q.$1] == correctId,
        'correct_option_id': correctId,
        'reference_answer': null,
        'explanation': 'Explained ${q.$1}.',
        'evidence_spans': <Object>[],
      });
    });
  }
  backend.on('GET /attempts/$listeningAttemptId/transcript', (_) => Reply(200, {
        'exercise_id': listeningExerciseId,
        'transcript': transcript,
        'evidence': [
          {'question_id': 'q1', 'spans': [evidenceSpan('I would like a chicken sandwich.')]},
          {'question_id': 'q2', 'spans': [evidenceSpan('I will sit near the window.')]},
        ],
      }));
}
