import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/speaking/application/voice_io.dart';
import 'package:english_day/features/speaking/presentation/speaking_screen.dart';

// ------------------------------------------------------- Izin mikrofon
/// Asks for microphone access before Speaking (the system dialog appears on tap).
class MicPermissionScreen extends ConsumerStatefulWidget {
  const MicPermissionScreen({super.key, this.permanentlyDenied = false});

  /// Start in the "access turned off" state (after a refusal, or in the gallery).
  final bool permanentlyDenied;

  @override
  ConsumerState<MicPermissionScreen> createState() => _MicPermissionScreenState();
}

class _MicPermissionScreenState extends ConsumerState<MicPermissionScreen> {
  late bool _denied = widget.permanentlyDenied;
  bool _asking = false;

  Future<bool> _askPermission() async {
    final recorder = ref.read(voiceRecorderFactoryProvider)();
    try {
      return await recorder.hasPermission();
    } catch (_) {
      return false;
    } finally {
      recorder.dispose();
    }
  }

  Future<void> _allow() async {
    setState(() => _asking = true);
    final granted = await _askPermission();
    if (!mounted) return;
    setState(() => _asking = false);
    if (granted) {
      Navigator.of(context)
          .pushReplacement(MaterialPageRoute(builder: (_) => const SpeakingScreen()));
    } else if (_denied) {
      // Android/iOS no longer show the dialog after a refusal: only Settings can allow it.
      showAppSnack(context,
          'Izinkan mikrofon untuk English Day di Pengaturan HP (Aplikasi → Izin), lalu coba lagi.');
    } else {
      setState(() => _denied = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_denied) {
      return AppScaffold(
        title: 'Speaking',
        bottom: AppButton(
          label: 'Buka pengaturan',
          loading: _asking,
          onPressed: _allow,
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
          AppButton(label: 'Izinkan mikrofon', loading: _asking, onPressed: _allow),
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
