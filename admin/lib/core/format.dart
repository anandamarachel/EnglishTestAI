/// Small formatters (no intl dependency needed for these few patterns).
library;

const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/// "Nov 21, 2026"
String formatDate(DateTime d) => '${_months[d.month - 1]} ${d.day}, ${d.year}';

/// "10:30 AM"
String formatTime(DateTime d) {
  final hour = d.hour % 12 == 0 ? 12 : d.hour % 12;
  final minute = d.minute.toString().padLeft(2, '0');
  return '$hour:$minute ${d.hour < 12 ? 'AM' : 'PM'}';
}

/// "Nov 21, 2026 • 10:30 AM"
String formatDateTime(DateTime d) => '${formatDate(d)} • ${formatTime(d)}';

/// "Today, 10:30 AM", "Yesterday", "3 days ago", or a date.
String formatRelative(DateTime d, {DateTime? now}) {
  final today = now ?? DateTime.now();
  final days = DateTime(today.year, today.month, today.day)
      .difference(DateTime(d.year, d.month, d.day))
      .inDays;
  if (days <= 0) return 'Today, ${formatTime(d)}';
  if (days == 1) return 'Yesterday';
  if (days < 7) return '$days days ago';
  return formatDate(d);
}

/// "Today", "Yesterday", "3 days ago", or a date (no time).
String formatRelativeDay(DateTime d, {DateTime? now}) {
  final relative = formatRelative(d, now: now);
  return relative.startsWith('Today') ? 'Today' : relative;
}

/// "12h 30m"
String formatDuration(Duration d) {
  final h = d.inHours;
  final m = d.inMinutes % 60;
  return h == 0 ? '${m}m' : '${h}h ${m}m';
}

/// "0:44", "12:05"
String formatClock(Duration d) =>
    '${d.inMinutes}:${(d.inSeconds % 60).toString().padLeft(2, '0')}';

/// 85.5 -> "85.5", 86.0 -> "86".
String formatScore(double? value) {
  if (value == null) return '–';
  return value == value.roundToDouble() ? value.toInt().toString() : value.toStringAsFixed(1);
}

/// 0.774 -> "77%"
String formatPercent(double fraction) => '${(fraction * 100).round()}%';
