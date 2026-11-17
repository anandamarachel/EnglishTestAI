import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/network/api_client.dart';
import 'package:english_day/core/storage/token_storage.dart';

/// Overridden in tests and the design gallery with [MemoryTokenStorage].
final tokenStorageProvider = Provider<TokenStorage>((ref) => SecureTokenStorage());

/// One client for the whole app (shares the token cache and the refresh lock).
final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(storage: ref.watch(tokenStorageProvider));
  ref.onDispose(client.dispose);
  return client;
});
