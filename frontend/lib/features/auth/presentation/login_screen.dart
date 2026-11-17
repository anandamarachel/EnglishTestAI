import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/config/app_info.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/auth/presentation/register_screen.dart';
import 'package:english_day/features/dashboard/presentation/dashboard_screen.dart';

// ------------------------------------------------------------------- Login
enum LoginState { idle, loading, error }

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key, this.initialState = LoginState.idle});

  /// Only the design gallery starts in loading/error.
  final LoginState initialState;

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  static const _wrongCredentials = 'Email atau password salah.';

  late LoginState _state = widget.initialState;
  String _error = _wrongCredentials;
  late final _email = TextEditingController(
      text: widget.initialState == LoginState.idle ? '' : 'rina.amelia@sman10gowa.sch.id');
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
    if (_email.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() {
        _state = LoginState.error;
        _error = 'Isi email dan password terlebih dahulu.';
      });
      return;
    }
    setState(() => _state = LoginState.loading);
    try {
      await ref
          .read(sessionControllerProvider.notifier)
          .login(email: _email.text, password: _password.text);
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
        (_) => false,
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _state = LoginState.error;
        // Wrong password and an invalid email format both mean "check what you typed".
        _error = e.code == 'INVALID_CREDENTIALS' || e.code == 'VALIDATION_ERROR'
            ? _wrongCredentials
            : e.userMessage;
      });
    }
  }

  Future<void> _forgotPassword() async {
    final email = _email.text.trim();
    if (!email.contains('@')) {
      showAppSnack(context, 'Isi email kamu dulu, lalu ketuk "Lupa password?".');
      return;
    }
    try {
      await ref
          .read(apiClientProvider)
          .post('/auth/password/forgot', auth: false, data: {'email': email});
      if (mounted) showAppSnack(context, 'Jika email terdaftar, link reset dikirim ke email kamu.');
    } on ApiException catch (e) {
      if (mounted) showAppSnack(context, e.userMessage);
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
                  message: _error,
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
                  onPressed: loading ? null : _forgotPassword,
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
