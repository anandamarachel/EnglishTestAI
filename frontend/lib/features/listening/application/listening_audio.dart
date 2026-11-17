import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The Listening player as the screen sees it. Notifies on every position or
/// play/pause change.
abstract class ListeningAudio extends ChangeNotifier {
  Duration get duration;
  Duration get position;
  bool get playing;
  double get speed;

  /// Plays from the current position (from the start once it reached the end).
  Future<void> play();
  Future<void> pause();
  Future<void> seek(Duration position);

  /// 0.75 or 1.0 in the design.
  Future<void> setSpeed(double speed);
}

/// Creates the player for a downloaded audio file. Tests replace it (the real
/// player needs the platform plugin).
typedef ListeningAudioLoader = Future<ListeningAudio> Function(
    Uint8List bytes, String mimeType, Duration knownDuration);

final listeningAudioLoaderProvider =
    Provider<ListeningAudioLoader>((ref) => PlayerListeningAudio.load);

/// [ListeningAudio] on `audioplayers`, playing the downloaded bytes (the media
/// endpoint needs the login token, which a plain URL source could not send).
class PlayerListeningAudio extends ListeningAudio {
  PlayerListeningAudio._(this._player, this._duration);

  static Future<ListeningAudio> load(
      Uint8List bytes, String mimeType, Duration knownDuration) async {
    final player = AudioPlayer();
    try {
      await player.setReleaseMode(ReleaseMode.stop);
      await player.setSourceBytes(bytes, mimeType: mimeType);
      final duration = await player.getDuration();
      return PlayerListeningAudio._(player, duration ?? knownDuration).._listen();
    } catch (_) {
      await player.dispose();
      rethrow;
    }
  }

  final AudioPlayer _player;
  final _subscriptions = <StreamSubscription<Object?>>[];
  Duration _duration;
  Duration _position = Duration.zero;
  bool _playing = false;
  double _speed = 1.0;

  void _listen() {
    _subscriptions.addAll([
      _player.onPositionChanged.listen((p) {
        _position = p;
        notifyListeners();
      }),
      _player.onDurationChanged.listen((d) {
        if (d > Duration.zero) _duration = d;
        notifyListeners();
      }),
      _player.onPlayerStateChanged.listen((s) {
        _playing = s == PlayerState.playing;
        notifyListeners();
      }),
      _player.onPlayerComplete.listen((_) {
        _playing = false;
        _position = _duration;
        notifyListeners();
      }),
    ]);
  }

  @override
  Duration get duration => _duration;
  @override
  Duration get position => _position;
  @override
  bool get playing => _playing;
  @override
  double get speed => _speed;

  @override
  Future<void> play() async {
    if (_duration > Duration.zero && _position >= _duration) await seek(Duration.zero);
    await _player.resume();
    await _player.setPlaybackRate(_speed); // some platforms reset the rate on resume
  }

  @override
  Future<void> pause() => _player.pause();

  @override
  Future<void> seek(Duration position) async {
    await _player.seek(position);
    _position = position;
    notifyListeners();
  }

  @override
  Future<void> setSpeed(double speed) async {
    _speed = speed;
    notifyListeners();
    await _player.setPlaybackRate(speed);
  }

  @override
  void dispose() {
    for (final s in _subscriptions) {
      s.cancel();
    }
    _player.dispose();
    super.dispose();
  }
}

/// [ListeningAudio] without sound: moves the position with a timer. Used by the
/// design gallery and widget tests.
class SimulatedListeningAudio extends ListeningAudio {
  SimulatedListeningAudio({required Duration duration, Duration position = Duration.zero})
      : _duration = duration,
        _position = position;

  final Duration _duration;
  Duration _position;
  bool _playing = false;
  double _speed = 1.0;
  Timer? _ticker;

  @override
  Duration get duration => _duration;
  @override
  Duration get position => _position;
  @override
  bool get playing => _playing;
  @override
  double get speed => _speed;

  @override
  Future<void> play() async {
    if (_position >= _duration) _position = Duration.zero;
    _playing = true;
    _ticker?.cancel();
    _ticker = Timer.periodic(const Duration(milliseconds: 200), (t) {
      _position += Duration(milliseconds: (200 * _speed).round());
      if (_position >= _duration) {
        _position = _duration;
        _playing = false;
        t.cancel();
      }
      notifyListeners();
    });
    notifyListeners();
  }

  @override
  Future<void> pause() async {
    _ticker?.cancel();
    _playing = false;
    notifyListeners();
  }

  @override
  Future<void> seek(Duration position) async {
    _position = position;
    notifyListeners();
  }

  @override
  Future<void> setSpeed(double speed) async {
    _speed = speed;
    notifyListeners();
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }
}
