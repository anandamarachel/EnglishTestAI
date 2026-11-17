/// `User` from the backend (`GET /users/me`, login, register, dashboard).
class User {
  const User({
    required this.userId,
    required this.email,
    required this.displayName,
    required this.role,
    required this.createdAt,
  });

  final String userId;
  final String email;
  final String displayName;

  /// `student` or `teacher` (a profile label only; both have the same permissions).
  final String role;
  final DateTime createdAt;

  factory User.fromJson(Map<String, dynamic> json) => User(
        userId: json['user_id'] as String,
        email: json['email'] as String,
        displayName: json['display_name'] as String,
        role: json['user_role'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  /// "Rina Amelia" -> "Rina" (dashboard greeting).
  String get firstName => displayName.trim().split(RegExp(r'\s+')).first;

  /// "Rina Amelia" -> "RA", "Rina" -> "R" (avatar).
  String get initials {
    final words = displayName.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty);
    // runes (not [0]) so a name starting with an emoji is not cut in half.
    return words.take(2).map((w) => String.fromCharCode(w.runes.first).toUpperCase()).join();
  }

  String get roleLabel => role == 'teacher' ? 'Guru' : 'Siswa';
}

/// UI labels -> backend `user_role`.
const roleByLabel = {'Siswa': 'student', 'Guru': 'teacher'};
