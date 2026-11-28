import 'package:flutter_test/flutter_test.dart';

import 'package:english_day_admin/data/admin_repository.dart';
import 'package:english_day_admin/data/demo_admin_repository.dart';
import 'package:english_day_admin/data/models.dart';

void main() {
  final repo = DemoAdminRepository(latency: Duration.zero);

  test('a school of about 500 students in 12 classes (4 per grade)', () async {
    final all = await repo.students(pageSize: 1000);
    final classes = await repo.classes();
    expect(all.total, inInclusiveRange(450, 560));
    expect(classes, hasLength(12));
    for (final grade in [10, 11, 12]) {
      expect(classes.where((c) => c.grade == grade).map((c) => c.name).toList(), hasLength(4));
    }
    expect(classes.first.name, 'X-A');
    expect(classes.fold<int>(0, (sum, c) => sum + c.studentCount), all.total);
  });

  test('the data is the same on every run (fixed seed)', () async {
    final again = DemoAdminRepository(latency: Duration.zero);
    expect((await again.students()).items.first.name, (await repo.students()).items.first.name);
  });

  test('search by name or student ID, filter by grade, paginate', () async {
    final first = (await repo.students()).items.first;

    final byId = await repo.students(query: first.studentNumber.toLowerCase());
    expect(byId.items.map((s) => s.id), contains(first.id));

    final byName = await repo.students(query: first.name.split(' ').first);
    expect(byName.items.every((s) => s.name.contains(first.name.split(' ').first)), isTrue);

    final grade12 = await repo.students(grade: 12, pageSize: 1000);
    expect(grade12.items.every((s) => s.grade == 12), isTrue);

    final page2 = await repo.students(page: 2);
    expect(page2.items, hasLength(10));
    expect(page2.firstIndex, 11);
    expect(page2.lastIndex, 20);

    final none = await repo.students(query: 'zzz-nobody');
    expect(none.total, 0);
    expect(none.items, isEmpty);
  });

  test('a class lists only its own students', () async {
    final xa = (await repo.classes(grade: 10)).first;
    final members = await repo.students(classId: xa.id, pageSize: 100);
    expect(members.total, xa.studentCount);
    expect(members.items.every((s) => s.className == 'X-A'), isTrue);
  });

  test('student detail matches the summary shown in the tables', () async {
    final s = (await repo.students()).items.first;
    final d = await repo.student(s.id);
    expect(d.history, hasLength(s.completedExercises));
    expect(d.modules.fold<int>(0, (sum, m) => sum + m.submitted), s.completedExercises);
    for (var i = 1; i < d.history.length; i++) {
      expect(d.history[i - 1].completedAt.isAfter(d.history[i].completedAt), isTrue,
          reason: 'history is newest first');
    }
  });

  test('exercise detail carries the content of its module', () async {
    final students = (await repo.students(pageSize: 1000)).items;
    final seen = <Skill>{};
    for (final s in students) {
      for (final r in (await repo.student(s.id)).history) {
        if (!seen.add(r.skill)) continue;
        final d = await repo.exercise(s.id, r.id);
        expect(d.score, r.score);
        switch (r.skill) {
          case Skill.writing:
            expect(d.submission, isNotEmpty);
            expect(d.corrections, isNotEmpty);
            for (final c in d.corrections) {
              expect(d.submission, contains(c.original));
            }
          case Skill.reading:
            expect(d.passage, isNotEmpty);
            expect(d.answers, hasLength(5));
          case Skill.speaking:
            expect(d.conversation.where((t) => !t.fromAi), isNotEmpty);
            expect(d.criteria.where((c) => c.score == null), hasLength(2),
                reason: 'fluency and pronunciation are not assessed, as in the real backend');
          case Skill.listening:
            expect(d.transcript, isNotEmpty);
            expect(d.answers, hasLength(3));
        }
      }
      if (seen.length == Skill.values.length) break;
    }
    expect(seen, Skill.values.toSet());
  });

  test('login accepts only the demo admin', () async {
    expect(
      () => repo.login(email: 'someone@sman10gowa.sch.id', password: 'admin123'),
      throwsA(isA<InvalidCredentialsException>()),
    );
    final admin = await repo.login(email: ' ADMIN@sman10gowa.sch.id ', password: 'admin123');
    expect(admin.initials, 'AS');
  });
}
