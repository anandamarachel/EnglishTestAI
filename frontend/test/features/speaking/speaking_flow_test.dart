import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/speaking/application/voice_io.dart';
import 'package:english_day/features/speaking/presentation/speaking_screen.dart';

import '../../support/fake_backend.dart';
import '../../support/speaking_fixtures.dart';

/// The Speaking screen against a fake backend, microphone and speaker.
void main() {
  late FakeBackend backend;
  late FakeConversation conversation;
  late FakeRecorder recorder;
  late FakePlayer player;

  Future<void> open(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final reportError = FlutterError.onError!;
    FlutterError.onError = (d) {
      if (!d.exceptionAsString().contains('overflowed')) reportError(d); // test font only
    };
    addTearDown(() => FlutterError.onError = reportError);

    final storage = MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r'));
    await tester.pumpWidget(ProviderScope(
      overrides: [
        apiClientProvider.overrideWith((ref) {
          final api = ApiClient(storage: storage, baseUrl: 'http://test/api/v1', adapter: backend);
          ref.onDispose(api.dispose);
          return api;
        }),
        voiceRecorderFactoryProvider.overrideWithValue(() => recorder),
        voicePlayerFactoryProvider.overrideWithValue(() => player),
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () => Navigator.of(context)
                    .push(MaterialPageRoute(builder: (_) => const SpeakingScreen())),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }

  /// The big round button at the bottom (mic / stop).
  Finder micButton() => find.byType(InkWell).last;

  setUp(() {
    backend = FakeBackend();
    conversation = speakingHappyPath(backend);
    recorder = FakeRecorder();
    player = FakePlayer();
  });

  testWidgets('Akhiri without speaking just goes back (nothing to evaluate)', (tester) async {
    await open(tester);
    await tester.tap(find.text('Akhiri'));
    await tester.pumpAndSettle();
    expect(find.text('open'), findsOneWidget);
    expect(backend.count('POST /speaking/attempts/$speakingAttemptId/finish'), 0);
  });

  testWidgets('greeting, one spoken turn with the AI reply, then Akhiri', (tester) async {
    await open(tester);

    expect(find.text('Hi! What did you do last weekend?'), findsOneWidget);
    expect(player.played, hasLength(1)); // the greeting was spoken
    expect(find.text('Tekan untuk bicara'), findsOneWidget);

    await tester.tap(micButton());
    await tester.pump();
    expect(find.text('Mendengarkan…'), findsOneWidget);
    expect(recorder.recording, isTrue);

    await tester.tap(micButton());
    await tester.pumpAndSettle();
    expect(find.text('I went to the beach.'), findsOneWidget);
    expect(find.text('Which beach did you visit?'), findsOneWidget);
    expect(player.played, hasLength(2)); // the reply was spoken
    expect(find.text('Tekan untuk bicara'), findsOneWidget);

    await tester.tap(find.text('Akhiri'));
    await tester.pumpAndSettle();
    expect(backend.count('POST /speaking/attempts/$speakingAttemptId/finish'), 1);
    expect(recorder.disposed, isTrue);

    // The evaluation: assessed criteria with their score, the others marked.
    expect(find.text('Hasil Speaking'), findsOneWidget);
    expect(find.text('Good effort.'), findsOneWidget);
    expect(find.text('Kosakata'), findsOneWidget);
    expect(find.text('4,5/9'), findsOneWidget);
    expect(find.text('Use more varied words.'), findsOneWidget);
    expect(find.text('Belum dinilai'), findsOneWidget);
    expect(find.text('Nilai keseluruhan muncul setelah semua aspek bisa dinilai.'), findsOneWidget);

    await tester.tap(find.text('Kembali ke dashboard'));
    await tester.pumpAndSettle();
    expect(find.text('open'), findsOneWidget);
  });

  testWidgets('no speech heard shows the design banner', (tester) async {
    conversation.failNextTurn = 'NO_SPEECH_DETECTED';
    await open(tester);

    await tester.tap(micButton());
    await tester.pump();
    await tester.tap(micButton());
    await tester.pumpAndSettle();

    expect(find.text('Suaramu tidak terdengar jelas. Coba bicara lebih dekat ke HP.'),
        findsOneWidget);
    expect(backend.count('POST /speaking/attempts/$speakingAttemptId/finish'), 0);
  });

  testWidgets('refused microphone leads to the "akses dimatikan" screen', (tester) async {
    recorder.permission = false;
    await open(tester);

    await tester.tap(micButton());
    await tester.pumpAndSettle();

    expect(find.text('Akses mikrofon dimatikan'), findsOneWidget);
  });
}
