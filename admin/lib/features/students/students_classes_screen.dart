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

/// Directory of all students and classes, in two tabs (PM plan 3.C). The open
/// tab is part of the URL (`?tab=classes`) so the browser back button keeps it.
class StudentsClassesScreen extends StatelessWidget {
  const StudentsClassesScreen({super.key, this.showClasses = false});
  final bool showClasses;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PageHeader(
            eyebrow: 'Academic directory',
            title: 'Students & Classes',
            subtitle: 'Find any student or class at ${AppInfo.school}.',
          ),
          const SizedBox(height: 20),
          _Tabs(
            showClasses: showClasses,
            onChanged: (classes) => context.go(classes ? '/students?tab=classes' : '/students'),
          ),
          const SizedBox(height: 16),
          showClasses ? const _ClassesTab() : const _StudentsTab(),
        ],
      );
}

class _Tabs extends StatelessWidget {
  const _Tabs({required this.showClasses, required this.onChanged});
  final bool showClasses;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: AdminColors.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AdminColors.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _TabButton(
              icon: Icons.person_outline_rounded,
              label: 'Students',
              selected: !showClasses,
              onTap: () => onChanged(false),
            ),
            _TabButton(
              icon: Icons.class_outlined,
              label: 'Classes',
              selected: showClasses,
              onTap: () => onChanged(true),
            ),
          ],
        ),
      );
}

class _TabButton extends StatelessWidget {
  const _TabButton({required this.icon, required this.label, required this.selected, required this.onTap});
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: selected ? AdminColors.primarySoft : Colors.transparent,
        borderRadius: BorderRadius.circular(9),
        child: InkWell(
          borderRadius: BorderRadius.circular(9),
          onTap: selected ? null : onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
            child: Row(children: [
              Icon(icon, size: 18, color: selected ? AdminColors.primary : AdminColors.textSecondary),
              const SizedBox(width: 8),
              Text(label,
                  style: AdminText.body(
                      size: 13.5,
                      weight: FontWeight.w600,
                      color: selected ? AdminColors.primary : AdminColors.textSecondary)),
            ]),
          ),
        ),
      );
}

// ---------------------------------------------------------------- Students

class _StudentsTab extends ConsumerStatefulWidget {
  const _StudentsTab();

  @override
  ConsumerState<_StudentsTab> createState() => _StudentsTabState();
}

class _StudentsTabState extends ConsumerState<_StudentsTab> {
  String _query = '';
  int? _grade;
  int _page = 1;

  StudentQuery get _key => (query: _query, grade: _grade, classId: null, page: _page);

  @override
  Widget build(BuildContext context) {
    final page = ref.watch(studentsProvider(_key));
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              SizedBox(
                width: 340,
                child: SearchField(
                  hint: 'Search by student name or ID…',
                  onChanged: (v) => setState(() {
                    _query = v;
                    _page = 1;
                  }),
                ),
              ),
              GradeFilter(
                grade: _grade,
                onChanged: (g) => setState(() {
                  _grade = g;
                  _page = 1;
                }),
              ),
            ],
          ),
          const SizedBox(height: 16),
          AsyncSection<PageResult<StudentSummary>>(
            value: page,
            onRetry: () => ref.invalidate(studentsProvider(_key)),
            builder: (result) => Column(
              children: [
                StudentTable(students: result.items),
                const SizedBox(height: 14),
                PaginationBar(
                  page: result.page,
                  pageCount: result.pageCount,
                  summary: result.total == 0
                      ? 'No students match the filters'
                      : 'Showing ${result.firstIndex}–${result.lastIndex} of ${result.total} students',
                  onPage: (p) => setState(() => _page = p),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Student Name, Student ID, Grade, Class, Average Score, Action (PM plan 3.C.1).
class StudentTable extends StatelessWidget {
  const StudentTable({super.key, required this.students});
  final List<StudentSummary> students;

  @override
  Widget build(BuildContext context) => AdminTable(
        columns: const [
          AdminColumn('Student Name', flex: 4),
          AdminColumn('Student ID', flex: 2),
          AdminColumn('Grade', flex: 1),
          AdminColumn('Class', flex: 1),
          AdminColumn('Average Score', flex: 2),
          AdminColumn('Action', flex: 2, alignEnd: true),
        ],
        emptyText: 'No students found. Try another name, ID or grade.',
        onRowTap: (i) => context.go('/students/${students[i].id}'),
        rows: [
          for (final s in students)
            [
              StudentNameCell(student: s),
              Text(s.studentNumber, style: AdminText.body(size: 13, color: AdminColors.textSecondary)),
              Text('${s.grade}', style: AdminText.body(size: 13.5)),
              Pill(s.className),
              ScoreChip(s.averageScore),
              ViewDetailsLink(onTap: () => context.go('/students/${s.id}')),
            ],
        ],
      );
}

// ----------------------------------------------------------------- Classes

class _ClassesTab extends ConsumerStatefulWidget {
  const _ClassesTab();

  @override
  ConsumerState<_ClassesTab> createState() => _ClassesTabState();
}

class _ClassesTabState extends ConsumerState<_ClassesTab> {
  int? _grade;

  @override
  Widget build(BuildContext context) {
    final classes = ref.watch(classesProvider(_grade));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GradeFilter(grade: _grade, onChanged: (g) => setState(() => _grade = g)),
        const SizedBox(height: 16),
        AsyncSection<List<SchoolClass>>(
          value: classes,
          onRetry: () => ref.invalidate(classesProvider(_grade)),
          builder: (list) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final grade in const [10, 11, 12])
                if (list.any((c) => c.grade == grade)) ...[
                  Row(children: [
                    Text('Grade $grade', style: AdminText.sectionTitle),
                    const SizedBox(width: 8),
                    Pill('${list.where((c) => c.grade == grade).length} classes'),
                  ]),
                  const SizedBox(height: 12),
                  ResponsiveGrid(
                    minItemWidth: 230,
                    children: [
                      for (final c in list.where((c) => c.grade == grade)) _ClassCard(c),
                    ],
                  ),
                  const SizedBox(height: 24),
                ],
            ],
          ),
        ),
      ],
    );
  }
}

class _ClassCard extends StatelessWidget {
  const _ClassCard(this.schoolClass);
  final SchoolClass schoolClass;

  @override
  Widget build(BuildContext context) => PanelCard(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(child: Text(schoolClass.name, style: AdminText.headline(size: 22))),
              Pill('Grade ${schoolClass.grade}'),
            ]),
            const SizedBox(height: 4),
            Text('${schoolClass.studentCount} Students',
                style: AdminText.body(weight: FontWeight.w600, color: AdminColors.primary)),
            const SizedBox(height: 10),
            Row(children: [
              const Icon(Icons.circle, size: 8, color: AdminColors.success),
              const SizedBox(width: 6),
              Text('${schoolClass.activeCount} active', style: AdminText.small),
              const Spacer(),
              Text('Avg. ${formatScore(schoolClass.averageScore)}', style: AdminText.small),
            ]),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: TextButton(
                style: TextButton.styleFrom(
                  backgroundColor: AdminColors.primarySoft,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
                onPressed: () => context.go('/classes/${schoolClass.id}'),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text('View Class'),
                    SizedBox(width: 6),
                    Icon(Icons.arrow_forward_rounded, size: 16),
                  ],
                ),
              ),
            ),
          ],
        ),
      );
}
