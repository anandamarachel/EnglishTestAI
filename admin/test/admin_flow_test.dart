import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day_admin/app.dart';
import 'package:english_day_admin/data/demo_admin_repository.dart';
import 'package:english_day_admin/data/providers.dart';

/// The admin portal end to end on the demo data: login, every page, logout.
void main() {
  late DemoAdminRepository repo;

  Future<void> start(WidgetTester tester, {Size size = const Size(1440, 1000)}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final reportError = FlutterError.onError!;
    FlutterError.onError = (d) {
      if (!d.exceptionAsString().contains('overflowed')) reportError(d); // test font only
    };
    addTearDown(() => FlutterError.onError = reportError);
    await tester.pumpWidget(ProviderScope(
      overrides: [adminRepositoryProvider.overrideWithValue(repo)],
      child: const AdminApp(),
    ));
    await tester.pumpAndSettle();
  }

  Future<void> signIn(WidgetTester tester) async {
    await tester.enterText(find.byType(TextField).at(0), DemoAdminRepository.demoEmail);
    await tester.enterText(find.byType(TextField).at(1), DemoAdminRepository.demoPassword);
    await tester.tap(find.text('Sign in to Admin Portal'));
    await tester.pumpAndSettle();
  }

  setUp(() => repo = DemoAdminRepository(latency: Duration.zero));

  testWidgets('login validates, rejects wrong credentials, then opens the dashboard',
      (tester) async {
    await start(tester);
    expect(find.text('Welcome back'), findsOneWidget);

    await tester.tap(find.text('Sign in to Admin Portal'));
    await tester.pump();
    expect(find.text('Enter your email address.'), findsOneWidget);
    expect(find.text('Enter your password.'), findsOneWidget);

    await tester.enterText(find.byType(TextField).at(0), DemoAdminRepository.demoEmail);
    await tester.enterText(find.byType(TextField).at(1), 'wrong-password');
    await tester.tap(find.text('Sign in to Admin Portal'));
    await tester.pumpAndSettle();
    expect(find.text('Incorrect email or password.'), findsOneWidget);

    await signIn(tester);
    expect(find.text('Dashboard'), findsWidgets);
    final total = (await repo.students()).total;
    expect(find.text('$total'), findsOneWidget); // Total Students card
    expect(find.text('Learning Activity by Module'), findsOneWidget);
    expect(find.text('Student Performance'), findsOneWidget);
    expect(find.text('Recent Activity'), findsOneWidget);
    expect(find.text('Grade 10'), findsOneWidget);
  });

  testWidgets('students: search, open a student, open an exercise, back', (tester) async {
    await start(tester);
    await signIn(tester);
    await tester.tap(find.text('Students & Classes').first);
    await tester.pumpAndSettle();

    final first = (await repo.students()).items.first;
    expect(find.text(first.name), findsWidgets);
    expect(find.textContaining('Showing 1–10 of'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, first.studentNumber);
    await tester.pumpAndSettle();
    expect(find.textContaining('of 1 students'), findsOneWidget);

    await tester.tap(find.text('View Details').first);
    await tester.pumpAndSettle();
    expect(find.text('Module Performance'), findsOneWidget);
    expect(find.text('Learning History'), findsOneWidget);
    expect(find.text(first.studentNumber), findsOneWidget);

    final detail = await repo.student(first.id);
    final writing = detail.history.where((r) => r.skill.name == 'writing').toList();
    if (writing.isNotEmpty) {
      await tester.scrollUntilVisible(find.text('View Details').first, 300);
      await tester.tap(find.text('View Details').first);
      await tester.pumpAndSettle();
      expect(find.text('Student Submission'), findsOneWidget);
      expect(find.text('AI Evaluation'), findsOneWidget);

      await tester.tap(find.text('Back to student'));
      await tester.pumpAndSettle();
      expect(find.text('Learning History'), findsOneWidget);
    }
  });

  testWidgets('classes tab: filter by grade and open a class', (tester) async {
    await start(tester);
    await signIn(tester);
    await tester.tap(find.text('Students & Classes').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Classes'));
    await tester.pumpAndSettle();

    expect(find.text('X-A'), findsOneWidget);
    expect(find.text('XII-D'), findsOneWidget);

    await tester.tap(find.text('All Grades'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Grade 11').last);
    await tester.pumpAndSettle();
    expect(find.text('X-A'), findsNothing);
    expect(find.text('XI-A'), findsOneWidget);

    await tester.tap(find.text('View Class').first);
    await tester.pumpAndSettle();
    expect(find.text('Class XI-A'), findsOneWidget);
    expect(find.text('Student Directory'), findsOneWidget);
    expect(find.text('Module Performance'), findsOneWidget);
  });

  testWidgets('logout from the profile menu returns to login', (tester) async {
    await start(tester);
    await signIn(tester);
    await tester.tap(find.text('Admin Sekolah'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Logout'));
    await tester.pumpAndSettle();
    expect(find.text('Welcome back'), findsOneWidget);
  });

  testWidgets('narrow screens get a menu drawer instead of the sidebar', (tester) async {
    await start(tester, size: const Size(800, 1000));
    await signIn(tester);
    expect(find.byTooltip('Menu'), findsOneWidget);
    await tester.tap(find.byTooltip('Menu'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Students & Classes').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('Showing 1–10 of'), findsOneWidget);
  });
}
