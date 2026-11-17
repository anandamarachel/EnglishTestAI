import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/config/app_info.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/auth/presentation/login_screen.dart';
import 'package:english_day/features/dashboard/presentation/dashboard_screen.dart';
import 'package:english_day/features/system/presentation/offline_screen.dart';

// ------------------------------------------------------------------ Splash
/// Shows the brand while the stored session is restored, then opens the dashboard
/// (still logged in), the login screen, or the offline screen (server unreachable).
class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key, this.autoNavigate = true});

  /// False in the design gallery: stay on the splash, touch no session or network.
  final bool autoNavigate;

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  static const _minimumVisible = Duration(milliseconds: 1800);

  @override
  void initState() {
    super.initState();
    if (widget.autoNavigate) _start();
  }

  Future<void> _start() async {
    // Keep the splash on screen at least as long as before, even when restoring is instant.
    final results = await Future.wait([
      Future<void>.delayed(_minimumVisible),
      _restore(),
    ]);
    if (!mounted) return;
    final session = results[1] as Session?;
    final navigator = Navigator.of(context);
    if (session == null) {
      // Opening the offline screen removes this route and disposes this State, so
      // the retry must not use its ref/context: it keeps the container and navigator.
      final container = ProviderScope.containerOf(context, listen: false);
      _go(navigator, OfflineScreen(onRetry: () => _retryFromOffline(container, navigator)));
    } else {
      _goFor(navigator, session);
    }
  }

  /// Null when the server could not be reached.
  Future<Session?> _restore() async {
    try {
      return await ref.read(sessionControllerProvider.future);
    } catch (_) {
      return null;
    }
  }

  static Future<bool> _retryFromOffline(
      ProviderContainer container, NavigatorState navigator) async {
    try {
      await container.read(sessionControllerProvider.notifier).retryRestore();
    } catch (_) {
      return false;
    }
    final session = container.read(sessionControllerProvider).valueOrNull;
    if (session == null || !navigator.mounted) return false;
    _goFor(navigator, session);
    return true;
  }

  static void _goFor(NavigatorState navigator, Session session) =>
      _go(navigator, session.isLoggedIn ? const DashboardScreen() : const LoginScreen());

  static void _go(NavigatorState navigator, Widget page) {
    navigator.pushAndRemoveUntil(
      PageRouteBuilder(
        pageBuilder: (_, __, ___) => page,
        transitionsBuilder: (_, a, __, child) => FadeTransition(opacity: a, child: child),
      ),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(AppInfo.appName, style: AppText.display),
            const SizedBox(height: 16),
            Container(width: 72, height: 2, color: AppColors.border),
            const SizedBox(height: 16),
            Text(AppInfo.tagline, style: AppText.sans(size: 14, color: AppColors.textSecondary)),
          ],
        ),
      ),
    );
  }
}
