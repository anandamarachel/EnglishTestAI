import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:english_day_admin/core/format.dart';
import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/core/widgets/admin_table.dart';
import 'package:english_day_admin/core/widgets/common.dart';
import 'package:english_day_admin/data/models.dart';
import 'package:english_day_admin/data/providers.dart';

/// One class: summary, module averages and its students ("View Class").
class ClassDetailScreen extends ConsumerStatefulWidget {
  const ClassDetailScreen({super.key, required this.classId});
  final String classId;

  @override
  ConsumerState<ClassDetailScreen> createState() => _ClassDetailScreenState();
}

class _ClassDetailScreenState extends ConsumerState<ClassDetailScreen> {
  String _query = '';
  int _page = 1;

  StudentQuery get _key => (query: _query, grade: null, classId: widget.classId, page: _page);

  @override
  Widget build(BuildContext context) {
    final schoolClass = ref.watch(classProvider(widget.classId));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        BackLink(label: 'Back to Classes', onTap: () => context.go('/students?tab=classes')),
        const SizedBox(height: 8),
        AsyncSection<SchoolClass>(
          value: schoolClass,
          onRetry: () => ref.invalidate(classProvider(widget.classId)),
          builder: (c) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              PageHeader(
                title: 'Class ${c.name}',
                subtitle: 'Homeroom teacher: ${c.homeroom}',
                trailing: Wrap(spacing: 8, children: [
                  Pill('Grade ${c.grade}', icon: Icons.school_outlined),
                  Pill('${c.studentCount} students', icon: Icons.groups_outlined),
                ]),
              ),
              const SizedBox(height: 20),
              ResponsiveGrid(children: [
                StatCard(
                  label: 'Total Students',
                  value: '${c.studentCount}',
                  icon: Icons.groups_outlined,
                  caption: 'Enrolled in ${c.name}',
                ),
                StatCard(
                  label: 'Active Students',
                  value: '${c.activeCount}',
                  icon: Icons.bolt_rounded,
                  caption: '${formatPercent(c.activeCount / c.studentCount)} practiced this week',
                  progress: c.activeCount / c.studentCount,
                ),
                StatCard(
                  label: 'Average Score',
                  value: formatScore(c.averageScore),
                  unit: '/ 100',
                  icon: Icons.insights_rounded,
                  caption: 'All modules',
                ),
                StatCard(
                  label: 'Completed Exercises',
                  value: '${c.completedExercises}',
                  icon: Icons.task_alt_rounded,
                  caption: 'Avg. ${(c.completedExercises / c.studentCount).round()} per student',
                ),
              ]),
              const SizedBox(height: 20),
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionHeader(
                      title: 'Module Performance',
                      subtitle: 'Average AI score of this class per module',
                    ),
                    const SizedBox(height: 18),
                    ResponsiveGrid(
                      minItemWidth: 320,
                      maxColumns: 2,
                      spacing: 20,
                      children: [for (final m in c.modules) ModuleBar(m)],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SectionHeader(
                title: 'Student Directory',
                subtitle: 'Open a student to see their learning progress',
                trailing: SizedBox(
                  width: 280,
                  child: SearchField(
                    hint: 'Search name or ID…',
                    onChanged: (v) => setState(() {
                      _query = v;
                      _page = 1;
                    }),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              AsyncSection<PageResult<StudentSummary>>(
                value: ref.watch(studentsProvider(_key)),
                onRetry: () => ref.invalidate(studentsProvider(_key)),
                builder: (result) => Column(
                  children: [
                    AdminTable(
                      columns: const [
                        AdminColumn('Student Name', flex: 4),
                        AdminColumn('Student ID', flex: 2),
                        AdminColumn('Average Score', flex: 2),
                        AdminColumn('Completed', flex: 2),
                        AdminColumn('Last Active', flex: 2),
                        AdminColumn('Action', flex: 2, alignEnd: true),
                      ],
                      emptyText: 'No students found in this class.',
                      onRowTap: (i) => context.go('/students/${result.items[i].id}'),
                      rows: [
                        for (final s in result.items)
                          [
                            StudentNameCell(student: s),
                            Text(s.studentNumber,
                                style: AdminText.body(size: 13, color: AdminColors.textSecondary)),
                            ScoreChip(s.averageScore),
                            Text('${s.completedExercises} ${s.completedExercises == 1 ? 'exercise' : 'exercises'}',
                                style: AdminText.body(size: 13)),
                            Text(s.lastActive == null ? 'Never' : formatRelative(s.lastActive!),
                                style: AdminText.small),
                            ViewDetailsLink(onTap: () => context.go('/students/${s.id}')),
                          ],
                      ],
                    ),
                    const SizedBox(height: 14),
                    PaginationBar(
                      page: result.page,
                      pageCount: result.pageCount,
                      summary: result.total == 0
                          ? 'No students'
                          : 'Showing ${result.firstIndex}–${result.lastIndex} of ${result.total} students',
                      onPage: (p) => setState(() => _page = p),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// "Writing  86 / 100" with a bar.
class ModuleBar extends StatelessWidget {
  const ModuleBar(this.module, {super.key});
  final ModuleScore module;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(module.skill.icon, size: 18, color: module.skill.color),
            const SizedBox(width: 8),
            Text(module.skill.label, style: AdminText.body(weight: FontWeight.w700)),
            const Spacer(),
            Text.rich(TextSpan(children: [
              TextSpan(text: formatScore(module.average), style: AdminText.headline(size: 16)),
              TextSpan(text: ' / 100', style: AdminText.small),
            ])),
          ]),
          const SizedBox(height: 8),
          ThinBar(value: (module.average ?? 0) / 100, color: module.skill.color, height: 8),
        ],
      );
}
