import 'package:dio/dio.dart';

/// One field problem from a backend `VALIDATION_ERROR` (or similar) response.
class FieldError {
  const FieldError(this.field, this.message);
  final String field;
  final String message;
}

/// Every failed API call surfaces as this, so screens handle one error type.
///
/// Backend errors always look like `{code, message, request_id, retryable, details}`.
/// Connection problems use the client-side codes [network] and [timeout].
class ApiException implements Exception {
  const ApiException({
    required this.code,
    required this.message,
    this.statusCode,
    this.retryable = false,
    this.details = const [],
    this.requestId,
    this.retryAfter,
  });

  static const network = 'NETWORK_ERROR';
  static const timeout = 'TIMEOUT';
  static const unknown = 'UNKNOWN_ERROR';

  final String code;

  /// Backend message (English, for logs). Show [userMessage] in the UI instead.
  final String message;
  final int? statusCode;
  final bool retryable;
  final List<FieldError> details;
  final String? requestId;

  /// From the `Retry-After` header on 429/503.
  final Duration? retryAfter;

  bool get isUnauthorized => statusCode == 401;

  factory ApiException.fromDio(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return const ApiException(code: timeout, message: 'Request timed out.', retryable: true);
      case DioExceptionType.connectionError:
        return const ApiException(code: network, message: 'Cannot reach server.', retryable: true);
      case DioExceptionType.badResponse:
        return ApiException.fromResponse(e.response!);
      default:
        final inner = e.error;
        if (inner is ApiException) return inner;
        return ApiException(code: network, message: e.message ?? 'Request failed.', retryable: true);
    }
  }

  factory ApiException.fromResponse(Response<dynamic> response) {
    final body = response.data;
    final seconds = int.tryParse(response.headers.value('retry-after') ?? '');
    final retryAfter = seconds == null ? null : Duration(seconds: seconds);
    if (body is Map && body['code'] is String) {
      return ApiException(
        code: body['code'] as String,
        message: (body['message'] as String?) ?? '',
        statusCode: response.statusCode,
        retryable: body['retryable'] == true,
        requestId: body['request_id'] as String?,
        retryAfter: retryAfter,
        details: [
          for (final d in (body['details'] as List?) ?? const [])
            if (d is Map) FieldError('${d['field']}', '${d['message']}'),
        ],
      );
    }
    return ApiException(
      code: unknown,
      message: 'HTTP ${response.statusCode}',
      statusCode: response.statusCode,
      retryable: (response.statusCode ?? 0) >= 500,
      retryAfter: retryAfter,
    );
  }

  /// The session is gone (tokens rejected). The app-wide "Sesimu sudah berakhir"
  /// sheet handles this, so screens should not show their own error for it.
  bool get isSessionEnded => code == 'UNAUTHORIZED' || code == 'INVALID_REFRESH_TOKEN';

  /// Indonesian text for banners/snackbars. Screens may special-case codes first
  /// (e.g. INVALID_CREDENTIALS on the login screen).
  String get userMessage {
    switch (code) {
      case network:
        return 'Tidak bisa terhubung ke server. Periksa koneksimu, lalu coba lagi.';
      case timeout:
        return 'Server terlalu lama merespons. Coba lagi dalam beberapa saat.';
      case 'RATE_LIMITED':
        final wait = retryAfter;
        return wait == null
            ? 'Terlalu banyak percobaan. Tunggu sebentar, lalu coba lagi.'
            : 'Terlalu banyak percobaan. Coba lagi dalam ${_humanize(wait)}.';
      case 'SERVICE_UNAVAILABLE':
        return 'Server sedang sibuk. Coba lagi dalam beberapa saat.';
      case 'UNAUTHORIZED':
      case 'INVALID_REFRESH_TOKEN':
        return 'Sesimu sudah berakhir. Masuk lagi untuk melanjutkan.';
      case 'VALIDATION_ERROR':
        return 'Data yang dikirim belum sesuai. Periksa kembali isianmu.';
      case 'CAPACITY_EXCEEDED':
        return 'Data terlalu besar untuk diproses.';
      case 'NOT_FOUND':
        return 'Data tidak ditemukan.';
    }
    return 'Terjadi kesalahan. Coba lagi dalam beberapa saat.';
  }

  static String _humanize(Duration d) =>
      d.inSeconds < 60 ? '${d.inSeconds} detik' : '${(d.inSeconds / 60).ceil()} menit';

  @override
  String toString() => 'ApiException($statusCode $code: $message${requestId == null ? '' : ', request_id=$requestId'})';
}
