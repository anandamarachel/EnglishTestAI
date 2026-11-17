import 'dart:async';

import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/speaking/application/speaking_session.dart';
import 'package:english_day/features/speaking/data/speaking_repository.dart';

/// Speaking without a backend or microphone, for the design gallery: the dummy
/// conversation, a word-by-word "live transcript" and timed AI replies.
class DemoSpeakingPractice implements SpeakingPractice {
  DemoSpeakingPractice({bool withHistory = false}) {
    final source = withHistory ? SpeakingDummy.conversation : [SpeakingDummy.opening];
    for (final m in source) {
      _messages.add(_message(m.text, m.fromAi));
    }
    _turn = withHistory ? 1 : 0;
  }

  @override
  void Function()? onChange;

  final _messages = <SpeakingMessage>[];
  late int _turn;
  String _live = '';
  Timer? _timer;
  Completer<void>? _playing;

  SpeakingMessage _message(String text, bool fromAi) => SpeakingMessage(
      id: 'm${_messages.length}', fromAi: fromAi, text: text, audioMediaId: fromAi ? 'demo' : null);

  String get _userReply => SpeakingDummy.userReplies[_turn % SpeakingDummy.userReplies.length];
  String get _aiReply => SpeakingDummy.aiReplies[_turn % SpeakingDummy.aiReplies.length];

  /// Gallery "recording" state: show the live transcript without a timer.
  void showLiveTranscript() => _live = SpeakingDummy.liveTranscript;

  @override
  List<SpeakingMessage> get messages => _messages;
  @override
  bool get started => true;
  @override
  String get liveTranscript => _live;

  @override
  Future<void> start() async {}

  @override
  Future<void> startRecording() async {
    final words = _userReply.split(' ');
    var i = 0;
    _live = '';
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(milliseconds: 380), (t) {
      if (i >= words.length) return t.cancel();
      _live = words.sublist(0, ++i).join(' ');
      onChange?.call();
    });
  }

  @override
  Future<void> cancelRecording() async => _timer?.cancel();

  @override
  Future<SpeakingMessage?> stopAndSend() async {
    _timer?.cancel();
    await Future<void>.delayed(const Duration(milliseconds: 900));
    _messages.add(_message(_userReply, false));
    await Future<void>.delayed(const Duration(milliseconds: 1100));
    final reply = _message(_aiReply, true);
    _messages.add(reply);
    _turn++;
    return reply;
  }

  @override
  Future<void> cancelTurn() async {}

  @override
  Future<void> play(SpeakingMessage message) async {
    final done = _playing = Completer<void>();
    Timer(const Duration(milliseconds: 2400), () {
      if (!done.isCompleted) done.complete();
    });
    await done.future;
  }

  @override
  Future<void> stopPlayback() async {
    final playing = _playing;
    if (playing != null && !playing.isCompleted) playing.complete();
  }

  @override
  Future<void> finish() async {}

  @override
  void dispose() {
    _timer?.cancel();
    stopPlayback();
  }
}
