import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:english_day_admin/core/app_info.dart';
import 'package:english_day_admin/core/format.dart';
import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/core/widgets/admin_table.dart';
import 'package:english_day_admin/core/widgets/common.dart';
import 'package:english_day_admin/data/models.dart';
import 'package:english_day_admin/data/providers.dart';

/// School-wide overview (PM plan 3.B).
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(dashboardProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const PageHeader(
          title: 'Dashboard',
          subtitle: 'Overview of English learning activity at ${AppInfo.school}.',
          trailing: Pill('Academic Year ${AppInfo.academicYear}  •  ${AppInfo.term}',
              icon: Icons.calendar_today_rounded),
        ),
        const SizedBox(height: 24),
        AsyncSection<DashboardSummary>(
          value: summary,
          onRetry: () => ref.invalidate(dashboardProvider),
          loadingHeight: 400,
          builder: (data) => Column(
            children: [
              _Stats(data),
              const SizedBox(height: 20),
              LayoutBuilder(builder: (context, c) {
                final activity = _LearningActivity(data);
                final performance = _GradePerformanceCard(data.grades);
                if (c.maxWidth < 900) {
                  return Column(children: [activity, const SizedBox(height: 20), performance]);
                }
                // No IntrinsicHeight here: it cannot measure the LayoutBuilder in the chart.
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 3, child: activity),
                    const SizedBox(width: 20),
                    Expanded(flex: 2, child: performance),
                  ],
                );
              }),
              const SizedBox(height: 20),
              _RecentActivity(data.recent),
            ],
          ),
        ),
      ],
    );
  }
}

class _Stats extends StatelessWidget {
  const _Stats(this.data);
  final DashboardSummary data;

  @override
  Widget build(BuildContext context) {
    final activeRate = data.totalStudents == 0 ? 0.0 : data.activeStudents / data.totalStudents;
    return ResponsiveGrid(children: [
      StatCard(
        label: 'Total Students',
        value: '${data.totalStudents}',
        icon: Icons.groups_outlined,
        caption: 'Registered students, Grade 10–12',
      ),
      StatCard(
        label: 'Active Students',
        value: '${data.activeStudents}',
        icon: Icons.bolt_rounded,
        badge: '${formatPercent(activeRate)} active',
        caption: 'Practiced in the last 7 days',
        progress: activeRate,
      ),
      StatCard(
        label: 'Total Classes',
        value: '${data.totalClasses}',
        icon: Icons.class_outlined,
        caption: '${data.totalClasses ~/ 3} classes per grade',
      ),
      StatCard(
        label: 'Average Score',
        value: formatScore(data.averageScore),
        unit: '/ 100',
        icon: Icons.insights_rounded,
        caption: 'Across all 4 modules',
        progress: data.averageScore / 100,
      ),
    ]);
  }
}

class _LearningActivity extends StatelessWidget {
  const _LearningActivity(this.data);
  final DashboardSummary data;

  @override
  Widget build(BuildContext context) {
    final total = data.totalSubmissions;
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            title: 'Learning Activity by Module',
            subtitle: 'Submissions and average AI score per module',
            trailing: Pill('$total total submissions'),
          ),
          const SizedBox(height: 18),
          // Share of submissions per module in one segmented bar.
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Row(children: [
              for (final m in data.modules)
                if (m.submissions > 0)
                  Expanded(
                    flex: m.submissions,
                    child: Container(height: 10, color: m.skill.color),
                  ),
            ]),
          ),
          const SizedBox(height: 18),
          for (final m in data.modules) ...[
            _ModuleRow(module: m, share: total == 0 ? 0 : m.submissions / total),
            const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}

class _ModuleRow extends StatelessWidget {
  const _ModuleRow({required this.module, required this.share});
  final ModuleActivity module;
  final double share;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        decoration: BoxDecoration(
          color: AdminColors.primaryTint,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: module.skill.color,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(module.skill.icon, size: 18, color: Colors.white),
                ),
                const SizedBox(width: 12),
                Text(module.skill.label, style: AdminText.body(weight: FontWeight.w700)),
                const SizedBox(width: 8),
                Flexible(
                  child: Text('${module.submissions} submissions',
                      style: AdminText.small, overflow: TextOverflow.ellipsis),
                ),
                const Spacer(),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(formatPercent(share), style: AdminText.headline(size: 18)),
                    Text('Avg. score ${formatScore(module.average)}', style: AdminText.small),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 10),
            ThinBar(value: share, color: module.skill.color),
          ],
        ),
      );
}

class _GradePerformanceCard extends StatelessWidget {
  const _GradePerformanceCard(this.grades);
  final List<GradePerformance> grades;

  @override
  Widget build(BuildContext context) => PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionHeader(
              title: 'Student Performance',
              subtitle: 'Average score by grade level',
            ),
            const SizedBox(height: 20),
            Container(
              height: 260,
              padding: const EdgeInsets.fromLTRB(12, 16, 12, 12),
              decoration: BoxDecoration(
                color: AdminColors.primaryTint,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  for (var i = 0; i < grades.length; i++)
                    Expanded(child: _GradeBar(grades[i], shade: i)),
                ],
              ),
            ),
          ],
        ),
      );
}

class _GradeBar extends StatelessWidget {
  const _GradeBar(this.grade, {required this.shade});
  final GradePerformance grade;
  final int shade;

  static const _colors = [AdminColors.secondary, AdminColors.tertiary, AdminColors.primary];

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        // Bars use the 0–100 scale; leave room for the labels above and below.
        final maxBar = (c.maxHeight - 96).clamp(40.0, 400.0);
        return Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text(formatScore(grade.average), style: AdminText.headline(size: 15)),
            const SizedBox(height: 6),
            Container(
              width: 44,
              height: maxBar * grade.average / 100,
              decoration: BoxDecoration(
                color: _colors[shade % _colors.length],
                borderRadius: const BorderRadius.vertical(top: Radius.circular(8)),
              ),
            ),
            const SizedBox(height: 8),
            Text('Grade ${grade.grade}', style: AdminText.body(size: 13, weight: FontWeight.w700)),
            Text('${grade.students} students', style: AdminText.small),
            Text('${grade.classes} classes', style: AdminText.small),
          ],
        );
      });
}

class _RecentActivity extends StatelessWidget {
  const _RecentActivity(this.recent);
  final List<RecentActivity> recent;

  @override
  Widget build(BuildContext context) => PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionHeader(
              title: 'Recent Activity',
              subtitle: 'Latest exercises completed and evaluated by AI',
            ),
            const SizedBox(height: 16),
            AdminTable(
              columns: const [
                AdminColumn('Student', flex: 3),
                AdminColumn('Module', flex: 2),
                AdminColumn('Exercise', flex: 3),
                AdminColumn('Date & Time', flex: 3),
                AdminColumn('Score', flex: 1),
                AdminColumn('Action', flex: 2, alignEnd: true),
              ],
              onRowTap: (i) => _open(context, recent[i]),
              rows: [
                for (final a in recent)
                  [
                    StudentNameCell(student: a.student, showClass: true),
                    SkillBadge(a.record.skill),
                    Text(a.record.title, style: AdminText.body(size: 13.5, weight: FontWeight.w600)),
                    Text(formatDateTime(a.record.completedAt), style: AdminText.small),
                    ScoreChip(a.record.score),
                    ViewDetailsLink(onTap: () => _open(context, a)),
                  ],
              ],
            ),
          ],
        ),
      );

  void _open(BuildContext context, RecentActivity a) =>
      context.go('/students/${a.student.id}/exercises/${a.record.id}');
}
