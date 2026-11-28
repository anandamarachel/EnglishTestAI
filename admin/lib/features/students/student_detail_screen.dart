import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:english_day_admin/core/format.dart';
import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/core/widgets/admin_table.dart';
import 'package:english_day_admin/core/widgets/common.dart';
import 'package:english_day_admin/data/models.dart';
import 'package:english_day_admin/data/providers.dart';

/// One student: information, learning overview, module performance and
/// learning history (PM plan 3.D).
class StudentDetailScreen extends ConsumerWidget {
  const StudentDetailScreen({super.key, required this.studentId});
  final String studentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(studentDetailProvider(studentId));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        BackLink(
          label: 'Back to Students',
          onTap: () => context.go('/students'),
        ),
        const SizedBox(height: 8),
        AsyncSection<StudentDetail>(
          value: detail,
          onRetry: () => ref.invalidate(studentDetailProvider(studentId)),
          loadingHeight: 420,
          builder: (d) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _InfoCard(d.summary),
              const SizedBox(height: 20),
              _Overview(d),
              const SizedBox(height: 20),
              _ModulePerformance(d.modules),
              const SizedBox(height: 20),
              _LearningHistory(student: d.summary, history: d.history),
            ],
          ),
        ),
      ],
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard(this.s);
  final StudentSummary s;

  @override
  Widget build(BuildContext context) => PanelCard(
        child: Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 16,
          runSpacing: 12,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                InitialsAvatar(s.initials, size: 56),
                const SizedBox(width: 16),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: 10,
                      children: [
                        Text(s.name, style: AdminText.headline(size: 24)),
                        Pill(s.studentNumber),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text('Grade ${s.grade}  •  Class ${s.className}  •  ${s.email}',
                        style: AdminText.small),
                  ],
                ),
              ],
            ),
            StatusPill(active: s.active),
          ],
        ),
      );
}

class _Overview extends StatelessWidget {
  const _Overview(this.d);
  final StudentDetail d;

  @override
  Widget build(BuildContext context) {
    final s = d.summary;
    return ResponsiveGrid(children: [
      StatCard(
        label: 'Average Score',
        value: formatScore(s.averageScore),
        unit: '/ 100',
        icon: Icons.emoji_events_outlined,
        caption: 'All modules',
      ),
      StatCard(
        label: 'Completed Exercises',
        value: '${s.completedExercises}',
        unit: 'exercises',
        icon: Icons.task_alt_rounded,
        caption: 'Evaluated by AI',
      ),
      StatCard(
        label: 'Learning Time',
        value: formatDuration(d.learningTime),
        icon: Icons.schedule_rounded,
        caption: s.completedExercises == 0 ? 'No practice yet' : 'Total time in exercises',
      ),
      StatCard(
        label: 'Last Active',
        value: s.lastActive == null ? 'Never' : formatRelativeDay(s.lastActive!),
        icon: Icons.bolt_rounded,
        caption: d.history.isEmpty
            ? 'No exercise yet'
            : '${formatTime(d.history.first.completedAt)} • ${d.history.first.skill.label} • '
                '${d.history.first.title}',
      ),
    ]);
  }
}

class _ModulePerformance extends StatelessWidget {
  const _ModulePerformance(this.modules);
  final List<ModuleScore> modules;

  @override
  Widget build(BuildContext context) {
    final graded = modules.where((m) => m.average != null).toList()
      ..sort((a, b) => b.average!.compareTo(a.average!));
    final best = graded.isEmpty ? null : graded.first.skill;
    // Flag only a module that is really low, not just the lowest of four good ones.
    final weakest = graded.length < 2 || graded.last.average! >= 70 ? null : graded.last.skill;
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(
            title: 'Module Performance',
            subtitle: 'Average AI score per module (0–100)',
          ),
          const SizedBox(height: 16),
          ResponsiveGrid(
            minItemWidth: 200,
            children: [
              for (final m in modules)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: AdminColors.primaryTint,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Icon(m.skill.icon, size: 18, color: m.skill.color),
                        const SizedBox(width: 8),
                        Text(m.skill.label, style: AdminText.body(weight: FontWeight.w700)),
                        const Spacer(),
                        Text.rich(TextSpan(children: [
                          TextSpan(text: formatScore(m.average), style: AdminText.headline(size: 18)),
                          TextSpan(text: '/100', style: AdminText.small),
                        ])),
                      ]),
                      const SizedBox(height: 10),
                      ThinBar(value: (m.average ?? 0) / 100, color: m.skill.color, height: 8),
                      const SizedBox(height: 8),
                      Row(children: [
                        Expanded(
                          child: Text(
                            m.skill == best
                                ? 'Strongest module'
                                : m.skill == weakest
                                    ? 'Needs attention'
                                    : m.average == null
                                        ? 'Not practiced yet'
                                        : ' ',
                            style: AdminText.small.copyWith(
                              color: m.skill == weakest ? AdminColors.warning : AdminColors.textSecondary,
                              fontWeight: m.skill == best || m.skill == weakest ? FontWeight.w600 : null,
                            ),
                          ),
                        ),
                        Text('${m.submitted} submitted', style: AdminText.small),
                      ]),
                    ],
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _LearningHistory extends StatefulWidget {
  const _LearningHistory({required this.student, required this.history});
  final StudentSummary student;
  final List<ExerciseRecord> history;

  @override
  State<_LearningHistory> createState() => _LearningHistoryState();
}

class _LearningHistoryState extends State<_LearningHistory> {
  static const _pageSize = 8;
  Skill _skill = Skill.writing;
  int _shown = _pageSize;

  @override
  Widget build(BuildContext context) {
    final items = widget.history.where((r) => r.skill == _skill).toList();
    final visible = items.take(_shown).toList();
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(
            title: 'Learning History',
            subtitle: 'Completed exercises and their AI scores',
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final skill in Skill.values)
                ChoiceChip(
                  avatar: Icon(skill.icon, size: 16,
                      color: skill == _skill ? AdminColors.primary : AdminColors.textSecondary),
                  label: Text('${skill.label}  ${widget.history.where((r) => r.skill == skill).length}'),
                  selected: skill == _skill,
                  showCheckmark: false,
                  selectedColor: AdminColors.primarySoft,
                  backgroundColor: AdminColors.surface,
                  side: const BorderSide(color: AdminColors.border),
                  labelStyle: AdminText.body(
                      size: 13,
                      weight: FontWeight.w600,
                      color: skill == _skill ? AdminColors.primary : AdminColors.textSecondary),
                  onSelected: (_) => setState(() {
                    _skill = skill;
                    _shown = _pageSize;
                  }),
                ),
            ],
          ),
          const SizedBox(height: 16),
          AdminTable(
            columns: const [
              AdminColumn('Exercise Title', flex: 3),
              AdminColumn('Topic', flex: 3),
              AdminColumn('Completed', flex: 3),
              AdminColumn('Score', flex: 1),
              AdminColumn('Action', flex: 2, alignEnd: true),
            ],
            emptyText: 'No ${_skill.label} exercises yet.',
            onRowTap: (i) => _open(context, visible[i]),
            rows: [
              for (final r in visible)
                [
                  Text(r.title, style: AdminText.body(size: 13.5, weight: FontWeight.w600)),
                  Text(r.topic, style: AdminText.small),
                  Text(formatDateTime(r.completedAt), style: AdminText.small),
                  ScoreChip(r.score),
                  ViewDetailsLink(onTap: () => _open(context, r)),
                ],
            ],
          ),
          if (items.isNotEmpty) ...[
            const SizedBox(height: 12),
            Row(children: [
              Text('Showing ${visible.length} of ${items.length} ${_skill.label} exercises',
                  style: AdminText.small),
              const Spacer(),
              if (visible.length < items.length)
                TextButton(
                  onPressed: () => setState(() => _shown += _pageSize),
                  child: Text('Load ${(items.length - visible.length).clamp(0, _pageSize)} more'),
                ),
            ]),
          ],
        ],
      ),
    );
  }

  // `go`, not `push`: a page left mounted under another breaks its LayoutBuilders
  // when it is covered. Browser back still works (every page has its own URL).
  void _open(BuildContext context, ExerciseRecord r) =>
      context.go('/students/${widget.student.id}/exercises/${r.id}');
}
