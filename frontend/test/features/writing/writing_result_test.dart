import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/text/text_span_offsets.dart';
import 'package:english_day/features/writing/data/writing_result.dart';

WritingCorrection fix(int start, int end, String original, String replacement, [String id = 'c']) =>
    WritingCorrection(
      id: id,
      start: start,
      end: end,
      original: original,
      replacement: replacement,
      title: 't',
      explanation: 'e',
      example: 'x',
    );

void main() {
  group('code point offsets', () {
    test('emoji counts as one code point but two UTF-16 units', () {
      const text = 'Hi 😀 go';
      // code points: H i ␠ 😀 ␠ g o  -> "go" is [5, 7)
      expect(spanToUtf16(text, 5, 7, expected: 'go'), (6, 8));
      expect(text.substring(6, 8), 'go');
    });

    test('rejects spans out of range or not matching original', () {
      expect(spanToUtf16('abc', 1, 9), isNull);
      expect(spanToUtf16('abc', 0, 1, expected: 'b'), isNull);
    });
  });

  group('buildCorrectionTokens', () {
    test('marks corrected words and keeps the others', () {
      final tokens = buildCorrectionTokens('I go home.', [fix(2, 4, 'go', 'went')]);
      expect(tokens.map((t) => t.text), ['I', 'go', 'home.']);
      expect(tokens[1].correction, 'went');
      expect(tokens.where((t) => t.isWrong), hasLength(1));
    });

    test('a correction right before punctuation has no space after it', () {
      final tokens = buildCorrectionTokens('my friend, and', [fix(3, 9, 'friend', 'friends')]);
      expect(tokens.map((t) => t.text), ['my', 'friend', ',', 'and']);
      expect(tokens[1].trailingSpace, isFalse); // "friends," not "friends ,"
      expect(tokens[2].trailingSpace, isTrue);
    });

    test('uses code points, so text after an emoji is still matched', () {
      const text = '😀 I go';
      final tokens = buildCorrectionTokens(text, [fix(4, 6, 'go', 'went')]);
      expect(tokens.last.text, 'go');
      expect(tokens.last.correction, 'went');
    });

    test('skips spans that do not match the text instead of failing', () {
      final tokens = buildCorrectionTokens('I go home', [
        fix(2, 4, 'went', 'go', 'wrong-original'),
        fix(5, 99, 'home', 'house', 'out-of-range'),
      ]);
      expect(tokens.where((t) => t.isWrong), isEmpty);
      expect(tokens.map((t) => t.text).join(' '), 'I go home');
    });

    test('result without valid corrections counts as correct', () {
      final result = WritingResult(text: 'All good.', correctedText: 'All good.', corrections: const []);
      expect(result.hasCorrections, isFalse);
      expect(result.bestText, 'All good.');
    });
  });
}
