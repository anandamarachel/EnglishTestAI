import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/listening/application/listening_audio.dart';
import 'package:english_day/features/listening/presentation/listening_screen.dart';

import '../../support/fake_backend.dart';
import '../../support/listening_fixtures.dart';

/// Intro → audio + questions → result with transcript, against a fake backend.
void main() {
  late FakeBackend backend;
  late FakeAudioLoader loader;

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
        listeningAudioLoaderProvider.overrideWithValue(loader.call),
      ],
      child: MaterialApp(theme: AppTheme.light, home: const ListeningScreen()),
    ));
  }

  setUp(() {
    backend = FakeBackend();
    loader = FakeAudioLoader();
  });

  testWidgets('listen, answer, submit and read the unlocked transcript', (tester) async {
    listeningHappyPath(backend);
    await open(tester);

    await tester.tap(find.text('Mulai latihan'));
    await tester.pumpAndSettle();
    expect(find.text('At the Canteen'), findsOneWidget);
    expect(find.text('0:00 / 0:30'), findsOneWidget);
    expect(loader.audio!.playing, isTrue); // starts playing by itself

    await tester.tap(find.byIcon(Icons.pause_rounded));
    await tester.pump();
    expect(loader.audio!.playing, isFalse);
    await tester.tap(find.text('0,75×'));
    await tester.pump();
    expect(loader.audio!.speed, 0.75);

    await tester.tap(find.text('Kirim jawaban'));
    await tester.pump();
    expect(find.text('Jawab semua pertanyaan dulu, ya.'), findsOneWidget);

    for (final option in ['A. A chicken sandwich', 'C. In class']) {
      await tester.ensureVisible(find.text(option));
      await tester.pumpAndSettle();
      await tester.tap(find.text(option));
      await tester.pump();
    }
    await tester.pump(const Duration(seconds: 5)); // let the snackbar go
    await tester.tap(find.text('Kirim jawaban'));
    await tester.pumpAndSettle();

    expect(find.text('Hasil latihan'), findsOneWidget);
    expect(find.text('1/2'), findsOneWidget);
    expect(find.text('B. Near the window'), findsOneWidget); // the correct answer shown
    expect(find.text('Explained q2.'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Andi: I will sit near the window.'), 300);
    expect(find.text('Andi: I will sit near the window.'), findsOneWidget);
  });

  testWidgets('audio that cannot be loaded shows the design banner; retry fixes it',
      (tester) async {
    listeningHappyPath(backend);
    loader.failWith = Exception('decoder');
    await open(tester);

    await tester.tap(find.text('Mulai latihan'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Audio gagal dimuat'), findsOneWidget);
    expect(find.text('What does Andi want to buy?'), findsOneWidget); // can still answer

    loader.failWith = null;
    await tester.tap(find.text('Coba lagi'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Audio gagal dimuat'), findsNothing);
    expect(loader.audio!.playing, isTrue);
  });
}
