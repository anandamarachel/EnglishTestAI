import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/reading/presentation/reading_settings_screen.dart';

import '../../support/fake_backend.dart';
import '../../support/reading_fixtures.dart';

/// Settings → story → quiz → result against a fake backend, as the user does it.
void main() {
  testWidgets('choose, read, look up a word, answer the quiz and see the score',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final reportError = FlutterError.onError!;
    FlutterError.onError = (d) {
      if (!d.exceptionAsString().contains('overflowed')) reportError(d); // test font only
    };
    addTearDown(() => FlutterError.onError = reportError);

    final backend = FakeBackend();
    readingHappyPath(backend);
    final storage = MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r'));
    await tester.pumpWidget(ProviderScope(
      overrides: [
        apiClientProvider.overrideWith((ref) {
          final api = ApiClient(storage: storage, baseUrl: 'http://test/api/v1', adapter: backend);
          ref.onDispose(api.dispose);
          return api;
        }),
      ],
      child: MaterialApp(theme: AppTheme.light, home: const ReadingSettingsScreen()),
    ));

    await tester.tap(find.text('Buat cerita'));
    await tester.pumpAndSettle();
    expect(find.text('The Blue Kite'), findsOneWidget);
    expect(find.text('Medium · Budaya'), findsOneWidget);

    await tester.tap(find.text('gust'));
    await tester.pumpAndSettle();
    expect(find.text('hembusan angin'), findsOneWidget);
    await tester.tap(find.text('Kembali membaca'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Mulai kuis'));
    await tester.pumpAndSettle();
    expect(find.text('Soal 1 dari 2'), findsOneWidget);
    await tester.tap(find.text('B. Blue'));
    await tester.pump();
    await tester.tap(find.text('Kirim jawaban'));
    await tester.pumpAndSettle();
    expect(find.text('The story says it for q1.'), findsOneWidget);

    await tester.tap(find.text('Soal berikutnya'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('C. A bird'));
    await tester.pump();
    await tester.tap(find.text('Kirim jawaban'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Lihat hasil'));
    await tester.pumpAndSettle();

    expect(find.text('Hasil kuis'), findsOneWidget);
    expect(find.text('1/2'), findsOneWidget);
    expect(find.text('Belum tepat · A gust'), findsOneWidget);
  });
}
