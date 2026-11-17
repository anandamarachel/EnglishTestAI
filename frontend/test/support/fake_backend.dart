import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

/// One recorded request.
class SentRequest {
  SentRequest(this.method, this.path, this.headers, this.body);
  final String method;
  final String path;
  final Map<String, dynamic> headers;
  final Object? body;
}

/// Reply for a request: status + JSON body (+ headers).
class Reply {
  const Reply(this.status, [this.body, this.headers = const {}]);
  final int status;
  final Object? body;
  final Map<String, List<String>> headers;
}

/// In-memory stand-in for the backend: routes "METHOD /path" to a handler.
/// Handlers may be async (e.g. to keep a refresh call pending).
class FakeBackend implements HttpClientAdapter {
  final routes = <String, Future<Reply> Function(SentRequest)>{};
  final sent = <SentRequest>[];

  void on(String route, Reply Function(SentRequest) handler) =>
      routes[route] = (r) async => handler(r);

  void onAsync(String route, Future<Reply> Function(SentRequest) handler) =>
      routes[route] = handler;

  int count(String route) =>
      sent.where((r) => '${r.method} ${r.path}' == route).length;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final request = SentRequest(
      options.method,
      options.uri.path.replaceFirst(RegExp(r'^/api/v1'), ''),
      Map.of(options.headers),
      options.data,
    );
    sent.add(request);
    final handler = routes['${request.method} ${request.path}'];
    final reply = handler == null
        ? const Reply(404, {'code': 'NOT_FOUND', 'message': 'no fake route', 'retryable': false, 'details': []})
        : await handler(request);
    return ResponseBody.fromString(
      reply.body == null ? '' : jsonEncode(reply.body),
      reply.status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
        ...reply.headers,
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Map<String, dynamic> userJson({String name = 'Rina Amelia'}) => {
      'user_id': '10000000-0000-4000-8000-000000000001',
      'email': 'rina@example.test',
      'display_name': name,
      'user_role': 'student',
      'created_at': '2026-11-09T08:00:00Z',
    };

Map<String, dynamic> tokensJson(String access, String refresh) => {
      'access_token': access,
      'token_type': 'bearer',
      'expires_in': 900,
      'refresh_token': refresh,
      'user': userJson(),
    };

Map<String, dynamic> errorJson(String code, {List<Map<String, String>> details = const []}) => {
      'code': code,
      'message': code,
      'request_id': '20000000-0000-4000-8000-000000000001',
      'retryable': false,
      'details': details,
    };
