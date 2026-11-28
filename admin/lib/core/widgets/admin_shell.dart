import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:english_day_admin/core/app_info.dart';
import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/core/widgets/common.dart';
import 'package:english_day_admin/data/providers.dart';

/// Sidebar + top bar around every signed-in page. Below [_wide] px the sidebar
/// becomes a drawer opened from the top bar.
class AdminShell extends ConsumerWidget {
  const AdminShell({super.key, required this.location, required this.child});

  final String location;
  final Widget child;

  static const _wide = 1000.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // MediaQuery, not LayoutBuilder: [child] holds the router's Navigator, which must
    // not live inside a LayoutBuilder's build scope (it breaks page changes).
    final wide = MediaQuery.sizeOf(context).width >= _wide;
    final sidebar = _Sidebar(location: location);
    return Scaffold(
          drawer: wide ? null : Drawer(width: 260, child: sidebar),
          body: Row(
            children: [
              if (wide) SizedBox(width: 248, child: sidebar),
              Expanded(
                child: Column(
                  children: [
                    _TopBar(showMenu: !wide),
                    Expanded(
                      // Text can be selected and copied (student IDs, emails).
                      child: SelectionArea(
                        child: SingleChildScrollView(
                          padding: EdgeInsets.fromLTRB(wide ? 32 : 16, 24, wide ? 32 : 16, 40),
                          child: Center(
                            child: ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 1240),
                              child: child,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({required this.location});
  final String location;

  @override
  Widget build(BuildContext context) {
    final onStudents = location.startsWith('/students') || location.startsWith('/classes');
    return Container(
      decoration: const BoxDecoration(
        color: AdminColors.surface,
        border: Border(right: BorderSide(color: AdminColors.border)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const AppLogo(),
          const SizedBox(height: 28),
          Padding(
            padding: const EdgeInsets.only(left: 12, bottom: 8),
            child: Text('MENU', style: AdminText.caps),
          ),
          _NavItem(
            icon: Icons.grid_view_rounded,
            label: 'Dashboard',
            selected: location.startsWith('/dashboard'),
            onTap: () => _go(context, '/dashboard'),
          ),
          _NavItem(
            icon: Icons.school_outlined,
            label: 'Students & Classes',
            selected: onStudents,
            onTap: () => _go(context, '/students'),
          ),
          const Spacer(),
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
                Row(children: [
                  const Icon(Icons.apartment_rounded, size: 16, color: AdminColors.primary),
                  const SizedBox(width: 6),
                  Text(AppInfo.school, style: AdminText.body(size: 13, weight: FontWeight.w700)),
                ]),
                const SizedBox(height: 6),
                Text('Academic Year ${AppInfo.academicYear}', style: AdminText.small),
                const SizedBox(height: 4),
                Row(children: [
                  const Icon(Icons.circle, size: 8, color: AdminColors.success),
                  const SizedBox(width: 6),
                  Text('${AppInfo.term} Active', style: AdminText.small),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _go(BuildContext context, String path) {
    if (Scaffold.maybeOf(context)?.isDrawerOpen ?? false) Navigator.of(context).pop();
    context.go(path);
  }
}

/// "English Day / ADMIN PORTAL" mark.
class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.onDark = false});
  final bool onDark;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: onDark ? Colors.white.withValues(alpha: 0.14) : AdminColors.primary,
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.auto_stories_rounded, color: Colors.white, size: 22),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(AppInfo.appName,
                  style: AdminText.headline(
                      size: 17,
                      weight: FontWeight.w800,
                      color: onDark ? Colors.white : AdminColors.textPrimary)),
              Text(AppInfo.portalName.toUpperCase(),
                  style: AdminText.caps.copyWith(
                      fontSize: 10,
                      color: onDark ? Colors.white70 : AdminColors.primary)),
            ],
          ),
        ],
      );
}

class _NavItem extends StatelessWidget {
  const _NavItem({required this.icon, required this.label, required this.selected, required this.onTap});
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Material(
          color: selected ? AdminColors.primarySoft : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
              child: Row(
                children: [
                  Icon(icon, size: 20, color: selected ? AdminColors.primary : AdminColors.textSecondary),
                  const SizedBox(width: 12),
                  Text(label,
                      style: AdminText.body(
                          size: 14,
                          weight: selected ? FontWeight.w700 : FontWeight.w500,
                          color: selected ? AdminColors.primary : AdminColors.textPrimary)),
                ],
              ),
            ),
          ),
        ),
      );
}

class _TopBar extends ConsumerWidget {
  const _TopBar({required this.showMenu});
  final bool showMenu;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final admin = ref.watch(adminSessionProvider);
    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        color: AdminColors.surface,
        border: Border(bottom: BorderSide(color: AdminColors.border)),
      ),
      child: Row(
        children: [
          if (showMenu)
            IconButton(
              tooltip: 'Menu',
              onPressed: () => Scaffold.of(context).openDrawer(),
              icon: const Icon(Icons.menu_rounded),
            ),
          const SizedBox(width: 8),
          Expanded(
            child: Text('${AppInfo.portalName}  ›  ${AppInfo.school}',
                style: AdminText.small, overflow: TextOverflow.ellipsis),
          ),
          PopupMenuButton<String>(
            tooltip: 'Account',
            position: PopupMenuPosition.under,
            offset: const Offset(0, 8),
            onSelected: (value) async {
              if (value == 'logout') await ref.read(adminSessionProvider.notifier).logout();
            },
            itemBuilder: (_) => [
              PopupMenuItem<String>(
                enabled: false,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(admin?.name ?? '', style: AdminText.body(weight: FontWeight.w700)),
                    Text(admin?.email ?? '', style: AdminText.small),
                  ],
                ),
              ),
              const PopupMenuDivider(),
              PopupMenuItem<String>(
                value: 'logout',
                child: Row(children: [
                  const Icon(Icons.logout_rounded, size: 18, color: AdminColors.danger),
                  const SizedBox(width: 10),
                  Text('Logout', style: AdminText.body(color: AdminColors.danger)),
                ]),
              ),
            ],
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Row(
                children: [
                  InitialsAvatar(admin?.initials ?? '', size: 34),
                  const SizedBox(width: 10),
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(admin?.name ?? '', style: AdminText.body(size: 13, weight: FontWeight.w700)),
                      Text(admin?.role ?? '', style: AdminText.small.copyWith(fontSize: 11.5)),
                    ],
                  ),
                  const SizedBox(width: 4),
                  const Icon(Icons.expand_more_rounded, color: AdminColors.textSecondary),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
