import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/auth/application/session_controller.dart';

/// "Ubah nama" (`PATCH /users/me`). Built from the Register form's components.
class EditNameScreen extends ConsumerStatefulWidget {
  const EditNameScreen({super.key});

  @override
  ConsumerState<EditNameScreen> createState() => _EditNameScreenState();
}

class _EditNameScreenState extends ConsumerState<EditNameScreen> {
  late final _name = TextEditingController(text: ref.read(currentUserProvider)?.displayName);
  String? _error;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    final name = _name.text.trim();
    final error = name.isEmpty
        ? 'Nama lengkap wajib diisi.'
        : name.length > 100
            ? 'Nama maksimal 100 karakter.'
            : null;
    setState(() => _error = error);
    if (error != null) return;
    if (name == ref.read(currentUserProvider)?.displayName) {
      Navigator.pop(context);
      return;
    }
    setState(() => _saving = true);
    try {
      await ref.read(sessionControllerProvider.notifier).updateDisplayName(name);
      if (!mounted) return;
      showAppSnack(context, 'Nama disimpan.');
      Navigator.pop(context);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        if (e.details.any((d) => d.field == 'display_name')) _error = 'Nama lengkap belum sesuai.';
      });
      if (e.details.isEmpty && !e.isSessionEnded) showAppSnack(context, e.userMessage);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Ubah nama',
      bottom: AppButton(
        label: 'Simpan',
        loading: _saving,
        loadingLabel: 'Menyimpan…',
        onPressed: _save,
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          AppTextField(
            label: 'Nama lengkap',
            hint: 'Nama lengkap kamu',
            controller: _name,
            errorText: _error,
            enabled: !_saving,
          ),
          const SizedBox(height: 12),
          Text('Nama ini dipakai di dashboard dan saat AI menyapamu.', style: AppText.small),
        ],
      ),
    );
  }
}
