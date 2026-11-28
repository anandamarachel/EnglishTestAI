import 'package:flutter/material.dart';

import 'package:english_day_admin/core/theme/admin_theme.dart';

/// One column of an [AdminTable].
class AdminColumn {
  const AdminColumn(this.label, {this.flex = 1, this.alignEnd = false});
  final String label;
  final int flex;
  final bool alignEnd;
}

/// Simple data table: caps header row, then rows separated by thin lines.
/// Scrolls horizontally on narrow screens instead of squeezing the columns.
class AdminTable extends StatelessWidget {
  const AdminTable({
    super.key,
    required this.columns,
    required this.rows,
    this.onRowTap,
    this.minWidth = 760,
    this.emptyText = 'No data found.',
  });

  final List<AdminColumn> columns;
  final List<List<Widget>> rows;
  final void Function(int index)? onRowTap;
  final double minWidth;
  final String emptyText;

  Widget _cell(AdminColumn column, Widget child) => Expanded(
        flex: column.flex,
        child: Align(
          alignment: column.alignEnd ? Alignment.centerRight : Alignment.centerLeft,
          child: child,
        ),
      );

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        final width = c.maxWidth < minWidth ? minWidth : c.maxWidth;
        final table = SizedBox(
          width: width,
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: AdminColors.primaryTint,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(children: [
                  for (final col in columns)
                    _cell(col, Text(col.label.toUpperCase(), style: AdminText.caps)),
                ]),
              ),
              if (rows.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 36),
                  child: Text(emptyText, style: AdminText.small),
                ),
              for (var i = 0; i < rows.length; i++)
                InkWell(
                  onTap: onRowTap == null ? null : () => onRowTap!(i),
                  hoverColor: AdminColors.primaryTint,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    decoration: const BoxDecoration(
                      border: Border(bottom: BorderSide(color: AdminColors.divider)),
                    ),
                    child: Row(children: [
                      for (var j = 0; j < columns.length; j++) _cell(columns[j], rows[i][j]),
                    ]),
                  ),
                ),
            ],
          ),
        );
        return c.maxWidth < minWidth
            ? SingleChildScrollView(scrollDirection: Axis.horizontal, child: table)
            : table;
      });
}

/// "Showing 1–10 of 500 students"  ‹ Previous 1 2 3 … 50 Next ›
class PaginationBar extends StatelessWidget {
  const PaginationBar({
    super.key,
    required this.page,
    required this.pageCount,
    required this.summary,
    required this.onPage,
  });

  final int page;
  final int pageCount;
  final String summary;
  final ValueChanged<int> onPage;

  List<int?> _pages() {
    if (pageCount <= 7) return [for (var i = 1; i <= pageCount; i++) i];
    final set = <int>{1, 2, pageCount, page - 1, page, page + 1}
        .where((p) => p >= 1 && p <= pageCount)
        .toList()
      ..sort();
    final out = <int?>[];
    for (final p in set) {
      if (out.isNotEmpty && out.last != null && p - out.last! > 1) out.add(null); // gap
      out.add(p);
    }
    return out;
  }

  @override
  Widget build(BuildContext context) => Row(
        children: [
          Expanded(child: Text(summary, style: AdminText.small, overflow: TextOverflow.ellipsis)),
          const SizedBox(width: 12),
          Flexible(
            flex: 0,
            // Scrolls instead of overflowing on very narrow screens.
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: _pageButtons(),
            ),
          ),
        ],
      );

  Widget _pageButtons() => Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextButton.icon(
                onPressed: page > 1 ? () => onPage(page - 1) : null,
                icon: const Icon(Icons.chevron_left_rounded, size: 18),
                label: const Text('Previous'),
              ),
              for (final p in _pages())
                p == null
                    ? Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 6),
                        child: Text('…', style: AdminText.small),
                      )
                    : Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 2),
                        child: _PageButton(page: p, selected: p == page, onTap: () => onPage(p)),
                      ),
              TextButton(
                onPressed: page < pageCount ? () => onPage(page + 1) : null,
                child: const Row(mainAxisSize: MainAxisSize.min, children: [
                  Text('Next'),
                  Icon(Icons.chevron_right_rounded, size: 18),
                ]),
              ),
            ],
          );
}

class _PageButton extends StatelessWidget {
  const _PageButton({required this.page, required this.selected, required this.onTap});
  final int page;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: selected ? AdminColors.primary : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: selected ? null : onTap,
          child: SizedBox(
            width: 32,
            height: 32,
            child: Center(
              child: Text('$page',
                  style: AdminText.body(
                      size: 13,
                      weight: FontWeight.w600,
                      color: selected ? Colors.white : AdminColors.textPrimary)),
            ),
          ),
        ),
      );
}
