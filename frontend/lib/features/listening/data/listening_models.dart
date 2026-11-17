import 'package:english_day/core/models/choice_question.dart';
import 'package:english_day/core/text/text_span_offsets.dart';

/// "Medium" etc. for the backend difficulty, as on the Reading level chips.
String levelName(String difficulty) => switch (difficulty) {
      'beginner' => 'Easy',
      'advanced' => 'Hard',
      _ => 'Medium',
    };

/// A ready Listening exercise (`GET /exercises/{id}`): its audio and questions.
/// The transcript is never part of it; it unlocks after submitting.
class ListeningExercise {
  const ListeningExercise({
    required this.exerciseId,
    required this.title,
    required this.level,
    required this.topicName,
    required this.audioMediaId,
    required this.audioMimeType,
    required this.duration,
    required this.questions,
  });

  factory ListeningExercise.fromJson(Map<String, dynamic> json) {
    final content = json['content'] as Map<String, dynamic>;
    final audio = content['audio'] as Map<String, dynamic>;
    final topic = json['topic'] as Map<String, dynamic>?;
    return ListeningExercise(
      exerciseId: json['exercise_id'] as String,
      title: (json['title'] as String?) ?? 'Listening',
      level: levelName(json['difficulty'] as String),
      topicName: (topic?['name'] as String?) ?? 'Acak',
      audioMediaId: audio['media_id'] as String,
      audioMimeType: (audio['mime_type'] as String?) ?? 'audio/wav',
      duration: Duration(milliseconds: (audio['duration_ms'] as int?) ?? 0),
      questions: ChoiceQuestion.listFromJson(json['questions'] as List?),
    );
  }

  final String exerciseId;
  final String title;
  final String level;
  final String topicName;
  final String audioMediaId;
  final String audioMimeType;

  /// From the media metadata; the player's own duration wins once it is known.
  final Duration duration;
  final List<ChoiceQuestion> questions;

  /// "Medium · Sekolah"
  String get meta => '$level · $topicName';
}

/// One transcript line; [evidence] lines support a graded answer (highlighted).
class TranscriptLine {
  const TranscriptLine(this.text, {this.evidence = false});
  final String text;
  final bool evidence;
}

/// `GET /attempts/{id}/transcript`: lines, marking those that overlap an evidence
/// span (code points over the whole transcript).
List<TranscriptLine> transcriptLines(Map<String, dynamic> json) {
  final transcript = json['transcript'] as String;
  final offsets = codePointToUtf16Offsets(transcript);
  final spans = <(int, int)>[];
  for (final e in (json['evidence'] as List?) ?? const []) {
    for (final s in ((e as Map<String, dynamic>)['spans'] as List?) ?? const []) {
      final span = s as Map<String, dynamic>;
      final start = span['start'] as int;
      final end = span['end'] as int;
      if (start < 0 || end < start || end >= offsets.length) continue;
      final range = (offsets[start], offsets[end]);
      if (transcript.substring(range.$1, range.$2) != span['original']) continue;
      spans.add(range);
    }
  }
  final lines = <TranscriptLine>[];
  var from = 0;
  for (final raw in transcript.split('\n')) {
    final to = from + raw.length;
    if (raw.trim().isNotEmpty) {
      final evidence = spans.any((s) => s.$1 < to && s.$2 > from);
      lines.add(TranscriptLine(raw.trim(), evidence: evidence));
    }
    from = to + 1;
  }
  return lines;
}

/// What the result part of the screen shows.
class ListeningResult {
  const ListeningResult({
    required this.correct,
    required this.total,
    required this.answers,
    required this.transcript,
  });

  final int correct;
  final int total;

  /// Graded answers by question id.
  final Map<String, GradedAnswer> answers;
  final List<TranscriptLine> transcript;
}
