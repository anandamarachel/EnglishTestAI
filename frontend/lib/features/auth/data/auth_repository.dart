import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/network/providers.dart';
import 'package:english_day/core/storage/token_storage.dart';
import 'package:english_day/features/auth/data/user.dart';

/// Account endpoints (`/auth/*`, `/users/me`).
class AuthRepository {
  AuthRepository(this._api);
  final ApiClient _api;

  Future<bool> hasStoredSession() async => await _api.currentTokens() != null;

  /// Logs in and stores the tokens. Throws ApiException (INVALID_CREDENTIALS, ...).
  Future<User> login({required String email, required String password}) async {
    final body = await _api.post(
      '/auth/login',
      auth: false,
      data: {'email': email.trim(), 'password': password}, // passwords are never trimmed
    ) as Map<String, dynamic>;
    await _api.saveTokens(AuthTokens(
      accessToken: body['access_token'] as String,
      refreshToken: body['refresh_token'] as String,
    ));
    return User.fromJson(body['user'] as Map<String, dynamic>);
  }

  /// Creates the account (does not log in). Throws ApiException
  /// (EMAIL_ALREADY_REGISTERED, VALIDATION_ERROR with field details, ...).
  Future<User> register({
    required String displayName,
    required String email,
    required String password,
    required String passwordConfirmation,
    required String role,
  }) async {
    final body = await _api.post('/auth/register', auth: false, data: {
      'display_name': displayName.trim(),
      'email': email.trim(),
      'password': password,
      'password_confirmation': passwordConfirmation,
      'user_role': role,
    }) as Map<String, dynamic>;
    return User.fromJson(body);
  }

  Future<User> me() async =>
      User.fromJson(await _api.get('/users/me') as Map<String, dynamic>);

  /// Revokes the session on the server (best effort) and always forgets it locally.
  Future<void> logout() async {
    try {
      if (await _api.currentTokens() != null) await _api.post('/auth/logout');
    } catch (_) {
      // Offline or already revoked: the local logout below is what matters.
    } finally {
      await _api.clearTokens();
    }
  }
}

final authRepositoryProvider =
    Provider<AuthRepository>((ref) => AuthRepository(ref.watch(apiClientProvider)));
