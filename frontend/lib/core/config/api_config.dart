import 'package:flutter/foundation.dart';

/// Where the backend API lives.
///
/// Override at build/run time (or put it in frontend/.env, see .env.example):
///   flutter run --dart-define-from-file=.env
///   flutter run --dart-define=API_BASE_URL=http://192.168.1.20:8000/api/v1
///
/// Defaults reach a backend started with `make start` on this computer:
/// - Android emulator: 10.0.2.2 is the emulator's name for the host computer.
/// - Chrome, Windows, iOS simulator: localhost.
class ApiConfig {
  ApiConfig._();

  static const _override = String.fromEnvironment('API_BASE_URL');

  static String get baseUrl {
    if (_override.isNotEmpty) return _override;
    final isAndroid = !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
    return isAndroid ? 'http://10.0.2.2:8000/api/v1' : 'http://localhost:8000/api/v1';
  }

  /// Normal API calls. AI work never blocks a request (the backend returns a job
  /// to poll), so these stay short; uploads/downloads may pass their own timeouts.
  static const connectTimeout = Duration(seconds: 15);
  static const receiveTimeout = Duration(seconds: 30);
}
