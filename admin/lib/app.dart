import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/core/widgets/admin_shell.dart';
import 'package:english_day_admin/data/providers.dart';
import 'package:english_day_admin/features/auth/login_screen.dart';
import 'package:english_day_admin/features/dashboard/dashboard_screen.dart';
import 'package:english_day_admin/features/students/class_detail_screen.dart';
import 'package:english_day_admin/features/students/exercise_detail_screen.dart';
import 'package:english_day_admin/features/students/student_detail_screen.dart';
import 'package:english_day_admin/features/students/students_classes_screen.dart';

/// Every page has its own URL, so admins can bookmark, refresh and use the
/// browser's back button:
///   /login · /dashboard · /students[?tab=classes] · /classes/:classId
///   /students/:studentId · /students/:studentId/exercises/:exerciseId
final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<int>(0);
  ref.listen(adminSessionProvider, (_, __) => refresh.value++);
  ref.onDispose(refresh.dispose);

  Page<void> page(GoRouterState state, Widget child) =>
      NoTransitionPage<void>(key: state.pageKey, child: child);

  return GoRouter(
    initialLocation: '/dashboard',
    refreshListenable: refresh,
    redirect: (context, state) {
      final signedIn = ref.read(adminSessionProvider) != null;
      final atLogin = state.matchedLocation == '/login';
      if (!signedIn && !atLogin) {
        final from = state.uri.toString();
        return from == '/dashboard' ? '/login' : '/login?from=${Uri.encodeComponent(from)}';
      }
      if (signedIn && atLogin) return state.uri.queryParameters['from'] ?? '/dashboard';
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (_, __) => '/dashboard'),
      GoRoute(path: '/login', pageBuilder: (_, state) => page(state, const LoginScreen())),
      ShellRoute(
        builder: (context, state, child) => AdminShell(location: state.matchedLocation, child: child),
        routes: [
          GoRoute(path: '/dashboard', pageBuilder: (_, state) => page(state, const DashboardScreen())),
          // Flat on purpose (not nested under /students): a nested route keeps the list
          // page mounted offstage under the detail page, which breaks its LayoutBuilders.
          GoRoute(
            path: '/students',
            pageBuilder: (_, state) => page(
              state,
              StudentsClassesScreen(showClasses: state.uri.queryParameters['tab'] == 'classes'),
            ),
          ),
          GoRoute(
            path: '/students/:studentId',
            pageBuilder: (_, state) =>
                page(state, StudentDetailScreen(studentId: state.pathParameters['studentId']!)),
          ),
          GoRoute(
            path: '/students/:studentId/exercises/:exerciseId',
            pageBuilder: (_, state) => page(
              state,
              ExerciseDetailScreen(
                studentId: state.pathParameters['studentId']!,
                exerciseId: state.pathParameters['exerciseId']!,
              ),
            ),
          ),
          GoRoute(
            path: '/classes/:classId',
            pageBuilder: (_, state) =>
                page(state, ClassDetailScreen(classId: state.pathParameters['classId']!)),
          ),
        ],
      ),
    ],
  );
});

class AdminApp extends ConsumerWidget {
  const AdminApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
        title: 'English Day Admin',
        debugShowCheckedModeBanner: false,
        theme: AdminTheme.light,
        routerConfig: ref.watch(routerProvider),
      );
}
