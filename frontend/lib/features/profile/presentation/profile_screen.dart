import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/config/app_info.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/dev/gallery_screen.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/auth/presentation/login_screen.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key, this.showLogoutConfirm = false});

  /// Only the design gallery opens the logout sheet directly.
  final bool showLogoutConfirm;

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  @override
  void initState() {
    super.initState();
    if (widget.showLogoutConfirm) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _confirmLogout());
    }
  }

  Future<void> _logout(BuildContext sheetContext) async {
    final navigator = Navigator.of(sheetContext);
    // Revokes the session on the server when reachable; always logs out locally.
    await ref.read(sessionControllerProvider.notifier).logout();
    navigator.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  void _confirmLogout() {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Keluar dari akun?', style: AppText.h2),
            const SizedBox(height: 16),
            Text('Kamu perlu masuk lagi untuk melanjutkan latihan.', style: AppText.body),
            const SizedBox(height: 24),
            AppButton.danger(label: 'Keluar', onPressed: () => _logout(ctx)),
            const SizedBox(height: 24),
            AppButton.secondary(label: 'Batal', onPressed: () => Navigator.pop(ctx)),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserProvider);
    return AppScaffold(
      title: 'Profil',
      bottom: AppButton.danger(label: 'Keluar', onPressed: _confirmLogout),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Container(
              width: 72,
              height: 72,
              decoration: const BoxDecoration(color: AppColors.primarySoft, shape: BoxShape.circle),
              alignment: Alignment.center,
              child: Text(user?.initials ?? '',
                  style: AppText.sans(size: 22, weight: FontWeight.w700, color: AppColors.primary)),
            ),
          ),
          const SizedBox(height: 16),
          Text(user?.displayName ?? '', style: AppText.h2),
          const SizedBox(height: 12),
          Text(user?.email ?? '', style: AppText.body),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: AppColors.primarySoft,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: AppColors.primary),
              ),
              child: Text(user?.roleLabel ?? '',
                  style: AppText.sans(size: 15, weight: FontWeight.w600, color: AppColors.primary)),
            ),
          ),
          const SizedBox(height: 24),
          AppCard(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Column(
              children: [
                _ProfileItem(
                  icon: Icons.person_outline,
                  label: 'Ubah nama',
                  // TODO(api): PATCH /users/me once the edit-name screen is designed.
                  onTap: () => showAppSnack(context, 'Fitur ubah nama segera hadir.'),
                ),
                _ProfileItem(
                  icon: Icons.lock_outline,
                  label: 'Ubah password',
                  // TODO(api): POST /auth/password/change once the screen is designed.
                  onTap: () => showAppSnack(context, 'Fitur ubah password segera hadir.'),
                ),
                _ProfileItem(
                  icon: Icons.info_outline,
                  label: 'Tentang aplikasi',
                  // The design gallery is a developer tool: debug builds only.
                  onTap: () => kDebugMode
                      ? Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => const GalleryScreen()))
                      : showAboutDialog(
                          context: context,
                          applicationName: AppInfo.appName,
                          applicationVersion: AppInfo.version,
                          applicationLegalese: AppInfo.school,
                        ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          Text('${AppInfo.tagline}\nVersi ${AppInfo.version}', style: AppText.small),
        ],
      ),
    );
  }
}

class _ProfileItem extends StatelessWidget {
  const _ProfileItem({required this.icon, required this.label, required this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: SizedBox(
        height: 60,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              Icon(icon, color: AppColors.primary, size: 24),
              const SizedBox(width: 16),
              Expanded(child: Text(label, style: AppText.sans(size: 15, weight: FontWeight.w600))),
              const Icon(Icons.chevron_right, color: AppColors.primary),
            ],
          ),
        ),
      ),
    );
  }
}
