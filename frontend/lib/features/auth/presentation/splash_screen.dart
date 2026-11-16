import 'dart:async';

import 'package:flutter/material.dart';

import 'package:english_day/core/config/app_info.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/auth/presentation/login_screen.dart';

// ------------------------------------------------------------------ Splash
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key, this.autoNavigate = true});
  final bool autoNavigate;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    if (widget.autoNavigate) {
      _timer = Timer(const Duration(milliseconds: 1800), () {
        if (!mounted) return;
        Navigator.of(context).pushReplacement(
          PageRouteBuilder(
            pageBuilder: (_, __, ___) => const LoginScreen(),
            transitionsBuilder: (_, a, __, child) => FadeTransition(opacity: a, child: child),
          ),
        );
      });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
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
