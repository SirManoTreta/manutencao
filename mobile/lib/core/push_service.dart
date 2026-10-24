import 'dart:async';
import 'dart:io';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'api_client.dart';

@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  // Android/iOS display the notification payload in background. Never access UI here.
}

abstract class MessagingDevice {
  Future<bool> requestPermission();
  Future<String?> token();
  Future<void> deleteToken();
  Stream<String> get refreshedTokens;
}

class FirebaseMessagingDevice implements MessagingDevice {
  @override
  Future<bool> requestPermission() async {
    final permission = await FirebaseMessaging.instance.requestPermission();
    if (![
      AuthorizationStatus.authorized,
      AuthorizationStatus.provisional,
    ].contains(permission.authorizationStatus)) {
      return false;
    }
    if (Platform.isIOS &&
        await FirebaseMessaging.instance.getAPNSToken() == null) {
      throw const ApiException(
        'Aguardando registro APNs. Tente novamente em instantes.',
      );
    }
    return true;
  }

  @override
  Future<String?> token() => FirebaseMessaging.instance.getToken();
  @override
  Future<void> deleteToken() => FirebaseMessaging.instance.deleteToken();
  @override
  Stream<String> get refreshedTokens =>
      FirebaseMessaging.instance.onTokenRefresh;
}

class PushService extends ChangeNotifier {
  PushService(this.api, {MessagingDevice? device})
    : _device = device ?? FirebaseMessagingDevice();
  final ApiClient api;
  final MessagingDevice _device;
  final pendingTicket = ValueNotifier<int?>(null);
  final _local = FlutterLocalNotificationsPlugin();
  final List<StreamSubscription<dynamic>> _subscriptions = [];
  Future<void> _operation = Future.value();
  String? _registeredToken, _activeSession;
  int _generation = 0;
  bool _active = false;
  bool _unregisterPending = false;
  bool available = false;
  String status = 'Notificações ainda não configuradas.';
  static const channel = AndroidNotificationChannel(
    'maintenance_tickets',
    'Novos chamados',
    description: 'Solicitações enviadas pelos computadores da escola',
    importance: Importance.high,
  );

  String get _currentSession => '${api.baseUrl}\u0000${api.token}';
  bool _valid(int generation) =>
      _active &&
      generation == _generation &&
      api.token != null &&
      _activeSession == _currentSession;
  Future<void> _serialize(Future<void> Function() task) {
    _operation = _operation.then((_) => task()).catchError((Object _) {
      status =
          'Falha ao configurar push. Verifique internet, servidor e Firebase.';
      notifyListeners();
    });
    return _operation;
  }

  void openTicket(dynamic id) {
    final parsed = int.tryParse('$id');
    if (parsed != null && parsed > 0) pendingTicket.value = parsed;
  }

  Future<void> initialize() async {
    if (!Platform.isAndroid && !Platform.isIOS) {
      status = 'Push disponível no Android e iOS.';
      return;
    }
    try {
      await Firebase.initializeApp().timeout(const Duration(seconds: 10));
      FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
      await _local.initialize(
        settings: const InitializationSettings(
          android: AndroidInitializationSettings('@drawable/ic_notification'),
          iOS: DarwinInitializationSettings(
            requestAlertPermission: false,
            requestBadgePermission: false,
            requestSoundPermission: false,
          ),
        ),
        onDidReceiveNotificationResponse: (response) =>
            openTicket(response.payload),
      );
      await _local
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >()
          ?.createNotificationChannel(channel);
      await FirebaseMessaging.instance
          .setForegroundNotificationPresentationOptions(
            alert: false,
            badge: false,
            sound: false,
          );
      final localLaunch = await _local.getNotificationAppLaunchDetails();
      if (localLaunch?.didNotificationLaunchApp == true) {
        openTicket(localLaunch?.notificationResponse?.payload);
      }
      final initial = await FirebaseMessaging.instance.getInitialMessage();
      if (initial != null) openTicket(initial.data['ticket_id']);
      _subscriptions.add(
        FirebaseMessaging.onMessageOpenedApp.listen(
          (message) => openTicket(message.data['ticket_id']),
        ),
      );
      _subscriptions.add(
        FirebaseMessaging.onMessage.listen((message) async {
          if (api.token == null) return;
          try {
            final id = int.tryParse('${message.data['ticket_id']}');
            await _local.show(
              id: id ?? 0,
              title: message.notification?.title ?? 'Novo chamado — TI',
              body:
                  message.notification?.body ??
                  '${message.data['pc_name'] ?? ''}: ${message.data['problem'] ?? 'Novo chamado'}',
              notificationDetails: NotificationDetails(
                android: AndroidNotificationDetails(
                  channel.id,
                  channel.name,
                  channelDescription: channel.description,
                  importance: Importance.high,
                  priority: Priority.high,
                ),
                iOS: const DarwinNotificationDetails(),
              ),
              payload: id?.toString(),
            );
          } catch (_) {
            status = 'Mensagem recebida; exibição bloqueada pelo sistema.';
            notifyListeners();
          }
        }),
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
            notifyListeners();
          },
        ),
      );
      available = true;
      status = 'Firebase disponível. Ative notificações neste dispositivo.';
    } catch (_) {
      status =
          'Firebase não configurado. Acesso ao sistema funciona; configure Firebase para receber push.';
    }
    notifyListeners();
  }

  Future<void> enable() {
    if (!available || api.token == null) return Future.value();
    if (!_active || _activeSession != _currentSession) {
      _generation++;
      _activeSession = _currentSession;
    }
    _active = true;
    final generation = _generation;
    return _serialize(() async {
      if (!_valid(generation)) return;
      if (!await _device.requestPermission()) {
        if (_valid(generation)) {
          status =
              'Permissão negada. Ative notificações nas configurações do celular.';
          notifyListeners();
        }
        return;
      }
      if (!_valid(generation)) return;
      final token = await _device.token().timeout(const Duration(seconds: 15));
      if (!_valid(generation)) return;
      if (token == null) {
        status = 'Token de notificações indisponível. Tente novamente.';
        notifyListeners();
      } else {
        await _register(token, generation);
      }
    });
  }

  Future<void> _register(String token, int generation) async {
    if (!_valid(generation)) return;
    await api.request(
      'POST',
      '/devices',
      body: {'token': token, 'platform': Platform.isIOS ? 'ios' : 'android'},
    );
    if (!_valid(generation)) return;
    if (_registeredToken != null && _registeredToken != token) {
      await api.request(
        'DELETE',
        '/devices',
        body: {'token': _registeredToken},
      );
    }
    if (!_valid(generation)) return;
    _registeredToken = token;
    status = 'Notificações ativas neste dispositivo.';
    notifyListeners();
  }

  Future<void> unregister() {
    pendingTicket.value = null;
    if (_unregisterPending || (!_active && _registeredToken == null)) {
      return _operation;
    }
    _unregisterPending = true;
    _active = false;
    _generation++;
    final oldSession = _activeSession;
    return _serialize(() async {
      try {
        final token =
            _registeredToken ??
            await _device.token().timeout(const Duration(seconds: 15));
        if (token != null &&
            api.token != null &&
            oldSession == _currentSession) {
          await api.request('DELETE', '/devices', body: {'token': token});
        }
      } catch (_) {
        /* Revoking native token still stops delivery when backend is offline. */
      }
      try {
        await _device.deleteToken().timeout(const Duration(seconds: 15));
        await _local.cancelAll();
      } catch (_) {}
      _registeredToken = null;
      _unregisterPending = false;
      status = 'Notificações desativadas neste dispositivo.';
      notifyListeners();
    });
  }

  @override
  void dispose() {
    for (final subscription in _subscriptions) {
      subscription.cancel();
    }
    pendingTicket.dispose();
    super.dispose();
  }
}
