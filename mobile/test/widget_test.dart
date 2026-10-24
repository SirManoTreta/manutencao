import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:manutencao_mobile/app.dart';
import 'package:manutencao_mobile/core/api_client.dart';
import 'package:manutencao_mobile/core/push_service.dart';
import 'package:manutencao_mobile/core/realtime.dart';
import 'package:manutencao_mobile/core/session.dart';
import 'package:manutencao_mobile/features/dashboard.dart';
import 'package:manutencao_mobile/models/models.dart';

class MemoryStorage implements SessionStorage {
  final values = <String, String>{};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }
}

class OfflineRealtime extends TicketRealtime {
  OfflineRealtime(super.api);
  @override
  void start() {}
  @override
  void stop() {}
}

class Fixture {
  late final ApiClient api;
  late final SessionController session;
  late final PushService push;
  late final TicketRealtime realtime;
  final requests = <http.Request>[];
  String ticketStatus = 'OPEN';
  Fixture({bool authenticated = true}) {
    api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        final path = request.url.path;
        final ticket = {
          'id': 42,
          'pc_name': 'PC-01',
          'room_name': '7º Ano A',
          'problem': 'Projetor sem imagem',
          'status': ticketStatus,
          'assigned_by': ticketStatus == 'OPEN' ? null : 'outro.tecnico',
          'created_at': '2026-10-23T15:00:00Z',
        };
        final machine = {
          'id': 7,
          'machine_name': 'PC-01',
          'room_name': '7º Ano A',
          'ip': '192.168.0.15',
          'username': 'professor',
          'profile': 'A',
          'room_status': 'OK',
          'peripherals': [],
        };
        dynamic result = <String, dynamic>{};
        if (path.endsWith('/auth/login')) {
          result = {
            'access_token': 'bearer-token',
            'user': {'id': 1, 'username': 'tecnico', 'is_admin': true},
          };
        } else if (path.endsWith('/dashboard')) {
          result = {
            'total_machines': 12,
            'online_count': 8,
            'open_tickets': 3,
            'in_progress_tickets': 1,
            'pending_inspections': 7,
            'pending_checkups': 5,
            'recent_tickets': [ticket],
            'recent_machines': [machine],
          };
        } else if (path.endsWith('/tickets/42/take')) {
          ticketStatus = 'IN_PROGRESS';
        } else if (path.endsWith('/tickets/42/close')) {
          ticketStatus = 'CLOSED';
        } else if (path.endsWith('/tickets/42')) {
          result = ticket;
        } else if (path.endsWith('/tickets')) {
          result = [ticket];
        } else if (path.endsWith('/machines/7')) {
          result = machine;
        } else if (path.endsWith('/machines')) {
          result = [machine];
        } else if (path.endsWith('/rooms')) {
          result = [
            {'room_name': '7º Ano A', 'room_status': 'OK', 'machine_count': 1},
          ];
        } else if (path.endsWith('/online')) {
          result = [];
        }
        return http.Response(
          jsonEncode(result),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    )..baseUrl = 'http://school.example';
    session = SessionController(api, MemoryStorage());
    if (authenticated) {
      api.token = 'bearer-token';
      session.user = const AppUser(id: 1, username: 'tecnico', isAdmin: true);
    }
    push = PushService(api);
    realtime = OfflineRealtime(api);
  }
  Widget app() =>
      MaintenanceApp(session: session, push: push, realtime: realtime);
  void dispose() {
    session.dispose();
    push.dispose();
    realtime.dispose();
    api.dispose();
  }
}

void main() {
  testWidgets(
    'login validates inputs and authenticates through configured server',
    (tester) async {
      final fixture = Fixture(authenticated: false);
      addTearDown(fixture.dispose);
      await tester.pumpWidget(fixture.app());
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Entrar'));
      await tester.tap(find.text('Entrar'));
      await tester.pumpAndSettle();
      expect(find.text('Informe o usuário'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Usuário'),
        'tecnico',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Senha'),
        'secret',
      );
      await tester.ensureVisible(find.text('Entrar'));
      await tester.tap(find.text('Entrar'));
      await tester.pumpAndSettle();
      expect(find.text('Visão geral'), findsOneWidget);
      expect(
        fixture.requests
            .where((r) => r.url.path.endsWith('/auth/login'))
            .single
            .url
            .host,
        'school.example',
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'main navigation, ticket actions and expired session discard private routes',
    (tester) async {
      final fixture = Fixture();
      addTearDown(fixture.dispose);
      await tester.pumpWidget(fixture.app());
      await tester.pumpAndSettle();
      expect(find.text('Visão geral'), findsOneWidget);
      await tester.tap(find.text('Chamados').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Projetor sem imagem'));
      await tester.pumpAndSettle();
      expect(find.text('Chamado #42'), findsOneWidget);
      await tester.ensureVisible(find.text('Assumir chamado'));
      await tester.tap(find.text('Assumir chamado'));
      await tester.pumpAndSettle();
      expect(find.text('Finalizar chamado'), findsOneWidget);
      // Current web/API rule permits every authenticated technician to close.
      fixture.session.expire();
      await tester.pumpAndSettle();
      expect(find.text('Entrar'), findsOneWidget);
      expect(find.text('Chamado #42'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('notification tap waits for login then opens ticket detail', (
    tester,
  ) async {
    final fixture = Fixture(authenticated: false);
    addTearDown(fixture.dispose);
    fixture.push.openTicket('42');
    await tester.pumpWidget(fixture.app());
    await tester.pumpAndSettle();
    await fixture.session.login('http://school.example', 'tecnico', 'secret');
    await tester.pumpAndSettle();
    expect(find.text('Chamado #42'), findsOneWidget);
    expect(fixture.push.pendingTicket.value, isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('machine and more pages navigate to real server-backed screens', (
    tester,
  ) async {
    final fixture = Fixture();
    addTearDown(fixture.dispose);
    await tester.pumpWidget(fixture.app());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Máquinas').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('PC-01'));
    await tester.pumpAndSettle();
    expect(find.text('Detalhes da máquina'), findsOneWidget);
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mais').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Computadores online'));
    await tester.pumpAndSettle();
    expect(find.text('Nenhum heartbeat recebido até agora.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('scheduled notification cannot cross logout and a new login', (
    tester,
  ) async {
    final fixture = Fixture();
    addTearDown(fixture.dispose);
    await tester.pumpWidget(fixture.app());
    await tester.pumpAndSettle();
    fixture.push.openTicket('42');
    fixture.session.expire();
    await fixture.session.login('http://school.example', 'tecnico', 'secret');
    await tester.pumpAndSettle();
    expect(find.text('Chamado #42'), findsNothing);
    expect(find.text('Visão geral'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('dashboard fits narrow device with larger accessibility text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 720);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final fixture = Fixture();
    addTearDown(fixture.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(
            size: Size(320, 720),
            textScaler: TextScaler.linear(1.3),
          ),
          child: Scaffold(
            body: DashboardPage(
              api: fixture.api,
              realtime: fixture.realtime,
              onTicket: (_) {},
              onMachine: (_) {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
