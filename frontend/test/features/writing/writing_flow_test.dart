import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/features/writing/presentation/writing_input_screen.dart';

import '../../support/fake_backend.dart';
import '../../support/writing_fixtures.dart';

/// The Writing screens against a fake backend, as the user goes through them.
void main() {
  late FakeBackend backend;

  Future<void> open(WidgetTester tester, {String? resumeAttemptId}) async {
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
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        home: WritingInputScreen(resumeAttemptId: resumeAttemptId),
      ),
    ));
    await tester.pumpAndSettle();
  }

  setUp(() => backend = FakeBackend());

  testWidgets('write, check, see corrections, open one, write again', (tester) async {
    writingHappyPath(backend);
    await open(tester);

    await tester.enterText(find.byType(TextField), sampleText);
    await tester.pump();
    await tester.tap(find.text('Cek grammar'));
    await tester.pumpAndSettle();

    expect(find.text('2 bagian perlu diperbaiki'), findsOneWidget);
    expect(find.text('went'), findsOneWidget);
    expect(find.text('Yesterday I went to school and we were late.'), findsOneWidget);

    await tester.tap(find.text('went'));
    await tester.pumpAndSettle();
    expect(find.text('Past tense'), findsOneWidget);
    expect(find.text('Explanation of Past tense.'), findsOneWidget);
    await tester.tap(find.text('Mengerti'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Tulis lagi'));
    await tester.pumpAndSettle();
    expect(find.text('Cek grammar'), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
  });

  testWidgets('no corrections shows "Tidak ada kesalahan"', (tester) async {
    writingHappyPath(backend,
        evaluation: evaluationJson(corrections: [], correctedText: 'All good.'));
    await open(tester);

    await tester.enterText(find.byType(TextField), 'All good.');
    await tester.pump();
    await tester.tap(find.text('Cek grammar'));
    await tester.pumpAndSettle();

    expect(find.text('Tidak ada kesalahan. Kalimatmu sudah benar.'), findsOneWidget);
  });

  testWidgets('AI failure shows the design banner and "Coba lagi" recovers', (tester) async {
    writingHappyPath(backend);
    backend.on('GET /jobs/$evaluateJobId',
        (_) => Reply(200, jobJson(evaluateJobId, 'evaluate_attempt', 'failed', error: 'AI_ERROR')));
    await open(tester);

    await tester.enterText(find.byType(TextField), sampleText);
    await tester.pump();
    await tester.tap(find.text('Cek grammar'));
    await tester.pumpAndSettle();
    expect(find.text('AI belum merespons. Coba lagi dalam beberapa saat.'), findsOneWidget);

    backend.on('GET /jobs/$evaluateJobId',
        (_) => Reply(200, jobJson(evaluateJobId, 'evaluate_attempt', 'succeeded')));
    await tester.tap(find.text('Coba lagi'));
    await tester.pumpAndSettle();
    expect(find.text('2 bagian perlu diperbaiki'), findsOneWidget);
  });

  testWidgets('"Lanjutkan" from the dashboard restores the saved text', (tester) async {
    backend.on('GET /attempts/$attemptId', (_) => Reply(200, {
          'attempt': attemptJson(revision: 4),
          'exercise': <String, dynamic>{},
          'draft': {'skill': 'writing', 'response_text': 'My saved draft'},
          'answers': <Object>[],
          'conversation': null,
          'active_jobs': <Object>[],
          'evaluation': null,
        }));
    await open(tester, resumeAttemptId: attemptId);

    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, 'My saved draft');
    expect(backend.count('POST /writing/exercises'), 0);
  });
}
