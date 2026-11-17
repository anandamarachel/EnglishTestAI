import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/navigation/route_observer.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/auth/presentation/splash_screen.dart';
import 'package:english_day/features/dashboard/presentation/dashboard_screen.dart';

class EnglishDayApp extends ConsumerStatefulWidget {
  const EnglishDayApp({super.key, this.home});

  final Widget? home;

  @override
  ConsumerState<EnglishDayApp> createState() => _EnglishDayAppState();
}

class _EnglishDayAppState extends ConsumerState<EnglishDayApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();

  @override
  Widget build(BuildContext context) {
    // The server ended an active session (revoked/expired refresh token): whatever
    // screen is open, show the "Sesimu sudah berakhir" sheet that leads to login.
    ref.listen(sessionControllerProvider, (previous, next) {
      final wasExpired = previous?.valueOrNull?.expired ?? false;
      final isExpired = next.valueOrNull?.expired ?? false;
      final context = _navigatorKey.currentContext;
      if (isExpired && !wasExpired && context != null) showSessionExpiredSheet(context);
    });

    return MaterialApp(
      navigatorKey: _navigatorKey,
      navigatorObservers: [appRouteObserver],
      title: 'English Day',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: widget.home ?? const SplashScreen(),
    );
  }
}
