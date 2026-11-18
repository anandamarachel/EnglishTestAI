import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/answer_widgets.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/speaking/application/speaking_session.dart';
import 'package:english_day/features/speaking/application/voice_io.dart';
import 'package:english_day/features/speaking/data/speaking_repository.dart';
import 'package:english_day/features/speaking/presentation/mic_permission_screen.dart';
import 'package:english_day/features/speaking/presentation/speaking_result_screen.dart';

// ---------------------------------------------------------- Percakapan
enum SpeakingState { idle, recording, processing, aiSpeaking, slow, error }

/// A spoken conversation with an AI persona: record a turn, the AI transcribes it
/// and answers with text and voice.
class SpeakingScreen extends ConsumerStatefulWidget {
  const SpeakingScreen({super.key, this.practice, this.resumeAttemptId, this.initialState});

  /// Default: a new [SpeakingSession] against the backend. The gallery passes a demo.
  final SpeakingPractice? practice;

  /// Continue this saved conversation (dashboard "Lanjutkan").
  final String? resumeAttemptId;

  /// Gallery only: start in this state.
  final SpeakingState? initialState;

  @override
  ConsumerState<SpeakingScreen> createState() => _SpeakingScreenState();
}

class _SpeakingScreenState extends ConsumerState<SpeakingScreen> {
  static const _slowAfter = Duration(seconds: 10);

  /// The backend accepts up to 2 minutes per turn; stop a bit before.
  static const _maxRecording = Duration(seconds: 110);

  late final SpeakingPractice _practice = widget.practice ??
      SpeakingSession(
        ref.read(speakingRepositoryProvider),
        ref.read(voiceRecorderFactoryProvider)(),
        ref.read(voicePlayerFactoryProvider)(),
        resumeAttemptId: widget.resumeAttemptId,
      );
  late SpeakingState _state = widget.initialState ??
      (_practice.started ? SpeakingState.idle : SpeakingState.processing);
  bool _startFailed = false;
  bool _ending = false;
  int? _speakingIndex;
  Timer? _slowTimer;
  Timer? _limitTimer;
  final _scroll = ScrollController();

  List<SpeakingMessage> get _messages => _practice.messages;

  @override
  void initState() {
    super.initState();
    _practice.onChange = () {
      if (mounted) setState(() {});
    };
    if (_state == SpeakingState.aiSpeaking) _speakingIndex = _messages.length - 1;
    if (!_practice.started && widget.initialState == null) _start();
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    _limitTimer?.cancel();
    _practice.onChange = null;
    _practice.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _waitWithSlowBanner() {
    _slowTimer?.cancel();
    _slowTimer = Timer(_slowAfter, () {
      if (mounted && _state == SpeakingState.processing) {
        setState(() => _state = SpeakingState.slow);
      }
    });
  }

  Future<void> _start() async {
    setState(() {
      _state = SpeakingState.processing;
      _startFailed = false;
    });
    _waitWithSlowBanner();
    try {
      await _practice.start();
      if (!mounted) return;
      _slowTimer?.cancel();
      setState(() => _state = SpeakingState.idle);
      _scrollDown();
      // A new conversation: let the AI say its greeting.
      if (_messages.length == 1 && _messages.first.fromAi) _playAi(0);
    } on OperationCancelledException {
      return;
    } catch (e) {
      if (!mounted) return;
      _slowTimer?.cancel();
      setState(() {
        _state = SpeakingState.idle;
        _startFailed = !(e is ApiException && e.isSessionEnded);
      });
    }
  }

  Future<void> _startRecording() async {
    if (!_practice.started) return;
    try {
      await _practice.startRecording();
    } on MicPermissionDeniedException {
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) => const MicPermissionScreen(permanentlyDenied: true)));
      return;
    } catch (_) {
      if (mounted) showAppSnack(context, 'Mikrofon tidak bisa dipakai. Coba lagi.');
      return;
    }
    if (!mounted) return;
    setState(() => _state = SpeakingState.recording);
    _limitTimer?.cancel();
    _limitTimer = Timer(_maxRecording, _stopRecording);
  }

  Future<void> _stopRecording() async {
    _limitTimer?.cancel();
    if (_state != SpeakingState.recording) return;
    setState(() => _state = SpeakingState.processing);
    _waitWithSlowBanner();
    try {
      final reply = await _practice.stopAndSend();
      if (!mounted) return;
      _slowTimer?.cancel();
      setState(() => _state = SpeakingState.idle);
      _scrollDown();
      if (reply != null) _playAi(_messages.indexOf(reply));
    } on OperationCancelledException {
      return;
    } on NoSpeechException {
      if (!mounted) return;
      _slowTimer?.cancel();
      setState(() => _state = SpeakingState.error);
    } catch (e) {
      if (!mounted) return;
      _slowTimer?.cancel();
      setState(() => _state = SpeakingState.idle);
      if (e is ApiException && e.isSessionEnded) return;
      showAppSnack(
          context,
          e is ApiException && e.code == ApiException.network
              ? e.userMessage
              : 'AI belum merespons. Coba bicara lagi.');
    }
  }

  void _cancelTurn() {
    _slowTimer?.cancel();
    _practice.cancelTurn();
    setState(() => _state = SpeakingState.idle);
  }

  Future<void> _playAi(int index) async {
    if (index < 0) return;
    setState(() {
      _state = SpeakingState.aiSpeaking;
      _speakingIndex = index;
    });
    try {
      await _practice.play(_messages[index]);
    } catch (_) {
      // Audio could not be loaded or played (e.g. browser autoplay rules): the text is shown.
    }
    if (mounted && _state == SpeakingState.aiSpeaking && _speakingIndex == index) {
      setState(() {
        _state = SpeakingState.idle;
        _speakingIndex = null;
      });
    }
  }

  Future<void> _end() async {
    if (_ending) return;
    _ending = true;
    _limitTimer?.cancel();
    if (_state == SpeakingState.recording) await _practice.cancelRecording();
    var evaluated = false;
    try {
      evaluated = await _practice.finish();
    } catch (_) {
      // The conversation stays open; it can be continued from the dashboard.
    }
    if (!mounted) return;
    if (evaluated) {
      // The practice is disposed with this screen, but evaluation() only needs the API.
      final load = _practice.evaluation;
      Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => SpeakingResultScreen(load: load)));
    } else {
      Navigator.maybePop(context);
    }
  }

  void _scrollDown() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Speaking',
      action: AppTextAction(label: 'Akhiri', onPressed: _end),
      bottom: _buildControls(),
      body: ListView(
        controller: _scroll,
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          if (_state == SpeakingState.slow) ...[
            StatusBanner.slow(onAction: _practice.started ? _cancelTurn : () => Navigator.maybePop(context)),
            const SizedBox(height: 24),
          ],
          if (_startFailed) ...[
            StatusBanner.timeout(onAction: _start),
            const SizedBox(height: 24),
          ],
          if (_state == SpeakingState.error) ...[
            StatusBanner(
              type: BannerType.error,
              message: 'Suaramu tidak terdengar jelas. Coba bicara lebih dekat ke HP.',
              actionLabel: 'Coba lagi',
              onAction: _startRecording,
            ),
            const SizedBox(height: 24),
          ],
          if (!_practice.started && !_startFailed)
            Text('Menyiapkan percakapan…', style: AppText.body),
          for (var i = 0; i < _messages.length; i++)
            ChatBubble(
              text: _messages[i].text,
              fromAi: _messages[i].fromAi,
              speaking: _speakingIndex == i,
              onSpeaker: _state == SpeakingState.idle && _messages[i].audioMediaId != null
                  ? () => _playAi(i)
                  : null,
            ),
          if (_messages.length == 1) ...[
            const SizedBox(height: 12),
            Text('Jawab dengan suaramu dalam bahasa Inggris.', style: AppText.body),
          ],
        ],
      ),
    );
  }

  Widget _buildControls() {
    late Widget button;
    late String label;
    switch (_state) {
      case SpeakingState.idle:
      case SpeakingState.error:
        label = 'Tekan untuk bicara';
        button = _MicButton(
          onTap: _practice.started ? _startRecording : null,
          color: _practice.started ? null : AppColors.disabled,
          child: Icon(Icons.mic_none_rounded,
              color: _practice.started ? Colors.white : AppColors.disabledText, size: 28),
        );
      case SpeakingState.recording:
        label = 'Mendengarkan…';
        button = Container(
          padding: const EdgeInsets.all(6),
          decoration: const BoxDecoration(color: AppColors.primarySoft, shape: BoxShape.circle),
          child: _MicButton(
            size: 60,
            onTap: _stopRecording,
            child: Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white, width: 1.6),
                borderRadius: BorderRadius.circular(5),
              ),
            ),
          ),
        );
      case SpeakingState.processing:
      case SpeakingState.slow:
        label = 'Memproses…';
        button = const _MicButton(
          child: SizedBox(
            width: 26,
            height: 26,
            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
          ),
        );
      case SpeakingState.aiSpeaking:
        label = 'AI sedang berbicara…';
        button = const _MicButton(
          color: AppColors.disabled,
          child: Icon(Icons.mic_none_rounded, color: AppColors.disabledText, size: 28),
        );
    }

    final live = _practice.liveTranscript;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_state == SpeakingState.recording) ...[
          const SizedBox(height: 4),
          Text(live.isEmpty ? '…' : live,
              textAlign: TextAlign.center,
              style: AppText.sans(size: 16, color: AppColors.primary)),
          const SizedBox(height: 12),
          const SoundWave(),
          const SizedBox(height: 12),
        ],
        button,
        const SizedBox(height: 10),
        Text(label,
            style: AppText.sans(size: 15, weight: FontWeight.w600, color: AppColors.textSecondary)),
      ],
    );
  }
}

class _MicButton extends StatelessWidget {
  const _MicButton({required this.child, this.onTap, this.size = 72, this.color});
  final Widget child;
  final VoidCallback? onTap;
  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color ?? AppColors.primary,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: SizedBox(width: size, height: size, child: Center(child: child)),
      ),
    );
  }
}
