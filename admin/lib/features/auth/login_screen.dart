import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day_admin/core/app_info.dart';
import 'package:english_day_admin/core/theme/admin_theme.dart';
import 'package:english_day_admin/core/widgets/admin_shell.dart';
import 'package:english_day_admin/data/admin_repository.dart';
import 'package:english_day_admin/data/demo_admin_repository.dart';
import 'package:english_day_admin/data/providers.dart';

/// Admin sign-in. On success the router moves on to the dashboard (or the page
/// that was requested before signing in).
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  String? _error;
  String? _emailError;
  String? _passwordError;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _email.text.trim();
    setState(() {
      _error = null;
      _emailError = email.isEmpty
          ? 'Enter your email address.'
          : RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)
              ? null
              : 'Enter a valid email address.';
      _passwordError = _password.text.isEmpty ? 'Enter your password.' : null;
    });
    if (_emailError != null || _passwordError != null) return;
    setState(() => _loading = true);
    try {
      await ref.read(adminSessionProvider.notifier).login(email: email, password: _password.text);
    } on InvalidCredentialsException {
      if (mounted) setState(() => _error = 'Incorrect email or password.');
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not sign in. Please try again.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: AdminColors.surface,
        body: LayoutBuilder(builder: (context, c) {
          final wide = c.maxWidth >= 900;
          return Row(
            children: [
              if (wide) const Expanded(flex: 11, child: _BrandPanel()),
              Expanded(
                flex: 9,
                child: Center(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(32),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 400),
                      child: _buildForm(wide),
                    ),
                  ),
                ),
              ),
            ],
          );
        }),
      );

  Widget _buildForm(bool wide) => AutofillGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (!wide) ...[const AppLogo(), const SizedBox(height: 36)],
            Text('Welcome back', style: AdminText.headline(size: 30)),
            const SizedBox(height: 6),
            Text('Sign in to access the school administration dashboard.',
                style: AdminText.body(color: AdminColors.textSecondary)),
            const SizedBox(height: 28),
            if (_error != null) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AdminColors.dangerSoft,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(children: [
                  const Icon(Icons.error_outline_rounded, color: AdminColors.danger, size: 20),
                  const SizedBox(width: 10),
                  Expanded(child: Text(_error!, style: AdminText.body(color: AdminColors.danger))),
                ]),
              ),
              const SizedBox(height: 20),
            ],
            Text('SCHOOL EMAIL ADDRESS', style: AdminText.caps),
            const SizedBox(height: 8),
            TextField(
              controller: _email,
              enabled: !_loading,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              textInputAction: TextInputAction.next,
              decoration: InputDecoration(
                hintText: 'admin@sman10gowa.sch.id',
                prefixIcon: const Icon(Icons.alternate_email_rounded, size: 20),
                errorText: _emailError,
              ),
            ),
            const SizedBox(height: 18),
            Text('PASSWORD', style: AdminText.caps),
            const SizedBox(height: 8),
            TextField(
              controller: _password,
              enabled: !_loading,
              obscureText: _obscure,
              autofillHints: const [AutofillHints.password],
              onSubmitted: (_) => _submit(),
              decoration: InputDecoration(
                hintText: 'Enter your password',
                prefixIcon: const Icon(Icons.lock_outline_rounded, size: 20),
                errorText: _passwordError,
                suffixIcon: IconButton(
                  tooltip: _obscure ? 'Show password' : 'Hide password',
                  onPressed: () => setState(() => _obscure = !_obscure),
                  icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                      size: 20),
                ),
              ),
            ),
            const SizedBox(height: 26),
            FilledButton(
              onPressed: _loading ? null : _submit,
              child: _loading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text('Sign in to Admin Portal'),
                        SizedBox(width: 8),
                        Icon(Icons.arrow_forward_rounded, size: 18),
                      ],
                    ),
            ),
            const SizedBox(height: 22),
            Text(
              'Restricted access. This portal is only for authorized school staff.',
              textAlign: TextAlign.center,
              style: AdminText.small,
            ),
            if (kDebugMode) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AdminColors.warningSoft,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  'Demo (debug only): ${DemoAdminRepository.demoEmail} / ${DemoAdminRepository.demoPassword}',
                  textAlign: TextAlign.center,
                  style: AdminText.small.copyWith(color: AdminColors.warning),
                ),
              ),
            ],
          ],
        ),
      );
}

class _BrandPanel extends StatelessWidget {
  const _BrandPanel();

  @override
  Widget build(BuildContext context) => Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AdminColors.tertiary, AdminColors.primary],
          ),
        ),
        padding: const EdgeInsets.all(48),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const AppLogo(onDark: true),
            const Spacer(),
            Text('Empowering Better',
                style: AdminText.headline(size: 40, color: Colors.white, height: 1.15)),
            Text('English Learning',
                style: AdminText.headline(size: 40, color: const Color(0xFF93C5FD), height: 1.15)),
            const SizedBox(height: 18),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Text(
                'Monitor student activity across Writing, Reading, Speaking and Listening, '
                'with every exercise evaluated automatically by AI.',
                style: AdminText.body(size: 16, color: Colors.white70, height: 1.55),
              ),
            ),
            const Spacer(),
            Text('${AppInfo.school}  •  Academic Year ${AppInfo.academicYear}',
                style: AdminText.small.copyWith(color: Colors.white60)),
          ],
        ),
      );
}
