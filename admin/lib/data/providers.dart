import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day_admin/data/admin_repository.dart';
import 'package:english_day_admin/data/demo_admin_repository.dart';
import 'package:english_day_admin/data/models.dart';

/// Swap this for the API implementation once the backend has admin endpoints.
final adminRepositoryProvider = Provider<AdminRepository>((ref) => DemoAdminRepository());

/// The signed-in admin, or null (the router then shows the login page).
class AdminSession extends Notifier<AdminUser?> {
  @override
  AdminUser? build() => null;

  Future<void> login({required String email, required String password}) async {
    state = await ref.read(adminRepositoryProvider).login(email: email, password: password);
  }

  Future<void> logout() async {
    await ref.read(adminRepositoryProvider).logout();
    state = null;
  }
}

final adminSessionProvider = NotifierProvider<AdminSession, AdminUser?>(AdminSession.new);

final dashboardProvider = FutureProvider.autoDispose<DashboardSummary>(
    (ref) => ref.watch(adminRepositoryProvider).dashboard());

/// Filters of a student list (records compare by value, so they work as family keys).
typedef StudentQuery = ({String query, int? grade, String? classId, int page});

final studentsProvider = FutureProvider.autoDispose.family<PageResult<StudentSummary>, StudentQuery>(
  (ref, q) => ref
      .watch(adminRepositoryProvider)
      .students(query: q.query, grade: q.grade, classId: q.classId, page: q.page),
);

final classesProvider = FutureProvider.autoDispose.family<List<SchoolClass>, int?>(
    (ref, grade) => ref.watch(adminRepositoryProvider).classes(grade: grade));

final classProvider = FutureProvider.autoDispose.family<SchoolClass, String>(
    (ref, id) => ref.watch(adminRepositoryProvider).schoolClass(id));

final studentDetailProvider = FutureProvider.autoDispose.family<StudentDetail, String>(
    (ref, id) => ref.watch(adminRepositoryProvider).student(id));

final exerciseDetailProvider = FutureProvider.autoDispose.family<ExerciseDetail, (String, String)>(
    (ref, ids) => ref.watch(adminRepositoryProvider).exercise(ids.$1, ids.$2));
