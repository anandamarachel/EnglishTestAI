import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/providers.dart';
import 'package:english_day/features/auth/data/user.dart';

/// Short attempt info (`AttemptSummary`) used by the dashboard card.
class AttemptSummary {
  const AttemptSummary({
    required this.attemptId,
    required this.exerciseId,
    required this.skill,
    required this.title,
    required this.status,
    required this.currentStage,
  });

  final String attemptId;
  final String exerciseId;

  /// writing | reading | listening | speaking
  final String skill;
  final String title;
  final String status;
  final String currentStage;

  factory AttemptSummary.fromJson(Map<String, dynamic> json) => AttemptSummary(
        attemptId: json['attempt_id'] as String,
        exerciseId: json['exercise_id'] as String,
        skill: json['skill'] as String,
        title: (json['title'] as String?) ?? '',
        status: json['status'] as String,
        currentStage: json['current_stage'] as String,
      );

  String get skillLabel => switch (skill) {
        'writing' => 'Writing',
        'reading' => 'Reading',
        'listening' => 'Listening',
        'speaking' => 'Speaking',
        _ => skill,
      };
}

/// `GET /dashboard`.
class DashboardData {
  const DashboardData({
    required this.user,
    required this.resumeAttempt,
    required this.pendingAttempts,
    required this.hasMorePending,
  });

  final User user;

  /// Most recently active in-progress practice, or null (new user / nothing open).
  final AttemptSummary? resumeAttempt;

  /// Submitted practices still being evaluated by the AI.
  final List<AttemptSummary> pendingAttempts;
  final bool hasMorePending;

  factory DashboardData.fromJson(Map<String, dynamic> json) => DashboardData(
        user: User.fromJson(json['user'] as Map<String, dynamic>),
        resumeAttempt: json['resume_attempt'] == null
            ? null
            : AttemptSummary.fromJson(json['resume_attempt'] as Map<String, dynamic>),
        pendingAttempts: [
          for (final a in (json['pending_attempts'] as List?) ?? const [])
            AttemptSummary.fromJson(a as Map<String, dynamic>),
        ],
        hasMorePending: json['has_more_pending'] == true,
      );
}

/// Reloaded every time the dashboard is opened again (autoDispose) or pulled to refresh.
final dashboardProvider = FutureProvider.autoDispose<DashboardData>((ref) async {
  final body = await ref.watch(apiClientProvider).get('/dashboard');
  return DashboardData.fromJson(body as Map<String, dynamic>);
});
