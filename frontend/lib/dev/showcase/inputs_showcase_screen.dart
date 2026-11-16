import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';

// --------------------------------------------- Komponen: input & pilihan
class InputsShowcaseScreen extends StatefulWidget {
  const InputsShowcaseScreen({super.key});

  @override
  State<InputsShowcaseScreen> createState() => _InputsShowcaseScreenState();
}

class _InputsShowcaseScreenState extends State<InputsShowcaseScreen> {
  String _role = 'Guru';
  final _focus = TextEditingController(text: 'Rina Amelia');
  final _err = TextEditingController(text: '123456');
  final _dis = TextEditingController(text: 'Rina Amelia');

  @override
  void dispose() {
    _focus.dispose();
    _err.dispose();
    _dis.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Komponen',
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          const AppTextField(label: 'Normal', hint: 'Tulis nama kamu'),
          const SizedBox(height: 16),
          AppTextField(label: 'Fokus', controller: _focus),
          const SizedBox(height: 16),
          AppTextField(
            label: 'Kesalahan',
            controller: _err,
            obscure: true,
            errorText: 'Password minimal 8 karakter.',
          ),
          const SizedBox(height: 16),
          AppTextField(label: 'Nonaktif saat diproses', controller: _dis, enabled: false),
          const SizedBox(height: 20),
          Text('Pilihan · normal dan terpilih', style: AppText.caption),
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
          const SizedBox(height: 20),
          Text('Ikon · target 48 dp, visual 24 dp', style: AppText.caption),
          const SizedBox(height: 4),
          Row(
            children: [
              IconButton(
                  onPressed: () {}, icon: const Icon(Icons.arrow_back, color: AppColors.primary)),
              IconButton(
                  onPressed: () {},
                  icon: const Icon(Icons.visibility_outlined, color: AppColors.primary)),
              IconButton(
                  onPressed: () {},
                  icon: const Icon(Icons.copy_outlined, color: AppColors.primary)),
            ],
          ),
        ],
      ),
    );
  }
}
