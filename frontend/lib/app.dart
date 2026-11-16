import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/auth/presentation/splash_screen.dart';

class EnglishDayApp extends StatelessWidget {
  const EnglishDayApp({super.key, this.home});

  final Widget? home;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'English Day',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: home ?? const SplashScreen(),
    );
  }
}
