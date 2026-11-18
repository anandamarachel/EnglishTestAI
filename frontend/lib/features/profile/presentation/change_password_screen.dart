import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/auth/presentation/login_screen.dart';
import 'package:english_day/features/auth/presentation/password_rules.dart';

/// "Ubah password" (`POST /auth/password/change`). The server then signs out every
/// device, so this ends on the login screen.
class ChangePasswordScreen extends ConsumerStatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  ConsumerState<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends ConsumerState<ChangePasswordScreen> {
  final _current = TextEditingController();
  final _new = TextEditingController();
  final _confirm = TextEditingController();
  Map<String, String?> _errors = {};
  bool _saving = false;

  /// Backend field -> form field and message.
  static const _apiErrors = {
    'current_password': ('current', 'Password sekarang salah.'),
    'new_password': ('new', passwordRuleMessage),
    'password_confirmation': ('confirm', 'Konfirmasi password tidak sama.'),
  };

  @override
  void dispose() {
    for (final c in [_current, _new, _confirm]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    final errors = {
      'current': _current.text.isEmpty ? 'Isi password kamu sekarang.' : null,
      'new': newPasswordError(_new.text),
      'confirm': confirmationError(_confirm.text, _new.text),
    };
    setState(() => _errors = errors);
    if (errors.values.any((e) => e != null)) return;
    setState(() => _saving = true);
    final navigator = Navigator.of(context);
    try {
      await ref.read(sessionControllerProvider.notifier).changePassword(
            currentPassword: _current.text,
            newPassword: _new.text,
            passwordConfirmation: _confirm.text,
          );
      if (!mounted) return;
      showAppSnack(context, 'Password diubah. Masuk lagi dengan password baru.');
      navigator.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
        (_) => false,
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _errors = {
          ..._errors,
          for (final d in e.details)
            if (_apiErrors[d.field] case (final field, final message)) field: message,
        };
      });
      if (e.details.isEmpty && !e.isSessionEnded) showAppSnack(context, e.userMessage);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Ubah password',
      bottom: AppButton(
        label: 'Simpan password',
        loading: _saving,
        loadingLabel: 'Menyimpan…',
        onPressed: _save,
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          AppTextField(
            label: 'Password sekarang',
            hint: 'Masukkan password sekarang',
            controller: _current,
            obscure: true,
            enabled: !_saving,
            errorText: _errors['current'],
          ),
          const SizedBox(height: 16),
          AppTextField(
            label: 'Password baru',
            hint: 'Minimal 8 karakter',
            controller: _new,
            obscure: true,
            enabled: !_saving,
            errorText: _errors['new'],
          ),
          const SizedBox(height: 16),
          AppTextField(
            label: 'Konfirmasi password baru',
            hint: 'Ulangi password baru',
            controller: _confirm,
            obscure: true,
            enabled: !_saving,
            errorText: _errors['confirm'],
          ),
          const SizedBox(height: 12),
          Text('Setelah diganti, kamu keluar dari semua perangkat dan perlu masuk lagi.',
              style: AppText.small),
        ],
      ),
    );
  }
}
