import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';

import 'package:english_day/core/config/api_config.dart';
import 'package:english_day/core/network/api_exception.dart';
import 'package:english_day/core/storage/token_storage.dart';

/// HTTP client for the English Day backend (`/api/v1`).
///
/// - Adds `Authorization: Bearer <access token>` to every request unless `auth: false`.
/// - On 401 it refreshes the session ONCE and retries the request. The backend rotates
///   refresh tokens (an already-used one is rejected), so concurrent 401s share a
///   single refresh call instead of each sending their own.
/// - If the refresh itself is rejected, tokens are cleared and [sessionExpired] fires.
/// - Every failure is thrown as [ApiException].
class ApiClient {
  ApiClient({
    required TokenStorage storage,
    String? baseUrl,
    HttpClientAdapter? adapter,
  })  : _storage = storage,
        _dio = Dio(_options(baseUrl ?? ApiConfig.baseUrl)),
        _refreshDio = Dio(_options(baseUrl ?? ApiConfig.baseUrl)) {
    if (adapter != null) {
      _dio.httpClientAdapter = adapter;
      _refreshDio.httpClientAdapter = adapter;
    }
    _dio.interceptors.add(InterceptorsWrapper(onRequest: _onRequest, onError: _onError));
  }

  static BaseOptions _options(String baseUrl) => BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: ApiConfig.connectTimeout,
        receiveTimeout: ApiConfig.receiveTimeout,
        contentType: Headers.jsonContentType,
        responseType: ResponseType.json,
      );

  final TokenStorage _storage;
  final Dio _dio;
  final Dio _refreshDio; // no interceptors: a refresh must never trigger another refresh
  final _expired = StreamController<void>.broadcast();
  static const _uuid = Uuid();

  AuthTokens? _tokens;
  bool _loaded = false;
  Future<AuthTokens?>? _refreshing;

  /// Fires when the stored session can no longer be refreshed (user must log in again).
  Stream<void> get sessionExpired => _expired.stream;

  /// New key for one user action. Keep it and pass the SAME key when retrying that action.
  static String newIdempotencyKey() => _uuid.v4();

  // ------------------------------------------------------------------ session

  Future<AuthTokens?> currentTokens() async {
    if (!_loaded) {
      _tokens = await _storage.read();
      _loaded = true;
    }
    return _tokens;
  }

  Future<void> saveTokens(AuthTokens tokens) async {
    _tokens = tokens;
    _loaded = true;
    await _storage.write(tokens);
  }

  Future<void> clearTokens() async {
    _tokens = null;
    _loaded = true;
    await _storage.clear();
  }

  // ------------------------------------------------------------------ requests

  Future<dynamic> get(String path, {Map<String, dynamic>? query, bool auth = true}) =>
      _send(() => _dio.get(path, queryParameters: query, options: _opts(auth)));

  /// A binary download (e.g. private audio), with the same auth and refresh as [get].
  Future<Uint8List> getBytes(String path) async {
    final data = await _send(() => _dio.get<List<int>>(path,
        options: _opts(true).copyWith(responseType: ResponseType.bytes)));
    return data is Uint8List ? data : Uint8List.fromList(data as List<int>);
  }

  /// [idempotencyKey] is required by the backend on protected creation/submission POSTs.
  Future<dynamic> post(
    String path, {
    Object? data,
    bool auth = true,
    String? idempotencyKey,
  }) =>
      _send(() => _dio.post(path, data: data, options: _opts(auth, idempotencyKey)));

  Future<dynamic> patch(String path, {Object? data, String? idempotencyKey}) =>
      _send(() => _dio.patch(path, data: data, options: _opts(true, idempotencyKey)));

  Options _opts(bool auth, [String? idempotencyKey]) => Options(
        extra: {'auth': auth},
        headers: {if (idempotencyKey != null) 'Idempotency-Key': idempotencyKey},
      );

  Future<dynamic> _send(Future<Response<dynamic>> Function() call) async {
    try {
      return (await call()).data;
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  // ---------------------------------------------------------- interceptor hooks

  Future<void> _onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    if (options.extra['auth'] != false) {
      final tokens = await currentTokens();
      if (tokens != null) options.headers['Authorization'] = 'Bearer ${tokens.accessToken}';
    }
    handler.next(options);
  }

  Future<void> _onError(DioException error, ErrorInterceptorHandler handler) async {
    final request = error.requestOptions;
    final unauthorized = error.response?.statusCode == 401;
    if (!unauthorized || request.extra['auth'] == false || request.extra['retried'] == true) {
      return handler.next(error);
    }
    final usedHeader = request.headers['Authorization'];
    final current = await currentTokens();
    if (current == null) return handler.next(error);

    // Another request may already have refreshed while this one was in flight.
    AuthTokens? fresh = current;
    if (usedHeader == 'Bearer ${current.accessToken}') {
      fresh = await _refreshOnce(current.refreshToken);
    }
    if (fresh == null) return handler.next(error);

    try {
      request
        ..headers['Authorization'] = 'Bearer ${fresh.accessToken}'
        ..extra['retried'] = true;
      handler.resolve(await _dio.fetch<dynamic>(request));
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  /// Single-flight refresh. Returns null when the session is gone.
  Future<AuthTokens?> _refreshOnce(String refreshToken) {
    return _refreshing ??= _refresh(refreshToken).whenComplete(() => _refreshing = null);
  }

  Future<AuthTokens?> _refresh(String refreshToken) async {
    try {
      final res = await _refreshDio.post<dynamic>(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );
      final body = res.data as Map<String, dynamic>;
      final tokens = AuthTokens(
        accessToken: body['access_token'] as String,
        refreshToken: body['refresh_token'] as String,
      );
      await saveTokens(tokens);
      return tokens;
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      if (status == 401 || status == 400 || status == 422) {
        // The refresh token is invalid, revoked or expired: the session is over.
        await clearTokens();
        _expired.add(null);
      }
      // Network failures keep the tokens: the user is still logged in, just offline.
      return null;
    }
  }

  void dispose() {
    _expired.close();
    _dio.close();
    _refreshDio.close();
  }
}
