import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';

import 'package:english_day/core/audio/wav.dart';

/// Records the student's voice as a WAV file (PCM 16-bit mono 16 kHz, what the
/// backend accepts). Tests and the design gallery replace it.
abstract interface class VoiceRecorder {
  /// Asks for microphone access when needed. False when the user refused.
  Future<bool> hasPermission();
  Future<void> start();

  /// Stops and returns the recording as WAV bytes.
  Future<Uint8List> stop();
  Future<void> cancel();
  void dispose();
}

/// Plays an AI reply. [play] completes when the audio ended or [stop] was called.
abstract interface class VoicePlayer {
  Future<void> play(Uint8List bytes, String mimeType);
  Future<void> stop();
  void dispose();
}

/// Factories: whoever creates a recorder/player (the Speaking session) disposes it.
final voiceRecorderFactoryProvider =
    Provider<VoiceRecorder Function()>((ref) => MicVoiceRecorder.new);
final voicePlayerFactoryProvider = Provider<VoicePlayer Function()>((ref) => SpeakerVoicePlayer.new);

/// [VoiceRecorder] on the `record` package. Streams raw PCM (supported the same
/// way on Android, iOS and web) and wraps it in a WAV header when stopped.
class MicVoiceRecorder implements VoiceRecorder {
  static const sampleRate = 16000;

  final _recorder = AudioRecorder();
  final _pcm = BytesBuilder(copy: false);
  StreamSubscription<Uint8List>? _subscription;
  Completer<void>? _streamDone;

  @override
  Future<bool> hasPermission() => _recorder.hasPermission();

  @override
  Future<void> start() async {
    _pcm.clear();
    final done = _streamDone = Completer<void>();
    final stream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: sampleRate,
      numChannels: 1,
    ));
    _subscription = stream.listen(_pcm.add, onDone: () {
      if (!done.isCompleted) done.complete();
    });
  }

  @override
  Future<Uint8List> stop() async {
    await _recorder.stop();
    // The last samples may still arrive after stop(); wait briefly for the stream end.
    await _streamDone?.future.timeout(const Duration(seconds: 1), onTimeout: () {});
    await _subscription?.cancel();
    _subscription = null;
    return wavFromPcm16(_pcm.takeBytes(), sampleRate: sampleRate);
  }

  @override
  Future<void> cancel() async {
    await _recorder.cancel();
    await _subscription?.cancel();
    _subscription = null;
    _pcm.clear();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _recorder.dispose();
  }
}

/// [VoicePlayer] on `audioplayers`, playing downloaded bytes (the media endpoint
/// needs the login token).
class SpeakerVoicePlayer implements VoicePlayer {
  final _player = AudioPlayer();
  Completer<void>? _playing;

  @override
  Future<void> play(Uint8List bytes, String mimeType) async {
    await stop();
    final done = _playing = Completer<void>();
    final completed = _player.onPlayerComplete.listen((_) {
      if (!done.isCompleted) done.complete();
    });
    try {
      await _player.play(BytesSource(bytes, mimeType: mimeType));
      await done.future;
    } finally {
      await completed.cancel();
    }
  }

  @override
  Future<void> stop() async {
    final playing = _playing;
    _playing = null;
    if (playing != null && !playing.isCompleted) playing.complete();
    await _player.stop();
  }

  @override
  void dispose() {
    final playing = _playing;
    if (playing != null && !playing.isCompleted) playing.complete();
    _player.dispose();
  }
}
