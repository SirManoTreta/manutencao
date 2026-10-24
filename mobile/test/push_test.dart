import 'dart:async';
import 'dart:convert';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:manutencao_mobile/core/api_client.dart';
import 'package:manutencao_mobile/core/push_service.dart';
import 'package:manutencao_mobile/models/ticket_notification.dart';

class FakeMessagingDevice implements MessagingDevice {
  Completer<String?>? tokenWait;
  final changes = StreamController<String>.broadcast();
  final foreground = StreamController<RemoteMessage>.broadcast();
  final opened = StreamController<RemoteMessage>.broadcast();
  int deletions = 0;
  bool permission = true, initializationFails = false;
  RemoteMessage? initial;
  @override
  bool get supported => true;
  @override
  Future<void> initialize() async {
    if (initializationFails) {
      throw StateError('No Firebase native configuration');
    }
  }

  @override
  Future<bool> requestPermission() async => permission;
  @override
  Future<String> deviceName() async => 'Samsung SM-A556B';
  @override
  Future<String?> token() => tokenWait?.future ?? Future.value('device-token');
  @override
  Future<void> deleteToken() async {
    deletions++;
  }

  @override
  Future<RemoteMessage?> initialMessage() async => initial;
  @override
  Stream<String> get refreshedTokens => changes.stream;
  @override
  Stream<RemoteMessage> get foregroundMessages => foreground.stream;
  @override
  Stream<RemoteMessage> get openedMessages => opened.stream;
  Future<void> close() async {
    await changes.close();
    await foreground.close();
    await opened.close();
  }
}

class FakeNotifications implements TicketNotificationPresenter {
  String? launchPayload;
  void Function(String?)? onTap;
  final shown = <TicketNotification>[];
  int cancellations = 0;
  bool failShowing = false;
  @override
  Future<void> initialize(void Function(String?) callback) async {
    onTap = callback;
  }

  @override
  Future<String?> initialPayload() async => launchPayload;
  @override
  Future<void> show(
    TicketNotification payload, {
    String? title,
    String? body,
  }) async {
    if (failShowing) throw StateError('Platform denied display');
    shown.add(payload);
  }

  @override
  Future<void> cancelAll() async {
    cancellations++;
  }
}

class PushFixture {
  final calls = <http.Request>[];
  final device = FakeMessagingDevice();
  final notifications = FakeNotifications();
  late final ApiClient api;
  late final PushService push;
  bool diagnosticFails = false;
  bool registrationConfirmed = true;
  PushFixture({bool authenticated = true}) {
    api =
        ApiClient(
            client: MockClient((request) async {
              calls.add(request);
              dynamic response;
              if (request.url.path.endsWith('/push/register')) {
                response = {'registered': registrationConfirmed};
              } else if (request.url.path.endsWith('/push/unregister')) {
                response = {'unregistered': true};
              } else if (request.url.path.endsWith('/push/status')) {
                if (diagnosticFails) {
                  return http.Response('{"detail":"Not Found"}', 404);
                }
                response = {
                  'enabled': true,
                  'credentials_configured': true,
                  'active_devices': 1,
                };
              }
              return http.Response(
                jsonEncode(response),
                200,
                headers: {'content-type': 'application/json'},
              );
            }),
          )
          ..baseUrl = 'https://school.example'
          ..token = authenticated ? 'session-one' : null;
    push = PushService(api, device: device, notifications: notifications);
  }
  List<http.Request> get registrations =>
      calls.where((c) => c.url.path.endsWith('/push/register')).toList();
  List<http.Request> get removals =>
      calls.where((c) => c.url.path.endsWith('/push/unregister')).toList();
  Future<void> initialize() => push.initialize();
  Future<void> close() async {
    push.dispose();
    api.dispose();
    await device.close();
  }
}

RemoteMessage message(int id, {String type = 'new_ticket'}) =>
    RemoteMessage(data: {'type': type, 'ticket_id': '$id'});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  group('Payload tipado', () {
    test('evento novo e legado preservam ID e dados úteis', () {
      for (final type in ['new_ticket', 'ticket_created']) {
        final parsed = TicketNotification.tryParse({
          'type': type,
          'ticket_id': '42',
          'room_name': '7º Ano A',
          'pc_name': 'PC-SALA07',
          'problem': 'Projetor sem imagem',
        });
        expect(parsed!.ticketId, 42);
        expect(parsed.fallbackBody, contains('7º Ano A'));
        expect(
          TicketNotification.fromLocalPayload(
            parsed.toLocalPayload(),
          )!.ticketId,
          42,
        );
      }
    });
    final invalid = <String, dynamic>{
      'ausente': null,
      'zero': '0',
      'negativo': '-1',
      'decimal': '1.5',
      'espaços': ' 42 ',
      'sinal': '+42',
      'número JSON': 42,
      'bool': true,
      'objeto': <String, dynamic>{},
      'fora de int64': '9223372036854775808',
    };
    for (final item in invalid.entries) {
      test('rejeita ticket_id ${item.key}', () {
        expect(
          TicketNotification.tryParse({
            'type': 'new_ticket',
            'ticket_id': item.value,
          }),
          isNull,
        );
      });
    }
    for (final type in [
      null,
      'ticket_taken',
      'ticket_closed',
      'announcement',
      'NEW_TICKET',
    ]) {
      test('rejeita evento $type', () {
        expect(
          TicketNotification.tryParse({'type': type, 'ticket_id': '42'}),
          isNull,
        );
      });
    }
    test('payload local precisa de JSON com evento validado', () {
      for (final payload in [
        null,
        '42',
        '{json inválido',
        '[]',
        '{"ticket_id":"42"}',
        '{"type":"new_ticket","ticket_id":42}',
      ]) {
        expect(TicketNotification.fromLocalPayload(payload), isNull);
      }
    });
  });

  test('registro envia contrato novo Bearer e metadados sem user_id', () async {
    final fixture = PushFixture();
    addTearDown(fixture.close);
    await fixture.initialize();
    await fixture.push.enable();
    final request = fixture.registrations.single;
    expect(request.method, 'POST');
    expect(request.headers['Authorization'], 'Bearer session-one');
    expect(jsonDecode(request.body), {
      'fcm_token': 'device-token',
      'platform': 'android',
      'device_name': 'Samsung SM-A556B',
    });
    expect(fixture.push.registeredAt, isNotNull);
    expect(fixture.push.backendStatus!.activeDevices, 1);
    expect(fixture.push.status, isNot(contains('device-token')));
  });

  test(
    'logout usa novo unregister idempotente e apaga destino pendente',
    () async {
      final fixture = PushFixture();
      addTearDown(fixture.close);
      await fixture.initialize();
      await fixture.push.enable();
      fixture.push.handleNotificationOpened(message(42).data);
      await fixture.push.unregister();
      await fixture.push.unregister();
      expect(fixture.removals.single.method, 'POST');
      expect(jsonDecode(fixture.removals.single.body), {
        'fcm_token': 'device-token',
      });
      expect(fixture.device.deletions, 1);
      expect(fixture.notifications.cancellations, 1);
      expect(fixture.push.pendingTicket.value, isNull);
      expect(fixture.push.permissionGranted, isFalse);
    },
  );

  test(
    'refresh registra token novo e desativa antigo na mesma sessão',
    () async {
      final fixture = PushFixture();
      addTearDown(fixture.close);
      await fixture.initialize();
      await fixture.push.enable();
      fixture.device.changes.add('new-device-token');
      await Future<void>.delayed(const Duration(milliseconds: 1));
      expect(fixture.registrations, hasLength(2));
      expect(
        jsonDecode(fixture.registrations.last.body)['fcm_token'],
        'new-device-token',
      );
      expect(
        jsonDecode(fixture.removals.single.body)['fcm_token'],
        'device-token',
      );
    },
  );

  test(
    'logout cancela token atrasado e novo login registra somente nova origem',
    () async {
      final fixture = PushFixture();
      addTearDown(fixture.close);
      await fixture.initialize();
      fixture.device.tokenWait = Completer<String?>();
      final enabling = fixture.push.enable();
      await Future<void>.delayed(Duration.zero);
      final disabling = fixture.push.unregister();
      fixture.api.baseUrl = 'https://other.example';
      fixture.api.token = 'new-session';
      final reEnabling = fixture.push.enable();
      fixture.device.tokenWait!.complete('old-device');
      await enabling;
      await disabling;
      await reEnabling;
      expect(fixture.registrations, hasLength(1));
      expect(fixture.registrations.single.url.host, 'other.example');
      expect(
        fixture.registrations.single.headers['Authorization'],
        'Bearer new-session',
      );
      expect(fixture.device.deletions, 1);
    },
  );

  test('permissão negada não registra nem copia token de teste', () async {
    final fixture = PushFixture();
    addTearDown(fixture.close);
    fixture.device.permission = false;
    await fixture.initialize();
    await fixture.push.enable();
    expect(fixture.calls, isEmpty);
    expect(fixture.push.status, contains('Permissão negada'));
    await expectLater(
      fixture.push.getDebugToken(),
      throwsA(isA<ApiException>()),
    );
    fixture.device.permission = true;
    await fixture.push.enable();
    expect(fixture.registrations, hasLength(1));
  });

  test('registro sem confirmação não declara sucesso', () async {
    final fixture = PushFixture();
    addTearDown(fixture.close);
    fixture.registrationConfirmed = false;
    await fixture.initialize();
    await fixture.push.enable();
    expect(fixture.push.registeredAt, isNull);
    expect(fixture.push.status, contains('não confirmou'));
  });

  test('diagnóstico indisponível preserva confirmação do registro', () async {
    final fixture = PushFixture();
    addTearDown(fixture.close);
    fixture.diagnosticFails = true;
    await fixture.initialize();
    await fixture.push.enable();
    expect(fixture.push.registeredAt, isNotNull);
    expect(fixture.push.backendStatus, isNull);
    expect(fixture.push.backendStatusNotice, contains('indisponível'));
  });

  test(
    'Firebase sem configuração mantém app utilizável e registro desativado',
    () async {
      final fixture = PushFixture();
      addTearDown(fixture.close);
      fixture.device.initializationFails = true;
      await fixture.initialize();
      await fixture.push.enable();
      expect(fixture.push.available, isFalse);
      expect(fixture.calls, isEmpty);
      expect(fixture.api.token, 'session-one');
      expect(fixture.push.status, contains('FlutterFire'));
    },
  );

  test(
    'FCM foreground duplica entrega mas apresenta apenas um alerta por chamado',
    () async {
      final fixture = PushFixture();
      addTearDown(fixture.close);
      await fixture.initialize();
      await fixture.push.enable();
      fixture.device.foreground.add(message(42));
      fixture.device.foreground.add(message(42));
      fixture.device.foreground.add(message(42, type: 'ticket_created'));
      fixture.device.foreground.add(message(43, type: 'ticket_closed'));
      await Future<void>.delayed(const Duration(milliseconds: 1));
      expect(fixture.notifications.shown.map((n) => n.ticketId), [42]);
      expect(fixture.push.pendingTicket.value, isNull);
      // New server/session starts its own event history even if ticket IDs overlap.
      await fixture.push.unregister();
      fixture.api.baseUrl = 'https://other.example';
      fixture.api.token = 'new-session';
      await fixture.push.enable();
      await fixture.push.handleForegroundMessage(message(42));
      expect(fixture.notifications.shown.map((n) => n.ticketId), [42, 42]);
    },
  );

  test('falha de exibição pode tentar novamente sem quebrar sessão', () async {
    final fixture = PushFixture();
    addTearDown(fixture.close);
    await fixture.initialize();
    await fixture.push.enable();
    fixture.notifications.failShowing = true;
    await fixture.push.handleForegroundMessage(message(42));
    fixture.notifications.failShowing = false;
    await fixture.push.handleForegroundMessage(message(42));
    expect(fixture.notifications.shown.single.ticketId, 42);
    expect(fixture.api.token, 'session-one');
  });

  test(
    'initialMessage e toque background validam evento antes de navegar',
    () async {
      final fixture = PushFixture(authenticated: false);
      addTearDown(fixture.close);
      fixture.device.initial = message(42);
      await fixture.initialize();
      expect(fixture.push.pendingTicket.value, 42);
      expect(fixture.push.pendingOriginMatchesServer, isTrue);
      fixture.push.discardPendingTicket();
      fixture.device.opened.add(message(43, type: 'announcement'));
      await Future<void>.delayed(Duration.zero);
      expect(fixture.push.pendingTicket.value, isNull);
      fixture.device.opened.add(message(44));
      await Future<void>.delayed(Duration.zero);
      expect(fixture.push.pendingTicket.value, 44);
      fixture.api.baseUrl = 'https://other.example';
      expect(fixture.push.pendingOriginMatchesServer, isFalse);
    },
  );

  test(
    'toque local usa JSON validado e ID desconhecido não entra na navegação',
    () async {
      final fixture = PushFixture();
      addTearDown(fixture.close);
      await fixture.initialize();
      fixture.notifications.onTap!('{"type":"ticket_closed","ticket_id":"42"}');
      expect(fixture.push.pendingTicket.value, isNull);
      fixture.notifications.onTap!(
        const TicketNotification(ticketId: 73).toLocalPayload(),
      );
      expect(fixture.push.pendingTicket.value, 73);
    },
  );

  test(
    'token debug requer sessão e desaparece se logout ocorre durante leitura',
    () async {
      final fixture = PushFixture(authenticated: false);
      addTearDown(fixture.close);
      await fixture.initialize();
      await expectLater(
        fixture.push.getDebugToken(),
        throwsA(isA<ApiException>()),
      );
      fixture.api.token = 'session';
      await fixture.push.enable();
      expect(await fixture.push.getDebugToken(), 'device-token');
      fixture.device.tokenWait = Completer<String?>();
      final pending = fixture.push.getDebugToken();
      await fixture.push.unregister();
      fixture.api.token = null;
      fixture.device.tokenWait!.complete('must-not-leak');
      expect(await pending, isNull);
    },
  );
}
