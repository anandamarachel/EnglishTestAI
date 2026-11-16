import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';

// --------------------------------------------------- Komponen: tombol
class ButtonsShowcaseScreen extends StatelessWidget {
  const ButtonsShowcaseScreen({super.key});

  @override
  Widget build(BuildContext context) {
    Widget caption(String t) => Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 8),
          child: Text(t, style: AppText.caption),
        );
    return AppScaffold(
      title: 'Komponen',
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text('Tombol & aksi', style: AppText.h2),
          caption('Normal · utama'),
          AppButton(label: 'Cek grammar', onPressed: () {}),
          caption('Ditekan · utama'),
          Container(
            height: 52,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.primaryPressed,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text('Cek grammar',
                style: AppText.sans(size: 15, weight: FontWeight.w600, color: Colors.white)),
          ),
          caption('Nonaktif · utama'),
          const AppButton(label: 'Cek grammar'),
          caption('Memuat · utama'),
          const AppButton(label: 'Cek grammar', loading: true, loadingLabel: 'Mengecek…'),
          caption('Sekunder'),
          AppButton.secondary(label: 'Edit teks ini', onPressed: () {}),
          caption('Aksi teks · target 48 dp'),
          Center(child: AppTextAction(label: 'Nanti saja', onPressed: () {})),
        ],
      ),
    );
  }
}
