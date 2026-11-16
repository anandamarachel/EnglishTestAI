import 'dart:async';

import 'package:flutter/material.dart';

import 'package:english_day/core/config/app_info.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/auth/presentation/register_screen.dart';
import 'package:english_day/features/dashboard/presentation/dashboard_screen.dart';

// ------------------------------------------------------------------- Login
enum LoginState { idle, loading, error }

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.initialState = LoginState.idle});
  final LoginState initialState;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late LoginState _state = widget.initialState;
  late final _email = TextEditingController(
      text: widget.initialState == LoginState.idle ? '' : DummyUser.email);
  late final _password = TextEditingController(
      text: widget.initialState == LoginState.idle ? '' : 'salah123');

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    setState(() => _state = LoginState.loading);
    await Future.delayed(const Duration(milliseconds: 1500));
    if (!mounted) return;
    // Dummy auth: email valid + password minimal 8 karakter dan bukan "salah123".
    final ok = _email.text.contains('@') &&
        _password.text.length >= 8 &&
        _password.text != 'salah123';
    if (ok) {
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
        (_) => false,
      );
    } else {
      setState(() => _state = LoginState.error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final loading = _state == LoginState.loading;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 40, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(AppInfo.tagline,
                  style: AppText.sans(size: 14, weight: FontWeight.w600, color: AppColors.primary)),
              const SizedBox(height: 28),
              Text('Masuk', style: AppText.h1),
              const SizedBox(height: 8),
              Text('Lanjutkan latihan bahasa Inggrismu.', style: AppText.body.copyWith(fontSize: 17)),
              const SizedBox(height: 24),
              if (_state == LoginState.error) ...[
                StatusBanner(
                  type: BannerType.error,
                  message: 'Email atau password salah.',
                  actionLabel: 'Coba lagi',
                  onAction: () => setState(() {
                    _state = LoginState.idle;
                    _password.clear();
                  }),
                ),
                const SizedBox(height: 24),
              ],
              AppTextField(
                label: 'Email',
                hint: 'nama@email.com',
                controller: _email,
                enabled: !loading,
                keyboardType: TextInputType.emailAddress,
              ),
              const SizedBox(height: 20),
              AppTextField(
                label: 'Password',
                hint: 'Masukkan password',
                controller: _password,
                enabled: !loading,
                obscure: true,
              ),
              const SizedBox(height: 16),
              Align(
                alignment: Alignment.centerRight,
                child: AppTextAction(
                  label: 'Lupa password?',
                  onPressed: () => showAppSnack(context, 'Link reset dikirim ke email kamu.'),
                ),
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: BottomActionBar(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AppButton(
              label: 'Masuk',
              loading: loading,
              loadingLabel: 'Masuk…',
              onPressed: _submit,
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text('Belum punya akun? ',
                    style: AppText.sans(size: 15, color: AppColors.textSecondary)),
                AppTextAction(
                  label: 'Daftar',
                  onPressed: () => Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => const RegisterScreen())),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
