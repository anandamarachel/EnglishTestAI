import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/storage/token_storage.dart';

import '../support/fake_backend.dart';

void main() {
  late FakeBackend backend;
  late MemoryTokenStorage storage;
  late ApiClient api;

  ApiClient client() =>
      ApiClient(storage: storage, baseUrl: 'http://test/api/v1', adapter: backend);

  setUp(() {
    backend = FakeBackend();
    storage = MemoryTokenStorage(
      const AuthTokens(accessToken: 'access-1', refreshToken: 'refresh-1'),
    );
    api = client();
  });
  tearDown(() => api.dispose());

  test('sends the stored access token', () async {
    backend.on('GET /users/me', (_) => Reply(200, userJson()));
    await api.get('/users/me');
    expect(backend.sent.single.headers['Authorization'], 'Bearer access-1');
  });

  test('auth: false sends no token (login/register)', () async {
    backend.on('POST /auth/login', (_) => Reply(200, tokensJson('a', 'r')));
    await api.post('/auth/login', auth: false, data: {'email': 'x@y.z', 'password': 'p'});
    expect(backend.sent.single.headers.containsKey('Authorization'), isFalse);
  });

  test('sends the Idempotency-Key header when given', () async {
    backend.on('POST /writing/exercises', (_) => const Reply(202, {}));
    final key = ApiClient.newIdempotencyKey();
    await api.post('/writing/exercises', data: {}, idempotencyKey: key);
    expect(backend.sent.single.headers['Idempotency-Key'], key);
  });

  test('on 401 refreshes once, stores the rotated tokens and retries', () async {
    backend.on('GET /users/me', (r) => r.headers['Authorization'] == 'Bearer access-2'
        ? Reply(200, userJson())
        : Reply(401, errorJson('UNAUTHORIZED')));
    backend.on('POST /auth/refresh', (r) {
      expect((r.body as Map)['refresh_token'], 'refresh-1');
      return Reply(200, tokensJson('access-2', 'refresh-2'));
    });

    final body = await api.get('/users/me') as Map;

    expect(body['display_name'], 'Rina Amelia');
    expect(backend.count('POST /auth/refresh'), 1);
    final saved = await storage.read();
    expect(saved?.accessToken, 'access-2');
    expect(saved?.refreshToken, 'refresh-2');
  });

  test('concurrent 401s share ONE refresh (the backend rotates refresh tokens)', () async {
    final release = Completer<void>();
    backend.on('GET /dashboard', (r) => r.headers['Authorization'] == 'Bearer access-2'
        ? const Reply(200, {'ok': true})
        : Reply(401, errorJson('UNAUTHORIZED')));
    backend.onAsync('POST /auth/refresh', (_) async {
      await release.future; // keep the first refresh in flight while others fail
      return Reply(200, tokensJson('access-2', 'refresh-2'));
    });

    final calls = [for (var i = 0; i < 3; i++) api.get('/dashboard')];
    await Future<void>.delayed(const Duration(milliseconds: 50));
    release.complete();
    final results = await Future.wait(calls);

    expect(results, everyElement(equals({'ok': true})));
    expect(backend.count('POST /auth/refresh'), 1);
  });

  test('rejected refresh clears the session and emits sessionExpired', () async {
    backend.on('GET /dashboard', (_) => Reply(401, errorJson('UNAUTHORIZED')));
    backend.on('POST /auth/refresh', (_) => Reply(401, errorJson('INVALID_REFRESH_TOKEN')));
    final expired = expectLater(api.sessionExpired, emits(null));

    await expectLater(
      api.get('/dashboard'),
      throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', 401)),
    );
    await expired;
    expect(await storage.read(), isNull);
  });

  test('a refresh that fails offline keeps the tokens (still logged in)', () async {
    backend.on('GET /dashboard', (_) => Reply(401, errorJson('UNAUTHORIZED')));
    backend.on('POST /auth/refresh', (_) => Reply(503, errorJson('SERVICE_UNAVAILABLE')));

    await expectLater(api.get('/dashboard'), throwsA(isA<ApiException>()));
    expect((await storage.read())?.refreshToken, 'refresh-1');
  });

  test('parses the error envelope, field details and Retry-After', () async {
    backend.on('POST /auth/register', (_) => Reply(
          422,
          errorJson('VALIDATION_ERROR', details: [
            {'field': 'email', 'message': 'value is not a valid email address'},
          ]),
        ));
    backend.on('POST /auth/login', (_) => Reply(429, errorJson('RATE_LIMITED'), {
          'retry-after': ['120'],
        }));

    final validation = await api
        .post('/auth/register', auth: false, data: {})
        .then<ApiException?>((_) => null, onError: (Object e) => e as ApiException);
    expect(validation!.code, 'VALIDATION_ERROR');
    expect(validation.details.single.field, 'email');

    final limited = await api
        .post('/auth/login', auth: false, data: {})
        .then<ApiException?>((_) => null, onError: (Object e) => e as ApiException);
    expect(limited!.code, 'RATE_LIMITED');
    expect(limited.retryAfter, const Duration(seconds: 120));
    expect(limited.userMessage, contains('2 menit'));
  });
}
