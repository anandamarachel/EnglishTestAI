import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';

// --------------------------------------------------------------- AI status
class AiStatusScreen extends StatelessWidget {
  const AiStatusScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Status latihan',
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text('Status AI', style: AppText.h2),
          const SizedBox(height: 20),
          Text('Memproses lebih dari 10 detik', style: AppText.caption),
          const SizedBox(height: 8),
          StatusBanner.slow(onAction: () {}),
          const SizedBox(height: 20),
          Text('Timeout · input tetap tersimpan', style: AppText.caption),
          const SizedBox(height: 8),
          StatusBanner.timeout(onAction: () {}),
          const SizedBox(height: 28),
          Text('Memproses kurang dari 10 detik', style: AppText.caption),
          const SizedBox(height: 8),
          const AppButton(label: 'Cek', loading: true, loadingLabel: 'Mengecek…'),
        ],
      ),
    );
  }
}
