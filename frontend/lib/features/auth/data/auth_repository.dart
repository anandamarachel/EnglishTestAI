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

  /// `PATCH /users/me`: only the display name can change.
  Future<User> updateDisplayName(String displayName) async => User.fromJson(await _api
      .patch('/users/me', data: {'display_name': displayName.trim()}) as Map<String, dynamic>);

  /// `POST /auth/password/change`. The server then revokes every session, this one
  /// included, so the local tokens are dropped too. A wrong current password is a
  /// VALIDATION_ERROR on `current_password` (not 401).
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
    required String passwordConfirmation,
  }) async {
    await _api.post('/auth/password/change', data: {
      'current_password': currentPassword,
      'new_password': newPassword,
      'password_confirmation': passwordConfirmation,
    });
    await _api.clearTokens();
  }

  /// `POST /auth/password/forgot`: always "accepted", known email or not.
  Future<void> forgotPassword(String email) =>
      _api.post('/auth/password/forgot', auth: false, data: {'email': email.trim()});

  /// `POST /auth/password/reset` with the code from the email. Revokes every
  /// session; an invalid or expired code is INVALID_RESET_TOKEN.
  Future<void> resetPassword({
    required String token,
    required String newPassword,
    required String passwordConfirmation,
  }) async {
    await _api.post('/auth/password/reset', auth: false, data: {
      'token': token.trim(),
      'new_password': newPassword,
      'password_confirmation': passwordConfirmation,
    });
    await _api.clearTokens();
  }

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
