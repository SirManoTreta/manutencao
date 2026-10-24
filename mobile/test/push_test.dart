import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:manutencao_mobile/core/api_client.dart';
import 'package:manutencao_mobile/core/push_service.dart';

class FakeMessagingDevice implements MessagingDevice {
  Completer<String?>? tokenWait;
  final changes = StreamController<String>.broadcast();
  int deletions = 0;
  bool permission = true;
  @override
  Future<bool> requestPermission() async => permission;
  @override
  Future<String?> token() => tokenWait?.future ?? Future.value('device-token');
  @override
  Future<void> deleteToken() async {
    deletions++;
  }

  @override
  Stream<String> get refreshedTokens => changes.stream;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('push registers Bearer device and logout is idempotent', () async {
    final calls = <http.Request>[];
    final api =
        ApiClient(
            client: MockClient((request) async {
              calls.add(request);
              return http.Response('{}', 200);
            }),
          )
          ..baseUrl = 'https://school.example'
          ..token = 'session-one';
    final device = FakeMessagingDevice();
    final push = PushService(api, device: device)..available = true;
    await push.enable();
    expect(calls.single.method, 'POST');
    expect(calls.single.headers['Authorization'], 'Bearer session-one');
    push.openTicket('42');
    await push.unregister();
    await push.unregister();
    expect(device.deletions, 1);
    expect(calls.where((c) => c.method == 'DELETE'), hasLength(1));
    expect(push.pendingTicket.value, isNull);
    push.dispose();
    api.dispose();
    await device.changes.close();
  });

  test(
    'logout cancels pending token registration and queued login gets new session',
    () async {
      final calls = <http.Request>[];
      final api =
          ApiClient(
              client: MockClient((request) async {
                calls.add(request);
                return http.Response('{}', 200);
              }),
            )
            ..baseUrl = 'https://school.example'
            ..token = 'old-session';
      final device = FakeMessagingDevice()..tokenWait = Completer<String?>();
      final push = PushService(api, device: device)..available = true;
      final enabling = push.enable();
      await Future<void>.delayed(Duration.zero);
      final disabling = push.unregister();
      // User enters another server before a delayed native token resolves.
      api.baseUrl = 'https://other.example';
      api.token = 'new-session';
      final reEnabling = push.enable();
      device.tokenWait!.complete('old-device');
      await enabling;
      await disabling;
      await reEnabling;
      expect(calls.where((c) => c.method == 'POST'), hasLength(1));
      expect(calls.single.url.host, 'other.example');
      expect(calls.single.headers['Authorization'], 'Bearer new-session');
      expect(device.deletions, 1);
      push.dispose();
      api.dispose();
      await device.changes.close();
    },
  );

  test('permission denied never registers device', () async {
    var requests = 0;
    final api =
        ApiClient(
            client: MockClient((_) async {
              requests++;
              return http.Response('{}', 200);
            }),
          )
          ..baseUrl = 'https://school.example'
          ..token = 'session';
    final device = FakeMessagingDevice()..permission = false;
    final push = PushService(api, device: device)..available = true;
    await push.enable();
    expect(requests, 0);
    expect(push.status, contains('Permissão negada'));
    push.dispose();
    api.dispose();
    await device.changes.close();
  });

  test('pending notification accepts positive ticket IDs only', () {
    final api = ApiClient();
    final push = PushService(api);
    push.openTicket('not-an-id');
    expect(push.pendingTicket.value, isNull);
    push.openTicket(-2);
    expect(push.pendingTicket.value, isNull);
    push.openTicket('73');
    expect(push.pendingTicket.value, 73);
    push.dispose();
    api.dispose();
  });
}
