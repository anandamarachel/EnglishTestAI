import 'dart:typed_data';

import 'package:english_day/core/audio/wav.dart';
import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/jobs.dart';
import 'package:english_day/features/speaking/application/voice_io.dart';
import 'package:english_day/features/speaking/data/speaking_repository.dart';

/// The recording had no usable speech (too short, silent, or the AI heard nothing).
class NoSpeechException implements Exception {
  const NoSpeechException();
}

/// The student refused microphone access.
class MicPermissionDeniedException implements Exception {
  const MicPermissionDeniedException();
}

/// What the Speaking screen needs. [SpeakingSession] talks to the backend; the
/// design gallery uses a demo version.
abstract interface class SpeakingPractice {
  /// Oldest first; starts with the AI's greeting once [start] finished.
  List<SpeakingMessage> get messages;
  bool get started;

  /// Words heard so far while recording (empty: the backend has no live transcription).
  String get liveTranscript;

  /// Called when [liveTranscript] changes.
  set onChange(void Function()? callback);

  /// Prepares the conversation until the AI's greeting is ready.
  Future<void> start();

  /// Throws [MicPermissionDeniedException] when the microphone is not allowed.
  Future<void> startRecording();
  Future<void> cancelRecording();

  /// Sends the recording and waits for the AI's reply, which is returned (it is
  /// also the last of [messages]). Throws [NoSpeechException] when nothing was heard.
  Future<SpeakingMessage?> stopAndSend();

  /// Stops waiting for the current reply and cancels it on the server.
  Future<void> cancelTurn();

  /// Plays an AI message; completes when it ended or [stopPlayback] was called.
  Future<void> play(SpeakingMessage message);
  Future<void> stopPlayback();

  /// Ends the conversation (the server evaluates it) when the student spoke at least once.
  Future<void> finish();
  void dispose();
}

/// Speaking against the backend: generate the exercise with a persona (AI job) →
/// start the attempt (the greeting is another job) → for each turn upload a WAV
/// recording; one job transcribes it and writes the AI reply with its audio.
class SpeakingSession implements SpeakingPractice {
  SpeakingSession(this._repo, this._recorder, this._player, {String? resumeAttemptId})
      : _resumeAttemptId = resumeAttemptId;

  /// Recordings shorter than this hold no speech (the backend would reject them).
  static const minRecording = Duration(milliseconds: 500);

  /// The persona that matches the design's friendly greeting, if the backend has it.
  static const preferredPersona = 'Friendly Classmate';

  final SpeakingRepository _repo;
  final VoiceRecorder _recorder;
  final VoicePlayer _player;
  final String? _resumeAttemptId;

  String? _exerciseId;
  String? _generateJobId;
  String? _exerciseKey;
  String? _attemptKey;
  String? _attemptId;
  String? _greetingJobId;
  var _messages = <SpeakingMessage>[];
  bool _started = false;
  ({Uint8List wav, String clientKey, String key})? _pendingTurn;
  String? _turnJobId;
  String? _finishKey;
  final _audioCache = <String, Uint8List>{};
  int _run = 0;

  @override
  List<SpeakingMessage> get messages => List.unmodifiable(_messages);
  @override
  bool get started => _started;
  @override
  String get liveTranscript => '';
  @override
  set onChange(void Function()? callback) {} // no live transcript from the backend

  @override
  Future<void> start() async {
    final run = ++_run;
    bool cancelled() => run != _run;
    if (_attemptId == null) {
      final resumeId = _resumeAttemptId;
      if (resumeId != null) {
        _attemptId = resumeId;
      } else {
        await _generate(cancelled);
      }
    }
    // Wait for the greeting (or, when resuming, a turn still being processed).
    final active = _greetingJobId ?? (await _repo.conversation(_attemptId!)).activeJobId;
    if (active != null) await _repo.waitJob(active, isCancelled: cancelled);
    _greetingJobId = null;
    _messages = await _repo.messages(_attemptId!);
    _started = true;
  }

  Future<void> _generate(bool Function() cancelled) async {
    if (_exerciseId == null) {
      final personas = await _repo.personas();
      final persona = personas.firstWhere((p) => p.name == preferredPersona,
          orElse: () => personas.first);
      final created =
          await _repo.createExercise(persona.id, _exerciseKey ??= ApiClient.newIdempotencyKey());
      _exerciseKey = null;
      _exerciseId = created.exerciseId;
      _generateJobId = created.jobId;
    }
    final jobId = _generateJobId;
    if (jobId != null) {
      try {
        await _repo.waitJob(jobId, isCancelled: cancelled);
      } on JobFailedException {
        _exerciseId = null;
        _generateJobId = null;
        rethrow;
      }
      _generateJobId = null;
    }
    final started =
        await _repo.startAttempt(_exerciseId!, _attemptKey ??= ApiClient.newIdempotencyKey());
    _attemptKey = null;
    _attemptId = started.attemptId;
    _greetingJobId = started.greetingJobId;
  }

  @override
  Future<void> startRecording() async {
    await stopPlayback();
    if (!await _recorder.hasPermission()) throw const MicPermissionDeniedException();
    await _recorder.start();
  }

  @override
  Future<void> cancelRecording() => _recorder.cancel();

  @override
  Future<SpeakingMessage?> stopAndSend() async {
    final wav = await _recorder.stop();
    final pcmBytes = wav.length - 44;
    if (pcm16Duration(pcmBytes, sampleRate: MicVoiceRecorder.sampleRate) < minRecording) {
      throw const NoSpeechException();
    }
    _pendingTurn = (
      wav: wav,
      clientKey: ApiClient.newIdempotencyKey(),
      key: ApiClient.newIdempotencyKey(),
    );
    return _sendPending();
  }

  Future<SpeakingMessage?> _sendPending() async {
    final run = ++_run;
    final turn = _pendingTurn!;
    final String jobId;
    try {
      jobId = await _repo.sendTurn(
        attemptId: _attemptId!,
        wav: turn.wav,
        clientMessageKey: turn.clientKey,
        key: turn.key,
      );
    } on ApiException catch (e) {
      if (e.statusCode == 415) throw const NoSpeechException(); // not decodable audio
      rethrow;
    }
    _pendingTurn = null;
    _turnJobId = jobId;
    try {
      await _repo.waitJob(jobId, isCancelled: () => run != _run);
    } on JobFailedException catch (e) {
      _turnJobId = null;
      _messages = await _repo.messages(_attemptId!);
      if (e.job.errorCode == 'NO_SPEECH_DETECTED') throw const NoSpeechException();
      rethrow;
    }
    _turnJobId = null;
    _messages = await _repo.messages(_attemptId!);
    final last = _messages.isEmpty ? null : _messages.last;
    return last != null && last.fromAi ? last : null;
  }

  @override
  Future<void> cancelTurn() async {
    _run++;
    final jobId = _turnJobId;
    _turnJobId = null;
    if (jobId == null) return;
    try {
      await _repo.cancelJob(jobId);
    } on ApiException {
      // Already finished or unreachable.
    }
  }

  @override
  Future<void> play(SpeakingMessage message) async {
    final mediaId = message.audioMediaId;
    if (mediaId == null) return;
    final bytes = _audioCache[mediaId] ??= await _repo.audio(mediaId);
    await _player.play(bytes, message.audioMimeType);
  }

  @override
  Future<void> stopPlayback() => _player.stop();

  @override
  Future<void> finish() async {
    await stopPlayback();
    final attemptId = _attemptId;
    if (attemptId == null || !_messages.any((m) => !m.fromAi && m.text.isNotEmpty)) return;
    await _repo.finish(attemptId, _finishKey ??= ApiClient.newIdempotencyKey());
    _finishKey = null;
  }

  @override
  void dispose() {
    _run++;
    _recorder.cancel().whenComplete(_recorder.dispose);
    _player.stop().whenComplete(_player.dispose);
  }
}
