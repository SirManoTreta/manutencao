import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/models.dart';
import 'api_client.dart';

abstract class SessionStorage {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class SecureSessionStorage implements SessionStorage {
  final _storage = const FlutterSecureStorage();
  @override
  Future<String?> read(String key) => _storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class SessionController extends ChangeNotifier {
  SessionController(this.api, this.storage) {
    api.onUnauthorized = expire;
  }
  final ApiClient api;
  final SessionStorage storage;
  AppUser? user;
  bool busy = false;
  String? error;
  String? notice;
  int generation = 0;
  bool get authenticated => user != null && api.token != null;

  Future<void> restore() async {
    try {
      api.baseUrl = await storage.read('server') ?? '';
      api.token = await storage.read('token');
      if (api.token == null || api.baseUrl.isEmpty) return;
      final cached = await storage.read('user');
      if (cached != null) user = AppUser.fromJson(object(jsonDecode(cached)));
      try {
        user = AppUser.fromJson(object(await api.request('GET', '/auth/me')));
        await storage.write('user', jsonEncode(user!.toJson()));
      } on ApiException catch (e) {
        if (e.status == 401) {
          await clear();
        } else {
          notice =
              'Sem conexão com o servidor. Dados serão recarregados ao reconectar.';
        }
      }
    } catch (_) {
      user = null;
      api.token = null;
      error = 'Não foi possível restaurar a sessão. Entre novamente.';
    }
    notifyListeners();
  }

  Future<bool> login(String server, String username, String password) async {
    if (busy) return false;
    busy = true;
    error = null;
    notice = null;
    notifyListeners();
    try {
      api.baseUrl = ApiClient.normalizeBaseUrl(server);
      await storage.write('server', api.baseUrl);
      final response = object(
        await api.request(
          'POST',
          '/auth/login',
          body: {'username': username.trim(), 'password': password},
          auth: false,
        ),
      );
      final newToken = response['access_token'] as String;
      final newUser = AppUser.fromJson(object(response['user']));
      await storage.write('token', newToken);
      await storage.write('user', jsonEncode(newUser.toJson()));
      api.token = newToken;
      user = newUser;
      generation++;
      return true;
    } catch (e) {
      error = e is ApiException
          ? e.message
          : 'Não foi possível entrar. Tente novamente.';
      return false;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  void expire() {
    if (api.token == null) return;
    notice = 'Sessão expirada. Entre novamente.';
    user = null;
    api.token = null;
    generation++;
    storage.delete('token');
    storage.delete('user');
    notifyListeners();
  }

  Future<void> clear() async {
    user = null;
    api.token = null;
    generation++;
    await storage.delete('token');
    await storage.delete('user');
    notifyListeners();
  }

  Future<void> logout() async {
    try {
      await api.request('POST', '/auth/logout');
    } on ApiException {
      notice =
          'Sessão local encerrada. Servidor indisponível para revogar token.';
    } finally {
      await clear();
    }
  }
}
