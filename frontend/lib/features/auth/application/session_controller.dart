import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/providers.dart';
import 'package:english_day/features/auth/data/auth_repository.dart';
import 'package:english_day/features/auth/data/user.dart';

/// Who is using the app right now.
class Session {
  const Session._(this.user, {this.expired = false});

  const Session.loggedOut() : this._(null);
  const Session.loggedIn(User user) : this._(user);

  /// The server ended a session that was active in this app run (token revoked or
  /// expired). The app shows the "Sesimu sudah berakhir" sheet for this state.
  const Session.expired() : this._(null, expired: true);

  final User? user;
  final bool expired;
  bool get isLoggedIn => user != null;
}

/// App-wide session. Restores a stored session at startup (splash screen); login,
/// register and logout go through here so every screen sees the same user.
///
/// While starting up, an unreachable server leaves this in AsyncError (the splash
/// screen shows the offline screen); a rejected session ends as logged out.
class SessionController extends AsyncNotifier<Session> {
  AuthRepository get _repo => ref.read(authRepositoryProvider);

  @override
  Future<Session> build() async {
    final sub = ref.read(apiClientProvider).sessionExpired.listen((_) {
      final wasLoggedIn = state.valueOrNull?.isLoggedIn ?? false;
      state = AsyncData(wasLoggedIn ? const Session.expired() : const Session.loggedOut());
    });
    ref.onDispose(sub.cancel);

    if (!await _repo.hasStoredSession()) return const Session.loggedOut();
    try {
      return Session.loggedIn(await _repo.me());
    } catch (e) {
      // me() already refreshed on 401; if the refresh was rejected the tokens are
      // cleared, so this is a normal logged-out start. Anything else (offline,
      // server down) is rethrown for the splash screen to show.
      if (!await _repo.hasStoredSession()) return const Session.loggedOut();
      rethrow;
    }
  }

  Future<User> login({required String email, required String password}) async {
    final user = await _repo.login(email: email, password: password);
    state = AsyncData(Session.loggedIn(user));
    return user;
  }

  /// Registers, then logs in with the same credentials (register returns no tokens).
  Future<User> register({
    required String displayName,
    required String email,
    required String password,
    required String passwordConfirmation,
    required String role,
  }) async {
    await _repo.register(
      displayName: displayName,
      email: email,
      password: password,
      passwordConfirmation: passwordConfirmation,
      role: role,
    );
    return login(email: email, password: password);
  }

  Future<void> logout() async {
    await _repo.logout();
    state = const AsyncData(Session.loggedOut());
  }

  /// Retry a startup that failed because the server was unreachable.
  Future<void> retryRestore() async {
    state = const AsyncLoading();
    ref.invalidateSelf();
    await future;
  }
}

final sessionControllerProvider =
    AsyncNotifierProvider<SessionController, Session>(SessionController.new);

/// The logged-in user, or null. Convenience for screens that only display it.
final currentUserProvider = Provider<User?>(
  (ref) => ref.watch(sessionControllerProvider).valueOrNull?.user,
);
