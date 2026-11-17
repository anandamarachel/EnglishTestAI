import 'package:english_day/core/text/text_span_offsets.dart';
import 'package:english_day/core/widgets/lined_paper.dart';

/// Characters the input screen accepts (design limit; the backend has none).
const writingMaxChars = 500;

/// One AI correction of the original text (`feedback_payload.corrections[]`).
/// [start]/[end] count Unicode code points in the ORIGINAL text, never in
/// `corrected_text`.
class WritingCorrection {
  const WritingCorrection({
    required this.id,
    required this.start,
    required this.end,
    required this.original,
    required this.replacement,
    required this.title,
    required this.explanation,
    required this.example,
    this.category = 'grammar',
  });

  factory WritingCorrection.fromJson(Map<String, dynamic> json) => WritingCorrection(
        id: json['correction_id'] as String,
        start: json['start'] as int,
        end: json['end'] as int,
        original: json['original'] as String,
        replacement: json['replacement'] as String,
        category: (json['category'] as String?) ?? 'grammar',
        title: (json['title'] as String?) ?? '',
        explanation: (json['explanation'] as String?) ?? '',
        example: (json['example'] as String?) ?? '',
      );

  final String id;
  final int start;
  final int end;
  final String original;
  final String replacement;

  /// grammar | spelling | vocabulary | style
  final String category;
  final String title;
  final String explanation;
  final String example;
}

/// What the result screen shows: the submitted text and its AI evaluation.
class WritingResult {
  WritingResult({required this.text, required this.correctedText, required this.corrections});

  /// From `GET /attempts/{id}/evaluation` (or the evaluation inside an attempt).
  factory WritingResult.fromEvaluation(String text, Map<String, dynamic> evaluation) {
    final payload = (evaluation['feedback_payload'] as Map<String, dynamic>?) ?? const {};
    return WritingResult(
      text: text,
      correctedText: evaluation['corrected_text'] as String?,
      corrections: [
        for (final c in (payload['corrections'] as List?) ?? const [])
          WritingCorrection.fromJson(c as Map<String, dynamic>),
      ],
    );
  }

  final String text;
  final String? correctedText;
  final List<WritingCorrection> corrections;

  /// Word tokens for [CorrectionText]; corrections that do not match [text] are dropped.
  late final List<CorrectionToken> tokens = buildCorrectionTokens(text, corrections);

  late final int correctionCount = tokens.where((t) => t.isWrong).length;
  bool get hasCorrections => correctionCount > 0;

  WritingCorrection? correctionFor(CorrectionToken token) {
    for (final c in corrections) {
      if (c.id == token.ruleId) return c;
    }
    return null;
  }

  /// "Versi benar" when there are corrections, otherwise the text as written.
  String get bestText => hasCorrections ? (correctedText ?? text) : text;
}

/// Splits [text] into word tokens and turns each valid correction span into one
/// struck-through token (its `ruleId` is the correction id).
///
/// Spans are validated as the backend asks: in range, non-overlapping, and covering
/// exactly `original`. Invalid ones are skipped instead of breaking the screen.
List<CorrectionToken> buildCorrectionTokens(String text, List<WritingCorrection> corrections) {
  final offsets = codePointToUtf16Offsets(text);
  final pieces = <(int, int, WritingCorrection?)>[]; // UTF-16 [start, end), correction
  var cursor = 0;

  void addWords(int from, int to) {
    for (final m in RegExp(r'\S+').allMatches(text.substring(from, to))) {
      pieces.add((from + m.start, from + m.end, null));
    }
  }

  final sorted = [...corrections]..sort((a, b) => a.start.compareTo(b.start));
  for (final c in sorted) {
    if (c.start < 0 || c.end < c.start || c.end >= offsets.length) continue;
    final start = offsets[c.start];
    final end = offsets[c.end];
    if (start < cursor || text.substring(start, end) != c.original) continue;
    addWords(cursor, start);
    pieces.add((start, end, c));
    cursor = end;
  }
  addWords(cursor, text.length);

  bool spaceAt(int i) => i >= text.length || text[i].trim().isEmpty;
  return [
    for (final (start, end, c) in pieces)
      CorrectionToken(
        text.substring(start, end),
        correction: c?.replacement,
        ruleId: c?.id,
        trailingSpace: spaceAt(end),
      ),
  ];
}
