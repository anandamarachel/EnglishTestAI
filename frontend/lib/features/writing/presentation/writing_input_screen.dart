import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_exception.dart' show ApiException;
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/core/widgets/lined_paper.dart';
import 'package:english_day/features/writing/application/writing_session.dart';
import 'package:english_day/features/writing/data/writing_repository.dart';
import 'package:english_day/features/writing/data/writing_result.dart';
import 'package:english_day/features/writing/presentation/writing_result_screen.dart';

enum WritingState { idle, loading, slow, error }

// ------------------------------------------------------------ Input screen
class WritingInputScreen extends ConsumerStatefulWidget {
  const WritingInputScreen({
    super.key,
    this.resumeAttemptId,
    this.initialText = '',
    this.initialState = WritingState.idle,
  });

  /// Continue this saved attempt (dashboard "Lanjutkan").
  final String? resumeAttemptId;

  /// Only the design gallery starts with text or in loading/slow/error.
  final String initialText;
  final WritingState initialState;

  @override
  ConsumerState<WritingInputScreen> createState() => _WritingInputScreenState();
}

class _WritingInputScreenState extends ConsumerState<WritingInputScreen> {
  static const _slowAfter = Duration(seconds: 10);

  late final _controller = TextEditingController(text: widget.initialText);
  late WritingState _state = widget.initialState;
  late final _session = WritingSession(ref.read(writingRepositoryProvider));
  bool _restoring = false;
  int _run = 0; // ignores results of a check that was cancelled
  Timer? _slowTimer;

  @override
  void initState() {
    super.initState();
    _controller.addListener(() => setState(() {}));
    final resumeId = widget.resumeAttemptId;
    if (resumeId != null) _restore(resumeId);
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  int get _count => _controller.text.length;
  bool get _overLimit => _count > writingMaxChars;
  bool get _busy => _state == WritingState.loading || _state == WritingState.slow;

  Future<void> _restore(String attemptId) async {
    setState(() => _restoring = true);
    try {
      final attempt = await ref.read(writingRepositoryProvider).attempt(attemptId);
      if (!mounted) return;
      _controller.text = attempt.text;
      _session.resumeFrom(attempt);
      setState(() => _restoring = false);
      final result = attempt.result;
      if (result != null) {
        _openResult(result);
      } else if (attempt.isEvaluating) {
        _check();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _restoring = false);
      showAppSnack(context,
          e is ApiException ? e.userMessage : 'Latihan sebelumnya tidak bisa dibuka.');
    }
  }

  Future<void> _check() async {
    FocusScope.of(context).unfocus();
    final run = ++_run;
    setState(() => _state = WritingState.loading);
    _slowTimer?.cancel();
    _slowTimer = Timer(_slowAfter, () {
      if (mounted && _state == WritingState.loading) setState(() => _state = WritingState.slow);
    });
    try {
      final result = await _session.check(_controller.text);
      if (!mounted || run != _run) return;
      _slowTimer?.cancel();
      setState(() => _state = WritingState.idle);
      _openResult(result);
    } on OperationCancelledException {
      return;
    } catch (e) {
      if (!mounted || run != _run) return;
      _slowTimer?.cancel();
      _showError(e);
    }
  }

  void _showError(Object error) {
    if (error is ApiException) {
      final aiBusy = error.retryable && error.code != ApiException.network;
      if (!aiBusy) {
        // Session ended: the app-wide sheet takes over. Otherwise explain in a snack.
        setState(() => _state = WritingState.idle);
        if (!error.isSessionEnded) showAppSnack(context, error.userMessage);
        return;
      }
    }
    // AI failed, timed out or the server is busy: the design's "AI belum merespons".
    setState(() => _state = WritingState.error);
  }

  void _cancel() {
    _run++;
    _slowTimer?.cancel();
    _session.cancel();
    setState(() => _state = WritingState.idle);
  }

  Future<void> _openResult(WritingResult result) async {
    final action = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => WritingResultScreen(result: result)),
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
        onPressed:
            _controller.text.trim().isEmpty || _overLimit || _restoring ? null : _check,
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
              enabled: !_busy && !_restoring,
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
              '$_count/$writingMaxChars',
              style: AppText.sans(
                size: 13,
                color: _overLimit ? AppColors.error : AppColors.textSecondary,
              ),
            ),
          ),
          if (_overLimit) ...[
            const SizedBox(height: 4),
            FieldError('Kurangi ${_count - writingMaxChars} karakter agar bisa dicek.'),
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
