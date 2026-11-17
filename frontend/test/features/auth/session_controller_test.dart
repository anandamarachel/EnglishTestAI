import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/features/auth/application/session_controller.dart';
import 'package:english_day/features/dashboard/data/dashboard.dart';

import '../../support/fake_backend.dart';

void main() {
  late FakeBackend backend;

  ProviderContainer container(MemoryTokenStorage storage) {
    final c = ProviderContainer(overrides: [
      tokenStorageProvider.overrideWithValue(storage),
      apiClientProvider.overrideWith((ref) {
        final api = ApiClient(storage: storage, baseUrl: 'http://test/api/v1', adapter: backend);
        ref.onDispose(api.dispose);
        return api;
      }),
    ]);
    addTearDown(c.dispose);
    return c;
  }

  setUp(() => backend = FakeBackend());

  test('no stored tokens: starts logged out without calling the server', () async {
    final c = container(MemoryTokenStorage());
    final session = await c.read(sessionControllerProvider.future);
    expect(session.isLoggedIn, isFalse);
    expect(backend.sent, isEmpty);
  });

  test('stored tokens: restores the user from /users/me', () async {
    backend.on('GET /users/me', (_) => Reply(200, userJson()));
    final c = container(MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')));
    final session = await c.read(sessionControllerProvider.future);
    expect(session.user?.firstName, 'Rina');
    expect(session.user?.initials, 'RA');
  });

  test('stored tokens rejected by the server: logged out, tokens removed', () async {
    backend.on('GET /users/me', (_) => Reply(401, errorJson('UNAUTHORIZED')));
    backend.on('POST /auth/refresh', (_) => Reply(401, errorJson('INVALID_REFRESH_TOKEN')));
    final storage = MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r'));
    final c = container(storage);
    final session = await c.read(sessionControllerProvider.future);
    expect(session.isLoggedIn, isFalse);
    expect(session.expired, isFalse); // nothing was active yet: plain login screen
    expect(await storage.read(), isNull);
  });

  test('server unreachable at startup: error (splash shows the offline screen)', () async {
    backend.on('GET /users/me', (_) => Reply(503, errorJson('SERVICE_UNAVAILABLE')));
    final c = container(MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')));
    await expectLater(c.read(sessionControllerProvider.future), throwsA(isA<ApiException>()));
  });

  test('login stores tokens; register logs in after creating the account', () async {
    backend.on('POST /auth/register', (_) => Reply(201, userJson(name: 'Budi')));
    backend.on('POST /auth/login', (_) => Reply(200, tokensJson('a1', 'r1')));
    final storage = MemoryTokenStorage();
    final c = container(storage);
    await c.read(sessionControllerProvider.future);

    await c.read(sessionControllerProvider.notifier).register(
          displayName: 'Budi',
          email: 'budi@example.test',
          password: 'password123',
          passwordConfirmation: 'password123',
          role: 'student',
        );

    expect(c.read(currentUserProvider)?.email, 'rina@example.test');
    expect((await storage.read())?.accessToken, 'a1');
    final register = backend.sent.firstWhere((r) => r.path == '/auth/register');
    expect((register.body as Map)['user_role'], 'student');
  });

  test('session ended while using the app: state becomes expired', () async {
    backend.on('GET /users/me', (_) => Reply(200, userJson()));
    backend.on('GET /dashboard', (_) => Reply(401, errorJson('UNAUTHORIZED')));
    backend.on('POST /auth/refresh', (_) => Reply(401, errorJson('INVALID_REFRESH_TOKEN')));
    final c = container(MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')));
    expect((await c.read(sessionControllerProvider.future)).isLoggedIn, isTrue);

    await expectLater(c.read(dashboardProvider.future), throwsA(isA<ApiException>()));
    await Future<void>.delayed(Duration.zero);

    final session = c.read(sessionControllerProvider).value!;
    expect(session.expired, isTrue);
    expect(session.isLoggedIn, isFalse);
  });

  test('logout revokes on the server and forgets the tokens', () async {
    backend.on('GET /users/me', (_) => Reply(200, userJson()));
    backend.on('POST /auth/logout', (_) => const Reply(204));
    final storage = MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r'));
    final c = container(storage);
    await c.read(sessionControllerProvider.future);

    await c.read(sessionControllerProvider.notifier).logout();

    expect(backend.count('POST /auth/logout'), 1);
    expect(await storage.read(), isNull);
    expect(c.read(currentUserProvider), isNull);
  });

  test('dashboard parses the resume attempt', () async {
    backend.on('GET /dashboard', (_) => Reply(200, {
          'user': userJson(),
          'resume_attempt': {
            'attempt_id': '1',
            'exercise_id': '2',
            'skill': 'writing',
            'title': 'Describe your dream destination',
            'status': 'in_progress',
            'current_stage': 'writing',
          },
          'pending_attempts': [],
          'has_more_pending': false,
        }));
    final c = container(MemoryTokenStorage(const AuthTokens(accessToken: 'a', refreshToken: 'r')));
    final data = await c.read(dashboardProvider.future);
    expect(data.resumeAttempt?.skillLabel, 'Writing');
    expect(data.resumeAttempt?.title, 'Describe your dream destination');
  });
}
