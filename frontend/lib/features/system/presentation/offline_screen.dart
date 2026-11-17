import 'package:flutter/material.dart';

import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';

// ----------------------------------------------------------------- Offline
class OfflineScreen extends StatefulWidget {
  const OfflineScreen({super.key, this.onRetry});

  /// Tries to reach the server again; returns true when it worked (the caller then
  /// navigates away). Null in the design gallery.
  final Future<bool> Function()? onRetry;

  @override
  State<OfflineScreen> createState() => _OfflineScreenState();
}

class _OfflineScreenState extends State<OfflineScreen> {
  bool _loading = false;

  Future<void> _retry() async {
    setState(() => _loading = true);
    final retry = widget.onRetry;
    final ok = retry == null
        ? await Future.delayed(const Duration(milliseconds: 1500), () => false)
        : await retry();
    if (!mounted || ok) return;
    setState(() => _loading = false);
    showAppSnack(context, 'Masih belum terhubung. Coba lagi sebentar lagi.');
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
