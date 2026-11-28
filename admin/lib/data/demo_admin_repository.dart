import 'dart:math' as math;

import 'package:english_day_admin/data/admin_repository.dart';
import 'package:english_day_admin/data/models.dart';

/// Dummy school data for the UI slicing phase (no backend endpoints yet).
/// Generated from a fixed seed, so every run shows the same ~500 students.
class DemoAdminRepository implements AdminRepository {
  DemoAdminRepository({this.latency = const Duration(milliseconds: 250), DateTime? now})
      : _now = now ?? DateTime(2026, 11, 27, 14, 30) {
    _generate();
  }

  /// Simulated network delay (0 in tests).
  final Duration latency;
  final DateTime _now;

  static const demoEmail = 'admin@sman10gowa.sch.id';
  static const demoPassword = 'admin123';
  static const _admin = AdminUser(name: 'Admin Sekolah', email: demoEmail, role: 'Administrator');

  final _classes = <SchoolClass>[];
  final _students = <StudentSummary>[];
  final _history = <String, List<ExerciseRecord>>{};
  final _learningTime = <String, Duration>{};

  Future<T> _delay<T>(T Function() value) async {
    if (latency > Duration.zero) await Future<void>.delayed(latency);
    return value();
  }

  // ------------------------------------------------------------------ API

  @override
  Future<AdminUser> login({required String email, required String password}) => _delay(() {
        if (email.trim().toLowerCase() != demoEmail || password != demoPassword) {
          throw const InvalidCredentialsException();
        }
        return _admin;
      });

  @override
  Future<void> logout() => _delay(() {});

  @override
  Future<DashboardSummary> dashboard() => _delay(() {
        final all = [for (final h in _history.values) ...h];
        final modules = [
          for (final skill in Skill.values)
            ModuleActivity(
              skill: skill,
              submissions: all.where((r) => r.skill == skill).length,
              average: _avg(all.where((r) => r.skill == skill).map((r) => r.score)) ?? 0,
            ),
        ];
        final grades = [
          for (final grade in const [10, 11, 12])
            GradePerformance(
              grade: grade,
              average: _avg(_students
                      .where((s) => s.grade == grade && s.averageScore != null)
                      .map((s) => s.averageScore!)) ??
                  0,
              students: _students.where((s) => s.grade == grade).length,
              classes: _classes.where((c) => c.grade == grade).length,
            ),
        ];
        final byId = {for (final s in _students) s.id: s};
        final recent = [
          for (final entry in _history.entries)
            for (final r in entry.value) RecentActivity(student: byId[entry.key]!, record: r),
        ]..sort((a, b) => b.record.completedAt.compareTo(a.record.completedAt));
        return DashboardSummary(
          totalStudents: _students.length,
          activeStudents: _students.where((s) => s.active).length,
          totalClasses: _classes.length,
          averageScore: _avg(all.map((r) => r.score)) ?? 0,
          modules: modules,
          grades: grades,
          recent: recent.take(6).toList(),
        );
      });

  @override
  Future<PageResult<StudentSummary>> students({
    String query = '',
    int? grade,
    String? classId,
    int page = 1,
    int pageSize = 10,
  }) =>
      _delay(() {
        final q = query.trim().toLowerCase();
        final matches = _students.where((s) {
          if (grade != null && s.grade != grade) return false;
          if (classId != null && s.classId != classId) return false;
          if (q.isEmpty) return true;
          return s.name.toLowerCase().contains(q) || s.studentNumber.toLowerCase().contains(q);
        }).toList();
        final start = ((page - 1) * pageSize).clamp(0, matches.length);
        final end = (start + pageSize).clamp(0, matches.length);
        return PageResult(
          items: matches.sublist(start, end),
          page: page,
          pageSize: pageSize,
          total: matches.length,
        );
      });

  @override
  Future<List<SchoolClass>> classes({int? grade}) =>
      _delay(() => [for (final c in _classes) if (grade == null || c.grade == grade) c]);

  @override
  Future<SchoolClass> schoolClass(String classId) =>
      _delay(() => _classes.firstWhere((c) => c.id == classId, orElse: () => throw StateError('No class $classId')));

  @override
  Future<StudentDetail> student(String studentId) => _delay(() {
        final summary = _studentById(studentId);
        final history = _history[studentId]!;
        return StudentDetail(
          summary: summary,
          learningTime: _learningTime[studentId]!,
          modules: _moduleScores(history),
          history: history,
        );
      });

  @override
  Future<ExerciseDetail> exercise(String studentId, String exerciseId) => _delay(() {
        final student = _studentById(studentId);
        final record = _history[studentId]!.firstWhere((r) => r.id == exerciseId,
            orElse: () => throw StateError('No exercise $exerciseId'));
        return _detail(student, record);
      });

  StudentSummary _studentById(String id) =>
      _students.firstWhere((s) => s.id == id, orElse: () => throw StateError('No student $id'));

  // ------------------------------------------------------------ generation

  static const _firstNames = [
    'Andi', 'Siti', 'Budi', 'Nadia', 'Rizky', 'Dewi', 'Ahmad', 'Clarissa', 'Fajar', 'Putri',
    'Bayu', 'Intan', 'Dimas', 'Ayu', 'Rafi', 'Nurul', 'Yusuf', 'Citra', 'Arif', 'Salsabila',
    'Galih', 'Wulan', 'Irfan', 'Melati', 'Hendra', 'Rani', 'Taufik', 'Laras', 'Fikri', 'Anisa',
    'Reza', 'Dinda', 'Ilham', 'Maya', 'Aldi', 'Zahra', 'Daeng', 'Rina', 'Andika', 'Fitri',
  ];
  static const _lastNames = [
    'Pratama', 'Rahma', 'Santoso', 'Putri', 'Maulana', 'Lestari', 'Fauzi', 'Tan', 'Saputra',
    'Wijaya', 'Hidayat', 'Kurniawan', 'Amelia', 'Nugroho', 'Ramadhan', 'Syahputra', 'Halim',
    'Siregar', 'Gunawan', 'Permata', 'Setiawan', 'Anggraini', 'Firmansyah', 'Utami', 'Rasyid',
  ];
  static const _homerooms = [
    'Ibu Ratna Sari', 'Bapak Hasan', 'Ibu Marlina', 'Bapak Syamsul', 'Ibu Wahyuni',
    'Bapak Irwan', 'Ibu Fatimah', 'Bapak Darmawan', 'Ibu Kartini', 'Bapak Ridwan',
    'Ibu Sulastri', 'Bapak Amiruddin',
  ];
  static const _titles = {
    Skill.writing: [
      ('Daily Life Essay', 'Personal Routine & Grammar'),
      ('My Favorite Food', 'Descriptive Vocabulary'),
      ('A Memorable Holiday', 'Past Tense Narrative'),
      ('Technology in Daily Life', 'Argumentative Structure'),
      ('My Dream School', 'Future Plans'),
    ],
    Skill.reading: [
      ('A Trip to Bali', 'Reading Comprehension'),
      ('The Lost Kite', 'Narrative Text'),
      ('The Rich Heritage of Batik', 'Culture'),
      ('Saving the Coral Reefs', 'Environment'),
    ],
    Skill.speaking: [
      ('Introducing Yourself', 'Self Introduction'),
      ('Talking About Hobbies', 'Daily Conversation'),
      ('Ordering Food', 'Restaurant Role-play'),
    ],
    Skill.listening: [
      ('At the Restaurant', 'Conversation'),
      ('Planning a Weekend Trip', 'Travel'),
      ('At the School Canteen', 'School Life'),
    ],
  };

  void _generate() {
    final rnd = math.Random(42);
    var number = 0;
    var classIndex = 0;
    for (final grade in const [10, 11, 12]) {
      final roman = const {10: 'X', 11: 'XI', 12: 'XII'}[grade]!;
      for (final letter in const ['A', 'B', 'C', 'D']) {
        final classId = 'c-$grade-${letter.toLowerCase()}';
        final className = '$roman-$letter';
        final size = 38 + rnd.nextInt(8);
        final members = <StudentSummary>[];
        for (var i = 0; i < size; i++) {
          number++;
          final first = _firstNames[rnd.nextInt(_firstNames.length)];
          final last = _lastNames[rnd.nextInt(_lastNames.length)];
          final id = 's${number.toString().padLeft(3, '0')}';
          final active = rnd.nextDouble() < 0.78;
          final skillLevel = 62 + rnd.nextDouble() * 33; // the student's typical score
          final count = active ? 6 + rnd.nextInt(30) : rnd.nextInt(6);
          final history = <ExerciseRecord>[];
          // Newest first; practice happens between 07:00 and 21:00.
          var daysAgo = active ? rnd.nextInt(4) : 18 + rnd.nextInt(25);
          var minutes = 0;
          for (var k = 0; k < count; k++) {
            final roll = rnd.nextDouble();
            final skill = roll < 0.42
                ? Skill.writing
                : roll < 0.70
                    ? Skill.reading
                    : roll < 0.88
                        ? Skill.speaking
                        : Skill.listening;
            final options = _titles[skill]!;
            final (title, topic) = options[rnd.nextInt(options.length)];
            final score = (skillLevel + (rnd.nextDouble() - 0.5) * 18).clamp(40.0, 100.0).roundToDouble();
            var when = DateTime(_now.year, _now.month, _now.day - daysAgo, 7 + rnd.nextInt(14), rnd.nextInt(60));
            if (when.isAfter(_now)) when = _now.subtract(Duration(minutes: 5 + rnd.nextInt(300)));
            if (history.isNotEmpty && !when.isBefore(history.last.completedAt)) {
              when = history.last.completedAt.subtract(Duration(minutes: 30 + rnd.nextInt(120)));
            }
            history.add(ExerciseRecord(
              id: '$id-e$k',
              skill: skill,
              title: title,
              topic: topic,
              completedAt: when,
              score: score,
            ));
            minutes += 10 + rnd.nextInt(25);
            daysAgo += 1 + rnd.nextInt(3);
          }
          _history[id] = history;
          _learningTime[id] = Duration(minutes: minutes);
          members.add(StudentSummary(
            id: id,
            studentNumber: 'STD-${number.toString().padLeft(3, '0')}',
            name: '$first $last',
            email: '${first.toLowerCase()}.${last.toLowerCase()}$number@sman10gowa.sch.id',
            grade: grade,
            classId: classId,
            className: className,
            averageScore: _avg(history.map((r) => r.score)),
            completedExercises: history.length,
            active: active,
            lastActive: history.isEmpty ? null : history.first.completedAt,
          ));
        }
        _students.addAll(members);
        final classHistory = [for (final s in members) ..._history[s.id]!];
        _classes.add(SchoolClass(
          id: classId,
          name: className,
          grade: grade,
          homeroom: _homerooms[classIndex++ % _homerooms.length],
          studentCount: members.length,
          activeCount: members.where((s) => s.active).length,
          averageScore: _avg(classHistory.map((r) => r.score)),
          completedExercises: classHistory.length,
          modules: _moduleScores(classHistory),
        ));
      }
    }
  }

  static double? _avg(Iterable<double> values) {
    var sum = 0.0;
    var n = 0;
    for (final v in values) {
      sum += v;
      n++;
    }
    return n == 0 ? null : (sum / n * 10).roundToDouble() / 10;
  }

  static List<ModuleScore> _moduleScores(List<ExerciseRecord> history) => [
        for (final skill in Skill.values)
          ModuleScore(
            skill: skill,
            average: _avg(history.where((r) => r.skill == skill).map((r) => r.score)),
            submitted: history.where((r) => r.skill == skill).length,
          ),
      ];

  // --------------------------------------------------------- exercise detail

  ExerciseDetail _detail(StudentSummary student, ExerciseRecord record) {
    final score = record.score;
    final minutes = Duration(minutes: 12 + record.id.hashCode.abs() % 20);
    switch (record.skill) {
      case Skill.writing:
        return ExerciseDetail(
          record: record,
          student: student,
          score: score,
          timeSpent: minutes,
          summary: 'The student describes a daily routine clearly with good time sequencing. '
              'Most errors are verb forms and a few spelling mistakes.',
          criteria: [
            Criterion('Grammar & Mechanics', (score - 3).clamp(0, 100),
                'Mostly correct present tense; check subject-verb agreement.'),
            Criterion('Vocabulary Range', (score + 2).clamp(0, 100),
                'Good everyday vocabulary; try more precise adjectives.'),
            Criterion('Sentence Structure & Cohesion', score,
                'Clear order with time connectors such as "after" and "then".'),
          ],
          submission: 'Every morning, I wake up at 5:30 AM to prepare for school. After taking a '
              'shower, I eat breakfast with my family. I usually goes to school by bicycle because '
              'it only take fifteen minutes. In the afternoon, I join the english club and we '
              'practise speaking together. When I return home, I help my parents and do my '
              'homework. I enjoy this routine because it make me disciplined.',
          correctedText: 'Every morning, I wake up at 5:30 AM to prepare for school. After taking a '
              'shower, I eat breakfast with my family. I usually go to school by bicycle because '
              'it only takes fifteen minutes. In the afternoon, I join the English club and we '
              'practise speaking together. When I return home, I help my parents and do my '
              'homework. I enjoy this routine because it makes me disciplined.',
          corrections: const [
            TextCorrection(
                original: 'goes',
                replacement: 'go',
                title: 'Subject-verb agreement',
                explanation: 'With "I", use the base form: "I go".'),
            TextCorrection(
                original: 'take',
                replacement: 'takes',
                title: 'Subject-verb agreement',
                explanation: '"It" is singular, so the verb needs -s: "it takes".'),
            TextCorrection(
                original: 'english',
                replacement: 'English',
                title: 'Capitalization',
                explanation: 'Names of languages start with a capital letter.'),
            TextCorrection(
                original: 'make',
                replacement: 'makes',
                title: 'Subject-verb agreement',
                explanation: '"It makes me disciplined" — singular subject.'),
          ],
        );
      case Skill.reading:
        final correctCount = (score / 20).round().clamp(0, 5);
        return ExerciseDetail(
          record: record,
          student: student,
          score: score,
          timeSpent: minutes,
          summary: 'Good understanding of the main idea; details about time and place need more attention.',
          criteria: [Criterion('Reading comprehension', score, '$correctCount of 5 answers correct.')],
          passage: 'Every August, Daeng joined the kite festival near his home in Gowa. This year, he '
              'brought a blue kite that he had made with his father. Suddenly, a strong gust pulled '
              'the string from his hand and the kite landed on the rooftop of a small shop. With his '
              'father holding a ladder steady, Daeng climbed up slowly to get it back.',
          answers: _quiz(correctCount, const [
            ('Where was the festival?', 'In Gowa', 'In Makassar'),
            ('What colour was the kite?', 'Blue', 'Red'),
            ('Who held the ladder?', 'His father', 'His friends'),
            ('Where did the kite land?', 'On a rooftop', 'In a tree'),
            ('What did Daeng learn?', 'It is okay to ask for help', 'Kites are dangerous'),
          ]),
        );
      case Skill.speaking:
        return ExerciseDetail(
          record: record,
          student: student,
          score: score,
          timeSpent: minutes,
          summary: 'Answers are relevant and understandable. Use longer sentences and give examples.',
          criteria: [
            const Criterion('Fluency & coherence', null,
                'Needs an audio assessor; not judged from the transcript.'),
            Criterion('Vocabulary', score, 'Good range of everyday words.'),
            Criterion('Grammar', (score - 4).clamp(0, 100), 'Some past tense errors.'),
            const Criterion('Pronunciation', null,
                'Needs an audio assessor; not judged from the transcript.'),
          ],
          conversation: const [
            ConversationTurn(fromAi: true, text: 'Hi! What did you do last weekend?'),
            ConversationTurn(fromAi: false, text: 'I went to the beach with my family.'),
            ConversationTurn(fromAi: true, text: 'That sounds fun! Which beach did you visit?'),
            ConversationTurn(fromAi: false, text: 'We visited Bira Beach and we swim in the sea.'),
            ConversationTurn(fromAi: true, text: 'Wow, Bira Beach is beautiful! What else did you do?'),
          ],
        );
      case Skill.listening:
        final correctCount = (score / 33.4).round().clamp(0, 3);
        return ExerciseDetail(
          record: record,
          student: student,
          score: score,
          timeSpent: minutes,
          summary: 'Understands the main request; prices and numbers were harder to catch.',
          criteria: [Criterion('Listening comprehension', score, '$correctCount of 3 answers correct.')],
          audioDuration: const Duration(seconds: 44),
          transcript: const [
            'Andi: Good afternoon, Ms Mira.',
            'Mira: Hello, Andi. What would you like?',
            'Andi: I’d like a chicken sandwich, please.',
            'Mira: Of course. It costs fifteen thousand rupiah.',
            'Andi: Thank you. I’ll sit near the window.',
          ],
          answers: _quiz(correctCount, const [
            ('What does Andi want to buy?', 'A chicken sandwich', 'A bowl of noodles'),
            ('How much is the sandwich?', 'Fifteen thousand rupiah', 'Ten thousand rupiah'),
            ('Where will Andi sit?', 'Near the window', 'In his classroom'),
          ]),
        );
    }
  }

  static List<QuizAnswer> _quiz(int correctCount, List<(String, String, String)> items) => [
        for (var i = 0; i < items.length; i++)
          QuizAnswer(
            question: items[i].$1,
            correctAnswer: items[i].$2,
            chosen: i < correctCount ? items[i].$2 : items[i].$3,
            correct: i < correctCount,
            explanation: i < correctCount
                ? 'Correct: the text says "${items[i].$2}".'
                : 'The answer is "${items[i].$2}".',
          ),
      ];
}
