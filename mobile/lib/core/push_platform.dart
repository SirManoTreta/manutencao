import 'dart:io';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import '../models/ticket_notification.dart';
import 'api_client.dart';
import 'firebase_bootstrap.dart';

@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  if (TicketNotification.tryParse(message.data) == null) return;
  await initializeMaintenanceFirebase();
  // Android/iOS present the notification payload. This isolate never opens UI
  // or produces a second notification for the same background delivery.
}

abstract class MessagingDevice {
  bool get supported;
  Future<void> initialize();
  Future<bool> requestPermission();
  Future<String> deviceName();
  Future<String?> token();
  Future<void> deleteToken();
  Future<RemoteMessage?> initialMessage();
  Stream<String> get refreshedTokens;
  Stream<RemoteMessage> get foregroundMessages;
  Stream<RemoteMessage> get openedMessages;
}

class FirebaseMessagingDevice implements MessagingDevice {
  @override
  bool get supported => Platform.isAndroid || Platform.isIOS;
  @override
  Future<void> initialize() async {
    await initializeMaintenanceFirebase().timeout(const Duration(seconds: 10));
    FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
    // Foreground uses one local alert. Background is presented by the OS.
    await FirebaseMessaging.instance
        .setForegroundNotificationPresentationOptions(
          alert: false,
          badge: false,
          sound: false,
        );
  }

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
  Future<String> deviceName() async {
    final info = DeviceInfoPlugin();
    if (Platform.isAndroid) {
      final android = await info.androidInfo;
      return '${android.manufacturer} ${android.model}';
    }
    if (Platform.isIOS) {
      final ios = await info.iosInfo;
      // User-assigned names on iOS 16+ require an extra entitlement. Hardware
      // model is sufficient for device management and needs no such access.
      return '${ios.model} (${ios.utsname.machine})';
    }
    return Platform.operatingSystem;
  }

  @override
  Future<String?> token() => FirebaseMessaging.instance.getToken();
  @override
  Future<void> deleteToken() => FirebaseMessaging.instance.deleteToken();
  @override
  Future<RemoteMessage?> initialMessage() => FirebaseMessaging.instance
      .getInitialMessage()
      .timeout(const Duration(seconds: 10));
  @override
  Stream<String> get refreshedTokens =>
      FirebaseMessaging.instance.onTokenRefresh;
  @override
  Stream<RemoteMessage> get foregroundMessages => FirebaseMessaging.onMessage;
  @override
  Stream<RemoteMessage> get openedMessages =>
      FirebaseMessaging.onMessageOpenedApp;
}

abstract class TicketNotificationPresenter {
  Future<void> initialize(void Function(String?) onTap);
  Future<String?> initialPayload();
  Future<void> show(TicketNotification payload, {String? title, String? body});
  Future<void> cancelAll();
}

class LocalTicketNotifications implements TicketNotificationPresenter {
  final _local = FlutterLocalNotificationsPlugin();
  static const channel = AndroidNotificationChannel(
    'maintenance_tickets',
    'Novos chamados',
    description: 'Solicitações enviadas pelos computadores da escola',
    importance: Importance.high,
  );
  @override
  Future<void> initialize(void Function(String?) onTap) async {
    await _local.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@drawable/ic_notification'),
        iOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
      ),
      onDidReceiveNotificationResponse: (response) => onTap(response.payload),
    );
    await _local
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.createNotificationChannel(channel);
  }

  @override
  Future<String?> initialPayload() async {
    final launch = await _local.getNotificationAppLaunchDetails();
    return launch?.didNotificationLaunchApp == true
        ? launch?.notificationResponse?.payload
        : null;
  }

  @override
  Future<void> show(
    TicketNotification payload, {
    String? title,
    String? body,
  }) => _local.show(
    id: payload.ticketId & 0x7fffffff,
    title: title ?? 'Novo chamado — TI',
    body: body ?? payload.fallbackBody,
    notificationDetails: NotificationDetails(
      android: AndroidNotificationDetails(
        channel.id,
        channel.name,
        channelDescription: channel.description,
        importance: Importance.high,
        priority: Priority.high,
        tag: 'ticket_${payload.ticketId}',
      ),
      iOS: const DarwinNotificationDetails(),
    ),
    payload: payload.toLocalPayload(),
  );
  @override
  Future<void> cancelAll() => _local.cancelAll();
}
