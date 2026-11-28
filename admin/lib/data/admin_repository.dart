import 'package:english_day_admin/data/models.dart';

/// Wrong email/password on the login screen.
class InvalidCredentialsException implements Exception {
  const InvalidCredentialsException();
}

/// Everything the admin screens read. The screens only know this interface:
/// today it is backed by [DemoAdminRepository] (dummy data); once the backend has
/// admin endpoints, an API implementation replaces it without touching the UI.
abstract interface class AdminRepository {
  Future<AdminUser> login({required String email, required String password});
  Future<void> logout();

  Future<DashboardSummary> dashboard();

  /// Students of the whole school, or of one class when [classId] is given.
  Future<PageResult<StudentSummary>> students({
    String query = '',
    int? grade,
    String? classId,
    int page = 1,
    int pageSize = 10,
  });

  Future<List<SchoolClass>> classes({int? grade});
  Future<SchoolClass> schoolClass(String classId);

  Future<StudentDetail> student(String studentId);
  Future<ExerciseDetail> exercise(String studentId, String exerciseId);
}
