import 'dart:async';

import 'package:flutter/material.dart';

import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/speaking/presentation/speaking_screen.dart';

// ------------------------------------------------------- Izin mikrofon
class MicPermissionScreen extends StatelessWidget {
  const MicPermissionScreen({super.key, this.permanentlyDenied = false});
  final bool permanentlyDenied;

  void _goSpeaking(BuildContext context) => Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const SpeakingScreen()),
      );

  @override
  Widget build(BuildContext context) {
    if (permanentlyDenied) {
      return AppScaffold(
        title: 'Speaking',
        bottom: AppButton(
          label: 'Buka pengaturan',
          onPressed: () {
            showAppSnack(context, 'Membuka pengaturan (dummy)…');
            Future.delayed(const Duration(milliseconds: 900), () {
              if (context.mounted) _goSpeaking(context);
            });
          },
        ),
        body: const InfoStateView(
          icon: Icons.mic_off_outlined,
          title: 'Akses mikrofon dimatikan',
          message: 'Speaking butuh akses mikrofon. Buka pengaturan untuk mengizinkannya.',
        ),
      );
    }
    return AppScaffold(
      title: 'Speaking',
      bottom: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppButton(label: 'Izinkan mikrofon', onPressed: () => _goSpeaking(context)),
          const SizedBox(height: 8),
          AppTextAction(label: 'Nanti saja', onPressed: () => Navigator.maybePop(context)),
        ],
      ),
      body: const InfoStateView(
        icon: Icons.mic_none_rounded,
        title: 'Izinkan mikrofon untuk latihan Speaking',
        message: 'Suaramu hanya dipakai untuk mengubah ucapan menjadi teks selama latihan.',
      ),
    );
  }
}
