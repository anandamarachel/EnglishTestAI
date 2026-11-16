import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/core/widgets/lined_paper.dart';
import 'package:english_day/dev/dummy_data.dart';

// ----------------------------------------------------------- Result screen
class WritingResultScreen extends StatefulWidget {
  const WritingResultScreen({
    super.key,
    required this.text,
    this.startLoading = true,
    this.openRuleSheet = false,
    this.autoCopy = false,
  });

  final String text;
  final bool startLoading;
  final bool openRuleSheet;
  final bool autoCopy;

  @override
  State<WritingResultScreen> createState() => _WritingResultScreenState();
}

class _WritingResultScreenState extends State<WritingResultScreen> {
  late bool _loading = widget.startLoading;

  bool get _hasCorrections =>
      widget.text.trim().toLowerCase() == WritingDummy.sampleInput.toLowerCase();

  int get _correctionCount => WritingDummy.tokens.where((t) => t.isWrong).length;

  @override
  void initState() {
    super.initState();
    if (_loading) {
      Future.delayed(const Duration(milliseconds: 1400), () {
        if (mounted) setState(() => _loading = false);
      });
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.openRuleSheet) _showRule(WritingDummy.tokens[2]);
      if (widget.autoCopy) _copy();
    });
  }

  void _copy() {
    Clipboard.setData(ClipboardData(
        text: _hasCorrections ? WritingDummy.correctedText : widget.text));
    showAppSnack(context, 'Teks disalin.');
  }

  void _showRule(CorrectionToken token) {
    final rule = WritingDummy.rules[token.ruleId];
    if (rule == null) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 8, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(rule.title, style: AppText.title.copyWith(fontSize: 18))),
                IconButton(
                  onPressed: () => Navigator.pop(ctx),
                  icon: const Icon(Icons.close, color: AppColors.primary),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 16),
                  Text(rule.explanation, style: AppText.sans(size: 16, height: 1.55)),
                  const SizedBox(height: 20),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: Text(rule.example,
                        style: AppText.serif(size: 17, style: FontStyle.italic)),
                  ),
                  const SizedBox(height: 24),
                  AppButton(label: 'Mengerti', onPressed: () => Navigator.pop(ctx)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Hasil koreksi',
      bottom: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppButton(label: 'Tulis lagi', onPressed: () => Navigator.pop(context, 'rewrite')),
          const SizedBox(height: 8),
          AppButton.secondary(
              label: 'Edit teks ini', onPressed: () => Navigator.pop(context, 'edit')),
        ],
      ),
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 250),
        child: _loading
            ? _buildLoading()
            : _hasCorrections
                ? _buildCorrections()
                : _buildCorrect(),
      ),
    );
  }

  Widget _buildLoading() {
    return ListView(
      key: const ValueKey('loading'),
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        Text('Menyiapkan hasil…', style: AppText.h3),
        const SizedBox(height: 20),
        LinedPaper(
          lineHeight: 84,
          minLines: 2,
          child: LayoutBuilder(
            builder: (_, c) => Column(
              children: [
                for (var i = 0; i < 2; i++) ...[
                  const SkeletonBlock(),
                  const SizedBox(height: 16),
                  const SkeletonBlock(),
                  const SizedBox(height: 16),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: SkeletonBlock(width: c.maxWidth * 0.69),
                  ),
                  const SizedBox(height: 24),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCorrect() {
    return ListView(
      key: const ValueKey('correct'),
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Container(
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.success, width: 1.4),
                ),
                child: const Icon(Icons.check, size: 13, color: AppColors.success),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text('Tidak ada kesalahan. Kalimatmu sudah benar.',
                  style: AppText.sans(
                      size: 18, weight: FontWeight.w600, color: AppColors.success, height: 1.4)),
            ),
          ],
        ),
        const SizedBox(height: 20),
        LinedText(widget.text, minLines: 5),
        const SizedBox(height: 24),
        AppButton.secondary(label: 'Salin teks', onPressed: _copy),
      ],
    );
  }

  Widget _buildCorrections() {
    return ListView(
      key: const ValueKey('corrections'),
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        Text('$_correctionCount bagian perlu diperbaiki', style: AppText.h3),
        const SizedBox(height: 20),
        CorrectionText(tokens: WritingDummy.tokens, onTapCorrection: _showRule),
        const SizedBox(height: 16),
        Text('Ketuk kata yang dicoret untuk memahami koreksinya.', style: AppText.small),
        const SizedBox(height: 28),
        Row(
          children: [
            Expanded(child: Text('Versi benar', style: AppText.h3)),
            IconButton(
              onPressed: _copy,
              tooltip: 'Salin teks',
              icon: const Icon(Icons.copy_outlined, color: AppColors.primary),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(WritingDummy.correctedText,
            style: AppText.serif(size: 18, color: AppColors.primary, height: 1.6)),
      ],
    );
  }
}
