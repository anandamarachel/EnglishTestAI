import 'dart:async';

import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/core/widgets/lined_paper.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/writing/presentation/writing_result_screen.dart';

enum WritingState { idle, loading, slow, error }

// ------------------------------------------------------------ Input screen
class WritingInputScreen extends StatefulWidget {
  const WritingInputScreen({
    super.key,
    this.initialText = '',
    this.initialState = WritingState.idle,
  });

  final String initialText;
  final WritingState initialState;

  @override
  State<WritingInputScreen> createState() => _WritingInputScreenState();
}

class _WritingInputScreenState extends State<WritingInputScreen> {
  late final _controller = TextEditingController(text: widget.initialText);
  late WritingState _state = widget.initialState;
  Timer? _slowTimer;
  Timer? _doneTimer;

  @override
  void initState() {
    super.initState();
    _controller.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    _doneTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  int get _count => _controller.text.length;
  bool get _overLimit => _count > WritingDummy.maxChars;
  bool get _busy => _state == WritingState.loading || _state == WritingState.slow;

  void _check() {
    FocusScope.of(context).unfocus();
    setState(() => _state = WritingState.loading);
    // Simulasi: banner "masih memproses" muncul setelah 10 detik,
    // respons dummy datang setelah 2.5 detik.
    _slowTimer = Timer(const Duration(seconds: 10), () {
      if (mounted) setState(() => _state = WritingState.slow);
    });
    _doneTimer = Timer(const Duration(milliseconds: 2500), _openResult);
  }

  void _cancel() {
    _slowTimer?.cancel();
    _doneTimer?.cancel();
    setState(() => _state = WritingState.idle);
  }

  Future<void> _openResult() async {
    _slowTimer?.cancel();
    if (!mounted) return;
    setState(() => _state = WritingState.idle);
    final action = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => WritingResultScreen(text: _controller.text)),
    );
    if (action == 'rewrite') _controller.clear();
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Writing',
      bottom: AppButton(
        label: 'Cek grammar',
        loading: _busy,
        loadingLabel: 'Mengecek…',
        onPressed: _controller.text.trim().isEmpty || _overLimit ? null : _check,
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          if (_state == WritingState.slow) ...[
            StatusBanner.slow(onAction: _cancel),
            const SizedBox(height: 24),
          ],
          if (_state == WritingState.error) ...[
            StatusBanner.timeout(onAction: _check),
            const SizedBox(height: 24),
          ],
          Text('Tulis kalimat atau paragraf pendek dalam bahasa Inggris.',
              style: AppText.sans(size: 16, height: 1.55)),
          const SizedBox(height: 20),
          LinedPaper(
            height: _state == WritingState.idle && !_overLimit ? 364 : 252,
            child: TextField(
              controller: _controller,
              enabled: !_busy,
              maxLines: null,
              expands: true,
              textAlignVertical: TextAlignVertical.top,
              style: AppText.serif(size: 18, color: AppColors.primary, height: 28 / 18),
              decoration: InputDecoration(
                isCollapsed: true,
                border: InputBorder.none,
                hintText: 'Contoh: Yesterday I go to school with my friend.',
                hintStyle: AppText.serif(
                    size: 18, color: AppColors.textSecondary, height: 28 / 18),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: Text(
              '$_count/${WritingDummy.maxChars}',
              style: AppText.sans(
                size: 13,
                color: _overLimit ? AppColors.error : AppColors.textSecondary,
              ),
            ),
          ),
          if (_overLimit) ...[
            const SizedBox(height: 4),
            FieldError('Kurangi ${_count - WritingDummy.maxChars} karakter agar bisa dicek.'),
          ],
          if (_busy) ...[
            const SizedBox(height: 16),
            Text('Teks kamu tersimpan. Tunggu sampai pemeriksaan selesai.', style: AppText.small),
          ],
        ],
      ),
    );
  }
}
