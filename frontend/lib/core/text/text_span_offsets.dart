/// Backend text spans (`start`/`end`) count Unicode code points, but Dart strings
/// are indexed in UTF-16 code units: an emoji is 1 code point but 2 units.
///
/// Returns the UTF-16 index of every code point position 0..n (both ends included),
/// so `offsets[start]` and `offsets[end]` can be used with `substring`.
List<int> codePointToUtf16Offsets(String text) {
  final offsets = <int>[0];
  var index = 0;
  for (final rune in text.runes) {
    index += rune > 0xFFFF ? 2 : 1;
    offsets.add(index);
  }
  return offsets;
}

/// UTF-16 `[start, end)` for a backend span, or null when it does not fit [text]
/// or does not cover [expected] (the span's `original`), as the backend asks
/// clients to verify both.
(int, int)? spanToUtf16(String text, int start, int end, {String? expected}) {
  final offsets = codePointToUtf16Offsets(text);
  if (start < 0 || end < start || end >= offsets.length) return null;
  final range = (offsets[start], offsets[end]);
  if (expected != null && text.substring(range.$1, range.$2) != expected) return null;
  return range;
}
