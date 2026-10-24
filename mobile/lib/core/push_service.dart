import 'dart:async';
import 'dart:io';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import '../models/models.dart';
import '../models/ticket_notification.dart';
import 'api_client.dart';
import 'push_platform.dart';
export 'push_platform.dart'
    show MessagingDevice, FirebaseMessagingDevice, TicketNotificationPresenter;

class PushBackendStatus {
  const PushBackendStatus({
    required this.enabled,
    required this.credentialsConfigured,
    required this.activeDevices,
  });
  final bool enabled, credentialsConfigured;
  final int activeDevices;
  static PushBackendStatus? tryParse(dynamic value) {
    final data = object(value);
    if (data['enabled'] is! bool ||
        data['credentials_configured'] is! bool ||
        data['active_devices'] is! int ||
        data['active_devices'] < 0) {
      return null;
    }
    return PushBackendStatus(
      enabled: data['enabled'],
      credentialsConfigured: data['credentials_configured'],
      activeDevices: data['active_devices'],
    );
  }
}

class PushService extends ChangeNotifier {
  PushService(
    this.api, {
    MessagingDevice? device,
    TicketNotificationPresenter? notifications,
  }) : _device = device ?? FirebaseMessagingDevice(),
       _notifications = notifications ?? LocalTicketNotifications();
  final ApiClient api;
  final MessagingDevice _device;
  final TicketNotificationPresenter _notifications;
  final pendingTicket = ValueNotifier<int?>(null);
  final List<StreamSubscription<dynamic>> _subscriptions = [];
  final _foregroundSeen = <int>{};
  Future<void> _operation = Future.value();
  String? _registeredToken, _activeSession, _pendingOrigin;
  int _generation = 0;
  bool _active = false,
      _unregisterPending = false,
      _initialized = false,
      _disposed = false;
  bool available = false;
  bool permissionGranted = false;
  String? deviceName;
  DateTime? registeredAt;
  PushBackendStatus? backendStatus;
  String? backendStatusNotice;
  String status = 'Notificações ainda não configuradas.';

  String get _currentSession => '${api.baseUrl}\u0000${api.token}';
  bool get pendingOriginMatchesServer =>
      _pendingOrigin == null || _pendingOrigin == api.baseUrl;
  bool _valid(int generation) =>
      !_disposed &&
      _active &&
      generation == _generation &&
      api.token != null &&
      _activeSession == _currentSession;
  void _notify() {
    if (!_disposed) notifyListeners();
  }

  Future<void> _serialize(Future<void> Function() task) {
    _operation = _operation.then((_) => task()).catchError((Object error) {
      status = error is ApiException
          ? error.message
          : 'Falha ao configurar push. Verifique internet, servidor e Firebase.';
      _notify();
    });
    return _operation;
  }

  void discardPendingTicket() {
    _pendingOrigin = null;
    pendingTicket.value = null;
  }

  void handleNotificationOpened(Map<String, dynamic> data) {
    final notification = TicketNotification.tryParse(data);
    if (notification == null || _disposed) return;
    _pendingOrigin = api.baseUrl.isEmpty ? null : api.baseUrl;
    pendingTicket.value = notification.ticketId;
  }

  void handleLocalNotificationOpened(String? payload) {
    final notification = TicketNotification.fromLocalPayload(payload);
    if (notification == null) return;
    handleNotificationOpened({
      'type': 'new_ticket',
      'ticket_id': '${notification.ticketId}',
    });
  }

  Future<void> handleForegroundMessage(RemoteMessage message) async {
    final notification = TicketNotification.tryParse(message.data);
    final generation = _generation;
    if (notification == null ||
        !_valid(generation) ||
        !_foregroundSeen.add(notification.ticketId)) {
      return;
    }
    // WebSocket only refreshes pages. FCM alone owns the visible foreground alert.
    // Bound memory and scope this set to the current server/session generation.
    if (_foregroundSeen.length > 256) {
      _foregroundSeen.remove(_foregroundSeen.first);
    }
    try {
      await _notifications.show(
        notification,
        title: message.notification?.title,
        body: message.notification?.body,
      );
    } catch (_) {
      if (!_valid(generation)) return;
      _foregroundSeen.remove(notification.ticketId);
      status = 'Mensagem recebida; exibição bloqueada pelo sistema.';
      _notify();
    }
  }

  Future<void> initialize() async {
    if (_initialized || _disposed) return;
    if (!_device.supported) {
      status = 'Push disponível no Android e iOS.';
      _notify();
      return;
    }
    try {
      await _device.initialize();
      await _notifications.initialize(handleLocalNotificationOpened);
      _subscriptions.add(
        _device.openedMessages.listen(
          (message) => handleNotificationOpened(message.data),
        ),
      );
      _subscriptions.add(
        _device.foregroundMessages.listen(
          (message) => unawaited(handleForegroundMessage(message)),
          onError: (Object _) {
            status = 'Falha ao receber notificações. Tente ativar novamente.';
            _notify();
          },
        ),
      );
      _subscriptions.add(
        _device.refreshedTokens.listen(
          (token) {
            final generation = _generation;
            if (_valid(generation)) {
              unawaited(_serialize(() => _register(token, generation)));
            }
          },
          onError: (Object _) {
            status = 'Falha ao renovar notificações. Tente ativar novamente.';
            _notify();
          },
        ),
      );
      final localPayload = await _notifications.initialPayload();
      handleLocalNotificationOpened(localPayload);
      final initial = await _device.initialMessage();
      if (initial != null) handleNotificationOpened(initial.data);
      available = true;
      _initialized = true;
      status = 'Firebase disponível. Ative notificações neste dispositivo.';
    } catch (_) {
      for (final subscription in _subscriptions) {
        await subscription.cancel();
      }
      _subscriptions.clear();
      status =
          'Firebase não configurado neste aplicativo. Execute FlutterFire e compile com os arquivos nativos do projeto.';
    }
    _notify();
  }

  Future<void> enable() {
    if (!available || api.token == null) return Future.value();
    if (!_active || _activeSession != _currentSession) {
      _generation++;
      _activeSession = _currentSession;
      _foregroundSeen.clear();
      permissionGranted = false;
      registeredAt = null;
      backendStatus = null;
      backendStatusNotice = null;
      if (!pendingOriginMatchesServer) discardPendingTicket();
    }
    _active = true;
    final generation = _generation;
    return _serialize(() async {
      if (!_valid(generation)) return;
      final permission = await _device.requestPermission();
      if (!_valid(generation)) return;
      permissionGranted = permission;
      if (!permission) {
        status =
            'Permissão negada. Ative notificações nas configurações do celular.';
        _notify();
        return;
      }
      final token = await _device.token().timeout(const Duration(seconds: 15));
      if (!_valid(generation)) return;
      if (token == null || token.isEmpty) {
        status = 'Token de notificações indisponível. Tente novamente.';
        _notify();
      } else {
        await _register(token, generation);
      }
    });
  }

  Future<String> _readDeviceName() async {
    if (deviceName != null) return deviceName!;
    String name;
    try {
      name = await _device.deviceName().timeout(const Duration(seconds: 5));
    } catch (_) {
      name = Platform.isIOS ? 'iOS' : 'Android';
    }
    name = name.replaceAll(RegExp(r'[\x00-\x1f\x7f]'), ' ').trim();
    if (name.isEmpty) name = Platform.isIOS ? 'iOS' : 'Android';
    deviceName = name.length <= 120 ? name : name.substring(0, 120);
    return deviceName!;
  }

  Future<void> _register(String token, int generation) async {
    if (!_valid(generation) || !permissionGranted || token.isEmpty) return;
    final name = await _readDeviceName();
    if (!_valid(generation)) return;
    final response = object(
      await api.request(
        'POST',
        '/push/register',
        body: {
          'fcm_token': token,
          'platform': Platform.isIOS ? 'ios' : 'android',
          'device_name': name,
        },
      ),
    );
    if (!_valid(generation)) return;
    if (response['registered'] != true) {
      throw const ApiException(
        'Servidor não confirmou o registro de notificações. Verifique a versão da API.',
      );
    }
    if (_registeredToken != null && _registeredToken != token) {
      await api.request(
        'POST',
        '/push/unregister',
        body: {'fcm_token': _registeredToken},
      );
    }
    if (!_valid(generation)) return;
    _registeredToken = token;
    registeredAt = DateTime.now();
    status =
        'Registro confirmado no servidor. Entrega de push precisa de validação em aparelho.';
    _notify();
    await _loadBackendStatus(generation);
  }

  Future<void> _loadBackendStatus(int generation) async {
    try {
      final response = await api.request('GET', '/push/status');
      if (!_valid(generation)) return;
      backendStatus = PushBackendStatus.tryParse(response);
      backendStatusNotice = backendStatus == null
          ? 'Servidor não retornou diagnóstico válido.'
          : null;
    } catch (_) {
      if (!_valid(generation)) return;
      backendStatus = null;
      backendStatusNotice =
          'Diagnóstico do backend indisponível; registro do dispositivo permanece confirmado.';
    }
    _notify();
  }

  /// Explicit debug action for Firebase Console testing, never printed or logged.
  Future<String?> getDebugToken() async {
    final generation = _generation;
    if (!kDebugMode ||
        !available ||
        !permissionGranted ||
        !_valid(generation)) {
      throw const ApiException(
        'Entre e ative notificações antes de copiar o token de teste.',
      );
    }
    final token = await _device.token().timeout(const Duration(seconds: 15));
    if (!_valid(generation) || !permissionGranted) return null;
    return token;
  }

  Future<void> unregister() {
    discardPendingTicket();
    if (_unregisterPending || (!_active && _registeredToken == null)) {
      return _operation;
    }
    _unregisterPending = true;
    _active = false;
    _generation++;
    _foregroundSeen.clear();
    permissionGranted = false;
    final oldSession = _activeSession;
    return _serialize(() async {
      try {
        final token =
            _registeredToken ??
            await _device.token().timeout(const Duration(seconds: 15));
        if (token != null &&
            api.token != null &&
            oldSession == _currentSession) {
          await api.request(
            'POST',
            '/push/unregister',
            body: {'fcm_token': token},
          );
        }
      } catch (_) {
        /* Revoking the native token still stops delivery if server is offline. */
      }
      try {
        await _device.deleteToken().timeout(const Duration(seconds: 15));
        await _notifications.cancelAll();
      } catch (_) {}
      _registeredToken = null;
      _unregisterPending = false;
      registeredAt = null;
      backendStatus = null;
      backendStatusNotice = null;
      status = 'Notificações desativadas neste dispositivo.';
      _notify();
    });
  }

  @override
  void dispose() {
    _disposed = true;
    _active = false;
    _generation++;
    for (final subscription in _subscriptions) {
      subscription.cancel();
    }
    pendingTicket.dispose();
    super.dispose();
  }
}
