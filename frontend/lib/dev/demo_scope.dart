import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/auth/data/user.dart';
import 'package:english_day/features/dashboard/data/dashboard.dart';

/// Demo account shown in the design gallery (never sent to the server).
final demoUser = User(
  userId: '00000000-0000-4000-8000-000000000001',
  email: DummyUser.email,
  displayName: DummyUser.name,
  role: 'student',
  createdAt: DateTime.utc(2026, 11, 9),
);

DashboardData demoDashboard({required bool withResume}) => DashboardData(
      user: demoUser,
      resumeAttempt: withResume
          ? const AttemptSummary(
              attemptId: '00000000-0000-4000-8000-000000000003',
              exerciseId: '00000000-0000-4000-8000-000000000002',
              skill: 'reading',
              title: ReadingDummy.storyTitle,
              status: 'in_progress',
              currentStage: 'reading',
            )
          : null,
      pendingAttempts: const [],
      hasMorePending: false,
    );

/// Runs [child] with the demo account and demo dashboard instead of the real API,
/// so gallery screens look like the designs without a backend.
class DemoScope extends StatelessWidget {
  const DemoScope({super.key, required this.child, this.withResume = true});

  final Widget child;
  final bool withResume;

  @override
  Widget build(BuildContext context) {
    return ProviderScope(
      overrides: [
        // Every provider a gallery screen reads is overridden here: a nested scope
        // cannot mix overridden and app-level providers that depend on each other.
        sessionControllerProvider.overrideWith(_DemoSession.new),
        currentUserProvider.overrideWithValue(demoUser),
        dashboardProvider.overrideWith((ref) async => demoDashboard(withResume: withResume)),
      ],
      child: child,
    );
  }
}

class _DemoSession extends SessionController {
  @override
  Future<Session> build() async => Session.loggedIn(demoUser);

  @override
  Future<void> logout() async => state = const AsyncData(Session.loggedOut());
}
