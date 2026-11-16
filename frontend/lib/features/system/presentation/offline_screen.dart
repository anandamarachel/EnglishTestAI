import 'package:flutter/material.dart';

import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';

// ----------------------------------------------------------------- Offline
class OfflineScreen extends StatefulWidget {
  const OfflineScreen({super.key});

  @override
  State<OfflineScreen> createState() => _OfflineScreenState();
}

class _OfflineScreenState extends State<OfflineScreen> {
  bool _loading = false;

  Future<void> _retry() async {
    setState(() => _loading = true);
    await Future.delayed(const Duration(milliseconds: 1500));
    if (!mounted) return;
    setState(() => _loading = false);
    showAppSnack(context, 'Masih offline (dummy).');
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'English Day',
      bottom: AppButton(
        label: 'Coba lagi',
        loading: _loading,
        loadingLabel: 'Menghubungkan…',
        onPressed: _retry,
      ),
      body: const InfoStateView(
        icon: Icons.wifi_off_rounded,
        circleSize: 72,
        title: 'Tidak ada koneksi internet',
        message: 'Periksa jaringanmu, lalu coba lagi.',
      ),
    );
  }
}
