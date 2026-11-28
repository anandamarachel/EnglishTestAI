import 'package:flutter/material.dart';

import 'package:english_day_admin/core/theme/admin_theme.dart';

/// The four practice modules of the English Day app.
enum Skill {
  writing('Writing', Icons.edit_note_rounded, AdminColors.writing),
  reading('Reading', Icons.menu_book_rounded, AdminColors.reading),
  speaking('Speaking', Icons.mic_none_rounded, AdminColors.speaking),
  listening('Listening', Icons.headphones_rounded, AdminColors.listening);

  const Skill(this.label, this.icon, this.color);
  final String label;
  final IconData icon;
  final Color color;
}

class AdminUser {
  const AdminUser({required this.name, required this.email, required this.role});
  final String name;
  final String email;
  final String role;

  String get initials => initialsOf(name);
}

/// "Andi Pratama" -> "AP".
String initialsOf(String name) {
  final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) return '?';
  final first = parts.first.characters.first;
  final last = parts.length > 1 ? parts.last.characters.first : '';
  return (first + last).toUpperCase();
}

/// One page of a long list (students are paginated, about 500 in a school).
class PageResult<T> {
  const PageResult({required this.items, required this.page, required this.pageSize, required this.total});
  final List<T> items;
  final int page; // 1-based
  final int pageSize;
  final int total;

  int get pageCount => total == 0 ? 1 : (total / pageSize).ceil();
  int get firstIndex => total == 0 ? 0 : (page - 1) * pageSize + 1;
  int get lastIndex => firstIndex == 0 ? 0 : firstIndex + items.length - 1;
}

class StudentSummary {
  const StudentSummary({
    required this.id,
    required this.studentNumber,
    required this.name,
    required this.email,
    required this.grade,
    required this.classId,
    required this.className,
    required this.averageScore,
    required this.completedExercises,
    required this.active,
    required this.lastActive,
  });

  final String id;

  /// School student ID shown in the tables (e.g. STD-001).
  final String studentNumber;
  final String name;
  final String email;
  final int grade;
  final String classId;
  final String className;

  /// 0–100, null when the student has no graded exercise yet.
  final double? averageScore;
  final int completedExercises;
  final bool active;
  final DateTime? lastActive;

  String get initials => initialsOf(name);
}

class ModuleScore {
  const ModuleScore({required this.skill, required this.average, required this.submitted});
  final Skill skill;
  final double? average; // 0–100
  final int submitted;
}

class SchoolClass {
  const SchoolClass({
    required this.id,
    required this.name,
    required this.grade,
    required this.homeroom,
    required this.studentCount,
    required this.activeCount,
    required this.averageScore,
    required this.completedExercises,
    required this.modules,
  });

  final String id;
  final String name; // X-A
  final int grade;
  final String homeroom;
  final int studentCount;
  final int activeCount;
  final double? averageScore;
  final int completedExercises;
  final List<ModuleScore> modules;
}

class ExerciseRecord {
  const ExerciseRecord({
    required this.id,
    required this.skill,
    required this.title,
    required this.topic,
    required this.completedAt,
    required this.score,
  });

  final String id;
  final Skill skill;
  final String title;
  final String topic;
  final DateTime completedAt;
  final double score; // 0–100
}

class StudentDetail {
  const StudentDetail({
    required this.summary,
    required this.learningTime,
    required this.modules,
    required this.history,
  });

  final StudentSummary summary;
  final Duration learningTime;
  final List<ModuleScore> modules;

  /// Completed exercises, newest first.
  final List<ExerciseRecord> history;
}

/// One rubric line of an AI evaluation. Null score = not assessed.
class Criterion {
  const Criterion(this.label, this.score, this.feedback);
  final String label;
  final double? score; // 0–100
  final String feedback;
}

/// A grammar/vocabulary correction on the student's original text.
class TextCorrection {
  const TextCorrection({
    required this.original,
    required this.replacement,
    required this.title,
    required this.explanation,
  });
  final String original;
  final String replacement;
  final String title;
  final String explanation;
}

class QuizAnswer {
  const QuizAnswer({
    required this.question,
    required this.chosen,
    required this.correctAnswer,
    required this.correct,
    required this.explanation,
  });
  final String question;
  final String chosen;
  final String correctAnswer;
  final bool correct;
  final String explanation;
}

class ConversationTurn {
  const ConversationTurn({required this.fromAi, required this.text});
  final bool fromAi;
  final String text;
}

/// Everything shown on the exercise detail view. Which parts are filled depends
/// on the module (see the PM plan, section 3.E).
class ExerciseDetail {
  const ExerciseDetail({
    required this.record,
    required this.student,
    required this.score,
    required this.summary,
    required this.criteria,
    required this.timeSpent,
    this.submission,
    this.correctedText,
    this.corrections = const [],
    this.passage,
    this.answers = const [],
    this.conversation = const [],
    this.transcript = const [],
    this.audioDuration,
  });

  final ExerciseRecord record;
  final StudentSummary student;
  final double score;
  final String summary;
  final List<Criterion> criteria;
  final Duration timeSpent;

  // Writing
  final String? submission;
  final String? correctedText;
  final List<TextCorrection> corrections;

  // Reading (passage) and Reading/Listening (answers)
  final String? passage;
  final List<QuizAnswer> answers;

  // Speaking
  final List<ConversationTurn> conversation;

  // Listening
  final List<String> transcript;
  final Duration? audioDuration;

  int get wordCount =>
      (submission ?? '').trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
}

class ModuleActivity {
  const ModuleActivity({required this.skill, required this.submissions, required this.average});
  final Skill skill;
  final int submissions;
  final double average;
}

class GradePerformance {
  const GradePerformance({
    required this.grade,
    required this.average,
    required this.students,
    required this.classes,
  });
  final int grade;
  final double average;
  final int students;
  final int classes;
}

class RecentActivity {
  const RecentActivity({required this.student, required this.record});
  final StudentSummary student;
  final ExerciseRecord record;
}

class DashboardSummary {
  const DashboardSummary({
    required this.totalStudents,
    required this.activeStudents,
    required this.totalClasses,
    required this.averageScore,
    required this.modules,
    required this.grades,
    required this.recent,
  });

  final int totalStudents;
  final int activeStudents;
  final int totalClasses;
  final double averageScore;
  final List<ModuleActivity> modules;
  final List<GradePerformance> grades;
  final List<RecentActivity> recent;

  int get totalSubmissions => modules.fold(0, (sum, m) => sum + m.submissions);
}
