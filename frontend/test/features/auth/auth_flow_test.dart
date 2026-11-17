import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/app.dart';
import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';

import '../../support/fake_backend.dart';

/// Runs the real app (splash -> login -> dashboard) against a fake backend.
void main() {
  late FakeBackend backend;

  Map<String, dynamic> dashboardJson({bool withResume = true}) => {
        'user': userJson(),
        'resume_attempt': withResume
            ? {
                'attempt_id': '1',
                'exercise_id': '2',
                'skill': 'writing',
                'title': 'Describe your dream destination',
                'status': 'in_progress',
                'current_stage': 'writing',
              }
            : null,
        'pending_attempts': [],
        'has_more_pending': false,
      };

  Future<void> startApp(WidgetTester tester, MemoryTokenStorage storage) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final reportError = FlutterError.onError!;
    FlutterError.onError = (d) {
      // Test font overflows are not real (see gallery_test.dart).
      if (!d.exceptionAsString().contains('overflowed')) reportError(d);
    };
    addTearDown(() => FlutterError.onError = reportError);

    await tester.pumpWidget(ProviderScope(
      overrides: [
        tokenStorageProvider.overrideWithValue(storage),
        apiClientProvider.overrideWith((ref) {
          final api = ApiClient(storage: storage, baseUrl: 'http://test/api/v1', adapter: backend);
          ref.onDispose(api.dispose);
          return api;
        }),
      ],
      child: const EnglishDayApp(),
    ));
    await tester.pump(const Duration(milliseconds: 1900)); // splash minimum
    await tester.pumpAndSettle();
  }

  Future<void> login(WidgetTester tester, String password) async {
    await tester.enterText(find.byType(TextField).at(0), 'rina@example.test');
    await tester.enterText(find.byType(TextField).at(1), password);
    await tester.tap(find.text('Masuk').last);
    await tester.pumpAndSettle();
  }

  setUp(() => backend = FakeBackend());

  testWidgets('new user: splash -> login -> dashboard with real data', (tester) async {
    backend.on('POST /auth/login', (r) => (r.body as Map)['password'] == 'password123'
        ? Reply(200, tokensJson('a', 'r'))
        : Reply(401, errorJson('INVALID_CREDENTIALS')));
    backend.on('GET /dashboard', (_) => Reply(200, dashboardJson()));
    final storage = MemoryTokenStorage();

    await startApp(tester, storage);
    expect(find.text('Lanjutkan latihan bahasa Inggrismu.'), findsOneWidget); // login screen

    await login(tester, 'password123');

    expect(find.text('Halo, Rina'), findsOneWidget);
    expect(find.text('RA'), findsOneWidget);
    expect(find.text('Writing · Describe your dream destination'), findsOneWidget);
    expect((await storage.read())?.accessToken, 'a');
  });

  testWidgets('wrong password shows the design error banner', (tester) async {
    backend.on('POST /auth/login', (_) => Reply(401, errorJson('INVALID_CREDENTIALS')));
    await startApp(tester, MemoryTokenStorage());

    await login(tester, 'wrong-password');

    expect(find.text('Email atau password salah.'), findsOneWidget);
    expect(find.text('Halo, Rina'), findsNothing);
  });

  testWidgets('stored session opens the dashboard directly (no resume card)', (tester) async {
    backend.on('GET /users/me', (_) => Reply(200, userJson()));
    backend.on('GET /dashboard', (_) => Reply(200, dashboardJson(withResume: false)));

    await startApp(tester, MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')));

    expect(find.text('Halo, Rina'), findsOneWidget);
    expect(find.text('Lanjutkan latihan'), findsNothing);
    expect(backend.count('POST /auth/login'), 0);
  });

  testWidgets('session revoked on the server: only the sheet, no dashboard banner', (tester) async {
    backend.on('GET /users/me', (_) => Reply(200, userJson()));
    backend.on('GET /dashboard', (_) => Reply(401, errorJson('UNAUTHORIZED')));
    backend.on('POST /auth/refresh', (_) => Reply(401, errorJson('INVALID_REFRESH_TOKEN')));
    final storage = MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r'));

    await startApp(tester, storage);

    expect(find.textContaining('Sesimu sudah berakhir'), findsOneWidget); // the sheet
    expect(find.text('Coba lagi'), findsNothing); // no error banner behind it
    expect(await storage.read(), isNull);

    await tester.tap(find.text('Masuk').last);
    await tester.pumpAndSettle();
    expect(find.text('Lanjutkan latihan bahasa Inggrismu.'), findsOneWidget);
  });

  testWidgets('server down at startup: offline screen, "Coba lagi" works once it is back',
      (tester) async {
    var serverUp = false;
    backend.on('GET /users/me', (_) =>
        serverUp ? Reply(200, userJson()) : Reply(503, errorJson('SERVICE_UNAVAILABLE')));
    backend.on('GET /dashboard', (_) => Reply(200, dashboardJson(withResume: false)));

    await startApp(tester, MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')));
    expect(find.text('Tidak ada koneksi internet'), findsOneWidget);

    await tester.tap(find.text('Coba lagi'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Masih belum terhubung'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5)); // let the snackbar go
    await tester.pumpAndSettle();

    serverUp = true;
    await tester.tap(find.text('Coba lagi'));
    await tester.pumpAndSettle();
    expect(find.text('Halo, Rina'), findsOneWidget);
  });
}
