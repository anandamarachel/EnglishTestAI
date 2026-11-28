import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day_admin/core/format.dart';
import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/data/models.dart';

/// White rounded panel used for every section.
class PanelCard extends StatelessWidget {
  const PanelCard({super.key, required this.child, this.padding = const EdgeInsets.all(20)});
  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: padding,
        decoration: BoxDecoration(
          color: AdminColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AdminColors.border),
        ),
        child: child,
      );
}

/// Section title with an optional subtitle and trailing widget.
class SectionHeader extends StatelessWidget {
  const SectionHeader({super.key, required this.title, this.subtitle, this.trailing});
  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AdminText.sectionTitle),
                if (subtitle != null) ...[
                  const SizedBox(height: 4),
                  Text(subtitle!, style: AdminText.small),
                ],
              ],
            ),
          ),
          if (trailing != null) trailing!,
        ],
      );
}

/// Page title block at the top of each page.
class PageHeader extends StatelessWidget {
  const PageHeader({super.key, required this.title, this.subtitle, this.trailing, this.eyebrow});
  final String title;
  final String? subtitle;
  final String? eyebrow;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.end,
        runSpacing: 12,
        spacing: 16,
        children: [
          Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (eyebrow != null) ...[
                Text(eyebrow!.toUpperCase(),
                    style: AdminText.caps.copyWith(color: AdminColors.primary)),
                const SizedBox(height: 6),
              ],
              Text(title, style: AdminText.pageTitle),
              if (subtitle != null) ...[
                const SizedBox(height: 6),
                Text(subtitle!, style: AdminText.body(color: AdminColors.textSecondary)),
              ],
            ],
          ),
          if (trailing != null) trailing!,
        ],
      );
}

/// "← Back to …" link above detail pages.
class BackLink extends StatelessWidget {
  const BackLink({super.key, required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          onPressed: onTap,
          style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 4)),
          icon: const Icon(Icons.arrow_back_rounded, size: 18),
          label: Text(label),
        ),
      );
}

/// Thin rounded progress bar.
class ThinBar extends StatelessWidget {
  const ThinBar({super.key, required this.value, this.color = AdminColors.primary, this.height = 6});
  final double value; // 0..1
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(height),
        child: LinearProgressIndicator(
          value: value.clamp(0, 1),
          minHeight: height,
          color: color,
          backgroundColor: AdminColors.primarySoft,
        ),
      );
}

/// Summary number card (Total Students, Average Score, ...).
class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    this.unit,
    this.caption,
    this.badge,
    this.progress,
  });

  final String label;
  final String value;
  final String? unit;
  final IconData icon;
  final String? caption;
  final String? badge;
  final double? progress;

  @override
  Widget build(BuildContext context) => PanelCard(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(label.toUpperCase(), style: AdminText.caps)),
                Container(
                  width: 34,
                  height: 34,
                  decoration: const BoxDecoration(color: AdminColors.primarySoft, shape: BoxShape.circle),
                  child: Icon(icon, size: 18, color: AdminColors.primary),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                // Long values shrink instead of wrapping on narrow cards.
                Flexible(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerLeft,
                    child: Text.rich(TextSpan(children: [
                      TextSpan(text: value, style: AdminText.statValue),
                      if (unit != null)
                        TextSpan(
                            text: ' $unit',
                            style: AdminText.body(size: 14, color: AdminColors.textSecondary)),
                    ])),
                  ),
                ),
                if (badge != null) ...[const SizedBox(width: 8), Pill(badge!)],
              ],
            ),
            if (caption != null) ...[
              const SizedBox(height: 4),
              Text(caption!, style: AdminText.small, maxLines: 1, overflow: TextOverflow.ellipsis),
            ],
            // Same height with or without a bar, so cards in a row line up.
            const SizedBox(height: 12),
            progress == null ? const SizedBox(height: 4) : ThinBar(value: progress!, height: 4),
          ],
        ),
      );
}

/// Small rounded label.
class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.color = AdminColors.primary, this.background, this.icon});
  final String text;
  final Color color;
  final Color? background;
  final IconData? icon;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: background ?? AdminColors.primarySoft,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[Icon(icon, size: 13, color: color), const SizedBox(width: 4)],
            Text(text, style: AdminText.body(size: 11.5, weight: FontWeight.w600, color: color)),
          ],
        ),
      );
}

/// Module badge (icon + "Writing").
class SkillBadge extends StatelessWidget {
  const SkillBadge(this.skill, {super.key});
  final Skill skill;

  @override
  Widget build(BuildContext context) => Pill(skill.label, icon: skill.icon, color: skill.color);
}

/// Score number in a soft pill; amber below 70.
class ScoreChip extends StatelessWidget {
  const ScoreChip(this.score, {super.key});
  final double? score;

  @override
  Widget build(BuildContext context) {
    final low = score != null && score! < 70;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: low ? AdminColors.warningSoft : AdminColors.primarySoft,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(formatScore(score),
          style: AdminText.body(
              size: 13,
              weight: FontWeight.w700,
              color: low ? AdminColors.warning : AdminColors.primary)),
    );
  }
}

/// Active / Inactive.
class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.active});
  final bool active;

  @override
  Widget build(BuildContext context) => Pill(
        active ? 'Active' : 'Inactive',
        icon: Icons.circle,
        color: active ? AdminColors.success : AdminColors.textSecondary,
        background: active ? AdminColors.successSoft : AdminColors.divider,
      );
}

class InitialsAvatar extends StatelessWidget {
  const InitialsAvatar(this.initials, {super.key, this.size = 34});
  final String initials;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: const BoxDecoration(color: AdminColors.primarySoft, shape: BoxShape.circle),
        child: Text(initials,
            style: AdminText.body(
                size: size * 0.36, weight: FontWeight.w700, color: AdminColors.primary)),
      );
}

/// Avatar + name + one line below (email, or "Grade 11 • XI-A").
class StudentNameCell extends StatelessWidget {
  const StudentNameCell({super.key, required this.student, this.showClass = false});
  final StudentSummary student;
  final bool showClass;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          InitialsAvatar(student.initials),
          const SizedBox(width: 10),
          Flexible(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(student.name,
                    style: AdminText.body(size: 13.5, weight: FontWeight.w600),
                    overflow: TextOverflow.ellipsis),
                Text(
                  showClass ? 'Grade ${student.grade} • ${student.className}' : student.email,
                  style: AdminText.small,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      );
}

/// "All Grades / Grade 10 / 11 / 12" dropdown.
class GradeFilter extends StatelessWidget {
  const GradeFilter({super.key, required this.grade, required this.onChanged});
  final int? grade;
  final ValueChanged<int?> onChanged;

  @override
  Widget build(BuildContext context) => Container(
        height: 46,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: AdminColors.primaryTint,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AdminColors.border),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<int?>(
            value: grade,
            borderRadius: BorderRadius.circular(10),
            style: AdminText.body(size: 13.5, weight: FontWeight.w600),
            icon: const Icon(Icons.expand_more_rounded, size: 20),
            onChanged: onChanged,
            items: const [
              DropdownMenuItem(value: null, child: Text('All Grades')),
              DropdownMenuItem(value: 10, child: Text('Grade 10')),
              DropdownMenuItem(value: 11, child: Text('Grade 11')),
              DropdownMenuItem(value: 12, child: Text('Grade 12')),
            ],
          ),
        ),
      );
}

/// Search box with a magnifier icon.
class SearchField extends StatelessWidget {
  const SearchField({super.key, required this.hint, required this.onChanged, this.controller});
  final String hint;
  final ValueChanged<String> onChanged;
  final TextEditingController? controller;

  @override
  Widget build(BuildContext context) => SizedBox(
        height: 46,
        child: TextField(
          controller: controller,
          onChanged: onChanged,
          style: AdminText.body(size: 13.5),
          decoration: InputDecoration(
            hintText: hint,
            prefixIcon: const Icon(Icons.search_rounded, size: 20),
          ),
        ),
      );
}

/// "View Details →" table action.
class ViewDetailsLink extends StatelessWidget {
  const ViewDetailsLink({super.key, required this.onTap, this.label = 'View Details'});
  final VoidCallback onTap;
  final String label;

  @override
  Widget build(BuildContext context) => TextButton(
        onPressed: onTap,
        style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 8)),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right_rounded, size: 18),
          ],
        ),
      );
}

/// Lays children in [columns] equal columns, fewer on narrow widths.
class ResponsiveGrid extends StatelessWidget {
  const ResponsiveGrid({
    super.key,
    required this.children,
    this.minItemWidth = 220,
    this.maxColumns = 4,
    this.spacing = 16,
  });

  final List<Widget> children;
  final double minItemWidth;
  final int maxColumns;
  final double spacing;

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        var columns =
            ((c.maxWidth + spacing) / (minItemWidth + spacing)).floor().clamp(1, maxColumns);
        // Avoid a lonely last item (e.g. 4 cards as 3 + 1): use 2 + 2 instead.
        if (columns > 2 && children.length % columns != 0 && children.length % (columns - 1) == 0) {
          columns--;
        }
        final width = (c.maxWidth - spacing * (columns - 1)) / columns;
        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: [for (final child in children) SizedBox(width: width, child: child)],
        );
      });
}

/// Loading / error / data for one AsyncValue, with a retry on error.
class AsyncSection<T> extends StatelessWidget {
  const AsyncSection({
    super.key,
    required this.value,
    required this.builder,
    required this.onRetry,
    this.loadingHeight = 220,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final VoidCallback onRetry;
  final double loadingHeight;

  @override
  Widget build(BuildContext context) => value.when(
        skipLoadingOnRefresh: false,
        skipLoadingOnReload: true,
        data: builder,
        loading: () => SizedBox(
          height: loadingHeight,
          child: const Center(
            child: SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(strokeWidth: 2.4),
            ),
          ),
        ),
        error: (e, _) => PanelCard(
          child: Row(
            children: [
              const Icon(Icons.error_outline_rounded, color: AdminColors.danger),
              const SizedBox(width: 12),
              Expanded(
                child: Text('Data could not be loaded. Please try again.',
                    style: AdminText.body(color: AdminColors.danger)),
              ),
              TextButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}
