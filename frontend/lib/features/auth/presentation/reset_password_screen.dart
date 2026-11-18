import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/auth/data/auth_repository.dart';
import 'package:english_day/features/auth/presentation/password_rules.dart';

/// After "Lupa password?": enter the code from the reset email and a new password
/// (`POST /auth/password/reset`). Pops with true when the password was changed.
class ResetPasswordScreen extends ConsumerStatefulWidget {
  const ResetPasswordScreen({super.key, required this.email});

  /// Where the code was sent (shown as a reminder).
  final String email;

  @override
  ConsumerState<ResetPasswordScreen> createState() => _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends ConsumerState<ResetPasswordScreen> {
  final _code = TextEditingController();
  final _new = TextEditingController();
  final _confirm = TextEditingController();
  Map<String, String?> _errors = {};
  bool _saving = false;
  bool _resending = false;

  static const _invalidCode = 'Kode tidak valid atau sudah kedaluwarsa. Minta kode baru.';
  static const _apiErrors = {
    'token': ('code', _invalidCode),
    'new_password': ('new', passwordRuleMessage),
    'password_confirmation': ('confirm', 'Konfirmasi password tidak sama.'),
  };

  @override
  void dispose() {
    for (final c in [_code, _new, _confirm]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    final errors = {
      'code': _code.text.trim().isEmpty ? 'Tempel kode dari email.' : null,
      'new': newPasswordError(_new.text),
      'confirm': confirmationError(_confirm.text, _new.text),
    };
    setState(() => _errors = errors);
    if (errors.values.any((e) => e != null)) return;
    setState(() => _saving = true);
    try {
      await ref.read(authRepositoryProvider).resetPassword(
            token: _code.text,
            newPassword: _new.text,
            passwordConfirmation: _confirm.text,
          );
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _errors = {
          ..._errors,
          if (e.code == 'INVALID_RESET_TOKEN') 'code': _invalidCode,
          for (final d in e.details)
            if (_apiErrors[d.field] case (final field, final message)) field: message,
        };
      });
      if (e.details.isEmpty && e.code != 'INVALID_RESET_TOKEN') showAppSnack(context, e.userMessage);
    }
  }

  Future<void> _resend() async {
    setState(() => _resending = true);
    try {
      await ref.read(authRepositoryProvider).forgotPassword(widget.email);
      if (mounted) showAppSnack(context, 'Kode baru dikirim ke ${widget.email}.');
    } on ApiException catch (e) {
      if (mounted) showAppSnack(context, e.userMessage);
    } finally {
      if (mounted) setState(() => _resending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Reset password',
      bottom: AppButton(
        label: 'Simpan password',
        loading: _saving,
        loadingLabel: 'Menyimpan…',
        onPressed: _save,
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text('Jika ${widget.email} terdaftar, kode reset sudah dikirim ke email itu. '
              'Salin kodenya, lalu buat password baru.',
              style: AppText.body),
          const SizedBox(height: 20),
          AppTextField(
            label: 'Kode reset',
            hint: 'Tempel kode dari email',
            controller: _code,
            enabled: !_saving,
            errorText: _errors['code'],
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
          const SizedBox(height: 16),
          Align(
            alignment: Alignment.centerLeft,
            child: AppTextAction(
              label: 'Kirim ulang kode',
              onPressed: _resending || _saving ? null : _resend,
            ),
          ),
        ],
      ),
    );
  }
}
