import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/app.dart';
import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';

import '../../support/fake_backend.dart';

/// Ubah nama, ubah password and reset password, in the real app with a fake backend.
void main() {
  late FakeBackend backend;
  var name = 'Rina Amelia';

  Future<void> startApp(WidgetTester tester, MemoryTokenStorage storage) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final reportError = FlutterError.onError!;
    FlutterError.onError = (d) {
      if (!d.exceptionAsString().contains('overflowed')) reportError(d); // test font only
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

  MemoryTokenStorage loggedIn() =>
      MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r'));

  Future<void> openProfile(WidgetTester tester) async {
    await tester.tap(find.text('RA'));
    await tester.pumpAndSettle();
  }

  setUp(() {
    backend = FakeBackend();
    name = 'Rina Amelia';
    backend.on('GET /users/me', (_) => Reply(200, userJson(name: name)));
    backend.on('GET /dashboard', (_) => Reply(200, {
          'user': userJson(name: name),
          'resume_attempt': null,
          'pending_attempts': <Object>[],
          'has_more_pending': false,
        }));
  });

  testWidgets('Ubah nama updates the profile and the dashboard', (tester) async {
    backend.on('PATCH /users/me', (r) {
      name = ((r.body as Map)['display_name'] as String).trim();
      return Reply(200, userJson(name: name));
    });
    await startApp(tester, loggedIn());
    await openProfile(tester);

    await tester.tap(find.text('Ubah nama'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, 'Rina Amelia');
    await tester.enterText(find.byType(TextField), '   ');
    await tester.tap(find.text('Simpan'));
    await tester.pump();
    expect(find.text('Nama lengkap wajib diisi.'), findsOneWidget);
    expect(backend.count('PATCH /users/me'), 0);

    await tester.enterText(find.byType(TextField), 'Budi Santoso');
    await tester.tap(find.text('Simpan'));
    await tester.pumpAndSettle();
    expect((backend.sent.last.body as Map)['display_name'], 'Budi Santoso');
    expect(find.text('Budi Santoso'), findsOneWidget); // back on the profile
    expect(find.text('BS'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.arrow_back));
    await tester.pumpAndSettle();
    expect(find.text('Halo, Budi'), findsOneWidget);
  });

  testWidgets('Ubah password: wrong current password, then success signs out', (tester) async {
    var attempts = 0;
    backend.on('POST /auth/password/change', (r) {
      attempts++;
      if ((r.body as Map)['current_password'] != 'password123') {
        return Reply(422, errorJson('VALIDATION_ERROR', details: [
          {'field': 'current_password', 'message': 'Current password is incorrect.'},
        ]));
      }
      return const Reply(204);
    });
    final storage = loggedIn();
    await startApp(tester, storage);
    await openProfile(tester);
    await tester.tap(find.text('Ubah password'));
    await tester.pumpAndSettle();

    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'salah123');
    await tester.enterText(fields.at(1), 'passwordbaru');
    await tester.enterText(fields.at(2), 'passwordbeda');
    await tester.tap(find.text('Simpan password'));
    await tester.pump();
    expect(find.text('Konfirmasi password tidak sama.'), findsOneWidget);
    expect(attempts, 0);

    await tester.enterText(fields.at(2), 'passwordbaru');
    await tester.tap(find.text('Simpan password'));
    await tester.pumpAndSettle();
    expect(find.text('Password sekarang salah.'), findsOneWidget);

    await tester.enterText(fields.at(0), 'password123');
    await tester.tap(find.text('Simpan password'));
    await tester.pumpAndSettle();
    expect(find.text('Lanjutkan latihan bahasa Inggrismu.'), findsOneWidget); // login screen
    expect(find.text('Password diubah. Masuk lagi dengan password baru.'), findsOneWidget);
    expect(await storage.read(), isNull);
  });

  testWidgets('Lupa password leads to the reset screen; a valid code changes it',
      (tester) async {
    backend.on('POST /auth/password/forgot', (_) => const Reply(202, {'message': 'ok'}));
    backend.on('POST /auth/password/reset', (r) => (r.body as Map)['token'] == 'good-code'
        ? const Reply(204)
        : Reply(422, errorJson('INVALID_RESET_TOKEN', details: [
            {'field': 'token', 'message': 'Invalid or expired token.'},
          ])));
    await startApp(tester, MemoryTokenStorage());

    await tester.enterText(find.byType(TextField).at(0), 'rina@example.test');
    await tester.tap(find.text('Lupa password?'));
    await tester.pumpAndSettle();
    expect(find.text('Reset password'), findsOneWidget);
    expect((backend.sent.last.body as Map)['email'], 'rina@example.test');

    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'old-code');
    await tester.enterText(fields.at(1), 'passwordbaru');
    await tester.enterText(fields.at(2), 'passwordbaru');
    await tester.tap(find.text('Simpan password'));
    await tester.pumpAndSettle();
    expect(find.text('Kode tidak valid atau sudah kedaluwarsa. Minta kode baru.'), findsOneWidget);

    await tester.enterText(fields.at(0), ' good-code ');
    await tester.tap(find.text('Simpan password'));
    await tester.pumpAndSettle();
    expect((backend.sent.last.body as Map)['token'], 'good-code');
    expect(find.text('Lanjutkan latihan bahasa Inggrismu.'), findsOneWidget);
    expect(find.text('Password diubah. Silakan masuk dengan password baru.'), findsOneWidget);
  });
}
