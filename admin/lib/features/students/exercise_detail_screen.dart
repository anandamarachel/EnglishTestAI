import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:english_day_admin/core/format.dart';
import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/core/widgets/common.dart';
import 'package:english_day_admin/data/models.dart';
import 'package:english_day_admin/data/providers.dart';

/// One completed exercise and its AI evaluation (PM plan 3.E). What is shown
/// depends on the module: writing text + corrections, reading/listening answers,
/// speaking conversation.
class ExerciseDetailScreen extends ConsumerWidget {
  const ExerciseDetailScreen({super.key, required this.studentId, required this.exerciseId});
  final String studentId;
  final String exerciseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(exerciseDetailProvider((studentId, exerciseId)));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        BackLink(
          label: 'Back to student',
          onTap: () => context.go('/students/$studentId'),
        ),
        const SizedBox(height: 8),
        AsyncSection<ExerciseDetail>(
          value: detail,
          onRetry: () => ref.invalidate(exerciseDetailProvider((studentId, exerciseId))),
          loadingHeight: 420,
          builder: (d) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Header(d),
              const SizedBox(height: 20),
              _Facts(d),
              const SizedBox(height: 20),
              LayoutBuilder(builder: (context, c) {
                final content = _Content(d);
                final evaluation = _Evaluation(d);
                if (c.maxWidth < 980) {
                  return Column(children: [content, const SizedBox(height: 20), evaluation]);
                }
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 3, child: content),
                    const SizedBox(width: 20),
                    Expanded(flex: 2, child: evaluation),
                  ],
                );
              }),
            ],
          ),
        ),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header(this.d);
  final ExerciseDetail d;

  @override
  Widget build(BuildContext context) => PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 10,
              runSpacing: 8,
              children: [
                Text(d.record.title, style: AdminText.headline(size: 24)),
                SkillBadge(d.record.skill),
                Pill('Grade ${d.student.grade}', color: AdminColors.textSecondary,
                    background: AdminColors.divider),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 18,
              runSpacing: 6,
              children: [
                _Meta(Icons.person_outline_rounded,
                    '${d.student.name} (${d.student.studentNumber})',
                    onTap: () => context.go('/students/${d.student.id}')),
                _Meta(Icons.class_outlined, 'Class ${d.student.className}'),
                _Meta(Icons.event_rounded, 'Submitted ${formatDateTime(d.record.completedAt)}'),
              ],
            ),
          ],
        ),
      );
}

class _Meta extends StatelessWidget {
  const _Meta(this.icon, this.text, {this.onTap});
  final IconData icon;
  final String text;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 16, color: AdminColors.textSecondary),
          const SizedBox(width: 6),
          Text(text,
              style: AdminText.small.copyWith(
                  color: onTap == null ? AdminColors.textSecondary : AdminColors.primary,
                  fontWeight: onTap == null ? null : FontWeight.w600)),
        ]),
      );
}

class _Facts extends StatelessWidget {
  const _Facts(this.d);
  final ExerciseDetail d;

  @override
  Widget build(BuildContext context) {
    final correct = d.answers.where((a) => a.correct).length;
    return ResponsiveGrid(
      minItemWidth: 180,
      maxColumns: 4,
      children: [
        StatCard(label: 'Module', value: d.record.skill.label, icon: d.record.skill.icon,
            caption: 'Topic: ${d.record.topic}'),
        StatCard(label: 'Time Spent', value: formatDuration(d.timeSpent), icon: Icons.schedule_rounded,
            caption: 'In this exercise'),
        switch (d.record.skill) {
          Skill.writing => StatCard(label: 'Word Count', value: '${d.wordCount}', unit: 'words',
              icon: Icons.notes_rounded, caption: '${d.corrections.length} corrections by AI'),
          Skill.speaking => StatCard(label: 'Turns', value: '${d.conversation.where((t) => !t.fromAi).length}',
              unit: 'answers', icon: Icons.forum_outlined, caption: 'Spoken by the student'),
          _ => StatCard(label: 'Correct Answers', value: '$correct', unit: '/ ${d.answers.length}',
              icon: Icons.fact_check_outlined, caption: 'Graded by the server'),
        },
        StatCard(label: 'AI Score', value: formatScore(d.score), unit: '/ 100',
            icon: Icons.auto_awesome_rounded, caption: d.score >= 85 ? 'Very good' : d.score >= 70 ? 'Good' : 'Needs practice',
            progress: d.score / 100),
      ],
    );
  }
}

// ---------------------------------------------------------------- content

class _Content extends StatelessWidget {
  const _Content(this.d);
  final ExerciseDetail d;

  @override
  Widget build(BuildContext context) => switch (d.record.skill) {
        Skill.writing => _WritingContent(d),
        Skill.reading => Column(children: [
            PanelCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionHeader(title: 'Reading Text', subtitle: 'Story generated by AI'),
                  const SizedBox(height: 14),
                  Text(d.passage ?? '', style: AdminText.body(size: 15, height: 1.7)),
                ],
              ),
            ),
            const SizedBox(height: 20),
            _Answers(d.answers),
          ]),
        Skill.speaking => _Conversation(d.conversation),
        Skill.listening => Column(children: [
            PanelCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SectionHeader(
                    title: 'Audio Transcript',
                    subtitle: 'Conversation audio • ${formatClock(d.audioDuration ?? Duration.zero)}',
                    trailing: const Pill('Unlocked after submit', icon: Icons.lock_open_rounded),
                  ),
                  const SizedBox(height: 14),
                  for (final line in d.transcript)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(line, style: AdminText.body(size: 15, height: 1.6)),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            _Answers(d.answers),
          ]),
      };
}

class _WritingContent extends StatelessWidget {
  const _WritingContent(this.d);
  final ExerciseDetail d;

  /// The submission with each corrected word struck through and its fix after it.
  List<InlineSpan> _spans(TextStyle base) {
    final text = d.submission ?? '';
    final spans = <InlineSpan>[];
    var cursor = 0;
    for (final c in d.corrections) {
      final match = RegExp('\\b${RegExp.escape(c.original)}\\b').firstMatch(text.substring(cursor));
      if (match == null) continue;
      final start = cursor + match.start;
      final end = cursor + match.end;
      spans.add(TextSpan(text: text.substring(cursor, start)));
      spans.add(TextSpan(
        text: c.original,
        style: base.copyWith(
          decoration: TextDecoration.lineThrough,
          decorationColor: AdminColors.danger,
          decorationThickness: 2,
          color: AdminColors.danger,
        ),
      ));
      spans.add(TextSpan(
        text: ' ${c.replacement}',
        style: base.copyWith(
          color: AdminColors.success,
          fontWeight: FontWeight.w700,
          backgroundColor: AdminColors.successSoft,
        ),
      ));
      cursor = end;
    }
    spans.add(TextSpan(text: text.substring(cursor)));
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    final base = AdminText.body(size: 15, height: 1.75);
    return Column(children: [
      PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SectionHeader(
              title: 'Student Submission',
              subtitle: 'Original text with AI corrections',
              trailing: Pill('${d.corrections.length} corrections', color: AdminColors.danger,
                  background: AdminColors.dangerSoft),
            ),
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: AdminColors.primaryTint,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text.rich(TextSpan(style: base, children: _spans(base))),
            ),
            const SizedBox(height: 18),
            Text('Corrected version', style: AdminText.body(weight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text(d.correctedText ?? '', style: base.copyWith(color: AdminColors.primary)),
          ],
        ),
      ),
      const SizedBox(height: 20),
      PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionHeader(title: 'Corrections', subtitle: 'Grammar and vocabulary feedback'),
            const SizedBox(height: 12),
            for (final c in d.corrections)
              Container(
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  border: Border.all(color: AdminColors.border),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Text(c.original,
                          style: AdminText.body(
                              weight: FontWeight.w600,
                              color: AdminColors.danger,
                              ).copyWith(decoration: TextDecoration.lineThrough)),
                      const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 8),
                        child: Icon(Icons.arrow_forward_rounded, size: 16, color: AdminColors.textMuted),
                      ),
                      Text(c.replacement,
                          style: AdminText.body(weight: FontWeight.w700, color: AdminColors.success)),
                      const Spacer(),
                      Pill(c.title),
                    ]),
                    const SizedBox(height: 6),
                    Text(c.explanation, style: AdminText.small),
                  ],
                ),
              ),
          ],
        ),
      ),
    ]);
  }
}

class _Answers extends StatelessWidget {
  const _Answers(this.answers);
  final List<QuizAnswer> answers;

  @override
  Widget build(BuildContext context) => PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SectionHeader(
              title: 'Quiz Answers',
              subtitle: '${answers.where((a) => a.correct).length} of ${answers.length} correct',
            ),
            const SizedBox(height: 12),
            for (var i = 0; i < answers.length; i++)
              Container(
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: answers[i].correct ? AdminColors.successSoft : AdminColors.dangerSoft,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(answers[i].correct ? Icons.check_circle_rounded : Icons.cancel_rounded,
                        color: answers[i].correct ? AdminColors.success : AdminColors.danger, size: 20),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${i + 1}. ${answers[i].question}',
                              style: AdminText.body(weight: FontWeight.w700)),
                          const SizedBox(height: 4),
                          Text('Answer: ${answers[i].chosen}', style: AdminText.body(size: 13.5)),
                          if (!answers[i].correct)
                            Text('Correct answer: ${answers[i].correctAnswer}',
                                style: AdminText.body(size: 13.5, weight: FontWeight.w600,
                                    color: AdminColors.success)),
                          const SizedBox(height: 4),
                          Text(answers[i].explanation, style: AdminText.small),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      );
}

class _Conversation extends StatelessWidget {
  const _Conversation(this.turns);
  final List<ConversationTurn> turns;

  @override
  Widget build(BuildContext context) => PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionHeader(
              title: 'Conversation Transcript',
              subtitle: 'The student’s speech was transcribed by AI',
            ),
            const SizedBox(height: 14),
            for (final t in turns)
              Align(
                alignment: t.fromAi ? Alignment.centerLeft : Alignment.centerRight,
                child: Container(
                  constraints: const BoxConstraints(maxWidth: 460),
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: t.fromAi ? AdminColors.surface : AdminColors.primarySoft,
                    border: Border.all(color: t.fromAi ? AdminColors.border : AdminColors.primarySoft),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t.fromAi ? 'AI partner' : 'Student',
                          style: AdminText.caps.copyWith(
                              color: t.fromAi ? AdminColors.textSecondary : AdminColors.primary)),
                      const SizedBox(height: 4),
                      Text(t.text, style: AdminText.body(size: 14.5, height: 1.5)),
                    ],
                  ),
                ),
              ),
          ],
        ),
      );
}

// ------------------------------------------------------------- evaluation

class _Evaluation extends StatelessWidget {
  const _Evaluation(this.d);
  final ExerciseDetail d;

  @override
  Widget build(BuildContext context) => PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: AdminColors.primary,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.auto_awesome_rounded, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('AI Evaluation', style: AdminText.sectionTitle),
                    Text('Automatic, no manual grading needed', style: AdminText.small),
                  ],
                ),
              ),
              Text.rich(TextSpan(children: [
                TextSpan(text: formatScore(d.score), style: AdminText.headline(size: 26)),
                TextSpan(text: ' / 100', style: AdminText.small),
              ])),
            ]),
            const SizedBox(height: 18),
            Text('CATEGORY BREAKDOWN', style: AdminText.caps),
            const SizedBox(height: 10),
            for (final c in d.criteria) ...[
              Row(children: [
                Expanded(child: Text(c.label, style: AdminText.body(size: 13.5, weight: FontWeight.w600))),
                c.score == null
                    ? Text('Not assessed', style: AdminText.small)
                    : Text('${formatScore(c.score)} / 100',
                        style: AdminText.body(size: 13, weight: FontWeight.w700, color: AdminColors.primary)),
              ]),
              const SizedBox(height: 6),
              ThinBar(value: (c.score ?? 0) / 100, height: 6),
              const SizedBox(height: 4),
              Text(c.feedback, style: AdminText.small),
              const SizedBox(height: 14),
            ],
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AdminColors.primaryTint,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('AI FEEDBACK SUMMARY', style: AdminText.caps.copyWith(color: AdminColors.primary)),
                  const SizedBox(height: 6),
                  Text(d.summary, style: AdminText.body(size: 14, height: 1.55)),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Text('Practice score for learning, not an official IELTS score.', style: AdminText.small),
          ],
        ),
      );
}
