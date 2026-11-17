import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/auth/presentation/login_screen.dart';
import 'package:english_day/features/dashboard/data/dashboard.dart';
import 'package:english_day/features/listening/presentation/listening_screen.dart';
import 'package:english_day/features/profile/presentation/profile_screen.dart';
import 'package:english_day/features/reading/presentation/reading_settings_screen.dart';
import 'package:english_day/features/reading/presentation/reading_story_screen.dart';
import 'package:english_day/features/speaking/presentation/mic_permission_screen.dart';
import 'package:english_day/features/writing/presentation/writing_input_screen.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key, this.showSessionExpired = false});

  /// Only the design gallery opens the "session ended" sheet directly; in the app it
  /// is shown by EnglishDayApp when the server ends the session.
  final bool showSessionExpired;

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    if (widget.showSessionExpired) {
      WidgetsBinding.instance.addPostFrameCallback((_) => showSessionExpiredSheet(context));
    }
  }

  /// Opens a page and reloads the dashboard when the user comes back (progress changed).
  Future<void> _push(Widget page) async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
    if (mounted) ref.invalidate(dashboardProvider);
  }

  /// Practice screens are not connected to the API yet: open the skill's screen.
  // TODO(api): pass resume.attemptId once each practice module loads real attempts.
  Widget _resumePage(AttemptSummary resume) => switch (resume.skill) {
        'writing' => const WritingInputScreen(),
        'listening' => const ListeningScreen(),
        'speaking' => const MicPermissionScreen(),
        _ => const ReadingStoryScreen(),
      };

  @override
  Widget build(BuildContext context) {
    final dashboard = ref.watch(dashboardProvider);
    final user = dashboard.valueOrNull?.user ?? ref.watch(currentUserProvider);
    final resume = dashboard.valueOrNull?.resumeAttempt;
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          color: AppColors.primary,
          onRefresh: () => ref.refresh(dashboardProvider.future).then((_) {}, onError: (_) {}),
          child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(user == null ? 'Halo' : 'Halo, ${user.firstName}',
                          style: AppText.display),
                      const SizedBox(height: 4),
                      Text('Mau latihan apa hari ini?',
                          style: AppText.body.copyWith(fontSize: 17)),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Material(
                    color: AppColors.primarySoft,
                    shape: const CircleBorder(),
                    child: InkWell(
                      customBorder: const CircleBorder(),
                      onTap: () => _push(const ProfileScreen()),
                      child: SizedBox(
                        width: 44,
                        height: 44,
                        child: Center(
                          child: Text(user?.initials ?? '',
                              style: AppText.sans(
                                  size: 15, weight: FontWeight.w700, color: AppColors.primary)),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            if (dashboard.hasError && !dashboard.isLoading && !_isSessionEnded(dashboard.error)) ...[
              StatusBanner(
                type: BannerType.error,
                message: _errorText(dashboard.error),
                actionLabel: 'Coba lagi',
                onAction: () => ref.invalidate(dashboardProvider),
              ),
              const SizedBox(height: 28),
            ],
            if (resume != null) ...[
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Lanjutkan latihan',
                        style: AppText.sans(
                            size: 15, weight: FontWeight.w500, color: AppColors.textSecondary)),
                    const SizedBox(height: 12),
                    Text('${resume.skillLabel} · ${resume.title}',
                        style: AppText.sans(size: 19, weight: FontWeight.w600)),
                    const SizedBox(height: 12),
                    AppButton.secondary(
                      label: 'Lanjutkan',
                      onPressed: () => _push(_resumePage(resume)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),
            ],
            Text('Latihan', style: AppText.h3),
            const SizedBox(height: 12),
            _MenuTile(
              icon: Icons.edit_outlined,
              iconColor: AppColors.primary,
              bg: AppColors.writingBg,
              title: 'Writing',
              subtitle: 'Tulis kalimat, AI tandai yang perlu diperbaiki',
              onTap: () => _push(const WritingInputScreen()),
            ),
            _MenuTile(
              icon: Icons.menu_book_outlined,
              iconColor: AppColors.readingIcon,
              bg: AppColors.readingBg,
              title: 'Reading',
              subtitle: 'Baca cerita pendek, lalu jawab kuis',
              onTap: () => _push(const ReadingSettingsScreen()),
            ),
            _MenuTile(
              icon: Icons.mic_none_rounded,
              iconColor: AppColors.speakingIcon,
              bg: AppColors.speakingBg,
              title: 'Speaking',
              subtitle: 'Ngobrol langsung dengan AI pakai suara',
              onTap: () => _push(const MicPermissionScreen()),
            ),
            _MenuTile(
              icon: Icons.headphones_outlined,
              iconColor: AppColors.listeningIcon,
              bg: AppColors.listeningBg,
              title: 'Listening',
              subtitle: 'Dengarkan audio, lalu jawab pertanyaan',
              onTap: () => _push(const ListeningScreen()),
            ),
          ],
          ),
        ),
      ),
    );
  }

  /// Shown by the global session-expired sheet instead (see app.dart).
  static bool _isSessionEnded(Object? error) => error is ApiException && error.isSessionEnded;

  static String _errorText(Object? error) => error is ApiException
      ? error.userMessage
      : 'Gagal memuat dashboard. Coba lagi dalam beberapa saat.';
}

class _MenuTile extends StatelessWidget {
  const _MenuTile({
    required this.icon,
    required this.iconColor,
    required this.bg,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final Color iconColor;
  final Color bg;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: AppCard(
        onTap: onTap,
        padding: const EdgeInsets.fromLTRB(12, 18, 12, 18),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(10)),
              child: Icon(icon, color: iconColor, size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: AppText.sans(size: 16, weight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Text(subtitle,
                      style: AppText.sans(size: 13, color: AppColors.textSecondary, height: 1.35)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right, color: AppColors.primary),
          ],
        ),
      ),
    );
  }
}

/// Bottom sheet "Sesimu sudah berakhir".
Future<void> showSessionExpiredSheet(BuildContext context) {
  return showModalBottomSheet(
    context: context,
    isDismissible: false,
    enableDrag: false,
    showDragHandle: true, // as in the design; enableDrag: false would hide it
    builder: (ctx) => Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Sesimu sudah berakhir.\nMasuk lagi untuk melanjutkan.',
              style: AppText.sans(size: 21, weight: FontWeight.w600, height: 1.4)),
          const SizedBox(height: 20),
          AppButton(
            label: 'Masuk',
            onPressed: () => Navigator.of(ctx).pushAndRemoveUntil(
              MaterialPageRoute(builder: (_) => const LoginScreen()),
              (_) => false,
            ),
          ),
        ],
      ),
    ),
  );
}
