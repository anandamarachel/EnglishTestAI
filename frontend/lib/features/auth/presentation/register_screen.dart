import 'dart:async';

import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/dashboard/presentation/dashboard_screen.dart';

// ---------------------------------------------------------------- Register
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key, this.showErrors = false});
  final bool showErrors;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _name = TextEditingController();
  late final _email = TextEditingController(text: widget.showErrors ? 'rina.amelia@' : '');
  late final _password = TextEditingController(text: widget.showErrors ? '123456' : '');
  late final _confirm = TextEditingController(text: widget.showErrors ? '123456789' : '');
  String _role = 'Siswa';
  bool _loading = false;
  Map<String, String?> _errors = {};

  @override
  void initState() {
    super.initState();
    if (widget.showErrors) _errors = _validate();
  }

  @override
  void dispose() {
    for (final c in [_name, _email, _password, _confirm]) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, String?> _validate() {
    final emailOk = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(_email.text);
    return {
      'name': _name.text.trim().isEmpty ? 'Nama lengkap wajib diisi.' : null,
      'email': emailOk ? null : 'Masukkan email yang valid.',
      'password': _password.text.length < 8 ? 'Password minimal 8 karakter.' : null,
      'confirm': _confirm.text != _password.text || _confirm.text.isEmpty
          ? 'Konfirmasi password tidak sama.'
          : null,
    };
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    final errors = _validate();
    setState(() => _errors = errors);
    if (errors.values.any((e) => e != null)) return;
    setState(() => _loading = true);
    await Future.delayed(const Duration(milliseconds: 1200));
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const DashboardScreen(hasProgress: false)),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Buat akun',
      bottom: AppButton(
        label: 'Daftar',
        loading: _loading,
        loadingLabel: 'Mendaftar…',
        onPressed: _submit,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AppTextField(
              label: 'Nama lengkap',
              hint: 'Nama lengkap kamu',
              controller: _name,
              errorText: _errors['name'],
            ),
            const SizedBox(height: 16),
            AppTextField(
              label: 'Email',
              hint: 'nama@email.com',
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              errorText: _errors['email'],
            ),
            const SizedBox(height: 16),
            AppTextField(
              label: 'Password',
              hint: 'Masukkan password',
              controller: _password,
              obscure: true,
              errorText: _errors['password'],
            ),
            const SizedBox(height: 16),
            AppTextField(
              label: 'Konfirmasi password',
              hint: 'Ulangi password',
              controller: _confirm,
              obscure: true,
              errorText: _errors['confirm'],
            ),
            const SizedBox(height: 16),
            Text('Kamu sebagai', style: AppText.label),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                for (final r in ['Siswa', 'Guru'])
                  AppChoiceChip(
                    label: r,
                    selected: _role == r,
                    onTap: () => setState(() => _role = r),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
