import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:manutencao_mobile/core/api_client.dart';
import 'package:manutencao_mobile/core/session.dart';
import 'package:manutencao_mobile/models/models.dart';

const _user = AppUser(id: 7, username: 'tecnico', isAdmin: true);

http.Response _json(Object? value, [int status = 200]) => http.Response(
  jsonEncode(value),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

class MemorySessionStorage implements SessionStorage {
  MemorySessionStorage([Map<String, String>? initial]) : values = {...?initial};

  final Map<String, String> values;

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;

  @override
  Future<void> delete(String key) async => values.remove(key);
}

class StreamClient extends http.BaseClient {
  StreamClient(this.handler);

  final Future<http.StreamedResponse> Function(http.BaseRequest) handler;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      handler(request);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Autenticação e sessão', () {
    test('login envia senha intacta, guarda token e publica usuário', () async {
      late http.Request loginRequest;
      final api = ApiClient(
        client: MockClient((request) async {
          loginRequest = request;
          return _json({'access_token': 'token-novo', 'user': _user.toJson()});
        }),
      );
      final storage = MemorySessionStorage();
      final session = SessionController(api, storage);
      addTearDown(api.dispose);
      addTearDown(session.dispose);
      final states = <bool>[];
      session.addListener(() => states.add(session.busy));

      expect(
        await session.login(
          ' https://escola.example/ ',
          ' tecnico ',
          ' senha com espaços ',
        ),
        isTrue,
      );
      expect(
        loginRequest.url.toString(),
        'https://escola.example/api/v1/auth/login',
      );
      expect(loginRequest.headers['Authorization'], isNull);
      expect(jsonDecode(loginRequest.body), {
        'username': 'tecnico',
        'password': ' senha com espaços ',
      });
      expect(storage.values['server'], 'https://escola.example');
      expect(storage.values['token'], 'token-novo');
      expect(jsonDecode(storage.values['user']!)['id'], 7);
      expect(storage.values.containsKey('password'), isFalse);
      expect(session.authenticated, isTrue);
      expect(session.user!.isAdmin, isTrue);
      expect(session.generation, 1);
      expect(session.error, isNull);
      expect(states, [true, false]);
    });

    test('senha errada termina loading e preserva estado sem login', () async {
      final api = ApiClient(
        client: MockClient(
          (_) async => _json({'detail': 'Usuário ou senha inválidos.'}, 401),
        ),
      );
      final storage = MemorySessionStorage();
      final session = SessionController(api, storage);
      addTearDown(api.dispose);
      addTearDown(session.dispose);

      expect(
        await session.login('http://servidor.local:8000', 'tecnico', 'errada'),
        isFalse,
      );
      expect(session.authenticated, isFalse);
      expect(session.busy, isFalse);
      expect(session.error, 'Usuário ou senha inválidos.');
      expect(api.token, isNull);
      expect(storage.values['token'], isNull);
      expect(storage.values['user'], isNull);
    });

    test('401 protegido limpa sessão e armazenamento seguro mock', () async {
      FlutterSecureStorage.setMockInitialValues({
        'server': 'https://escola.example',
        'token': 'token-expirado',
        'user': jsonEncode(_user.toJson()),
      });
      final storage = SecureSessionStorage();
      final api =
          ApiClient(
              client: MockClient(
                (_) async => _json({'detail': 'Sessão expirada.'}, 401),
              ),
            )
            ..baseUrl = 'https://escola.example'
            ..token = await storage.read('token');
      final session = SessionController(api, storage)..user = _user;
      addTearDown(api.dispose);
      addTearDown(session.dispose);

      await expectLater(
        api.request('GET', '/dashboard'),
        throwsA(
          isA<ApiException>().having((error) => error.status, 'status', 401),
        ),
      );
      // expire deliberately invalidates in-memory auth before async key deletion.
      await Future<void>.delayed(Duration.zero);
      expect(session.authenticated, isFalse);
      expect(api.token, isNull);
      expect(await storage.read('token'), isNull);
      expect(await storage.read('user'), isNull);
      expect(await storage.read('server'), 'https://escola.example');
      expect(session.notice, contains('Sessão expirada'));
    });

    test(
      'restauração valida sessão remota e atualiza perfil em cache',
      () async {
        final storage = MemorySessionStorage({
          'server': 'https://escola.example',
          'token': 'token-salvo',
          'user': jsonEncode(
            const AppUser(id: 7, username: 'tecnico').toJson(),
          ),
        });
        final api = ApiClient(
          client: MockClient((request) async {
            expect(request.url.path, '/api/v1/auth/me');
            expect(request.headers['Authorization'], 'Bearer token-salvo');
            return _json(_user.toJson());
          }),
        );
        final session = SessionController(api, storage);
        addTearDown(api.dispose);
        addTearDown(session.dispose);

        await session.restore();
        expect(session.authenticated, isTrue);
        expect(session.user!.isAdmin, isTrue);
        expect(jsonDecode(storage.values['user']!)['is_admin'], isTrue);
        expect(session.notice, isNull);
      },
    );

    test(
      'restauração offline mantém cache e permite reconexão posterior',
      () async {
        final storage = MemorySessionStorage({
          'server': 'https://escola.example',
          'token': 'token-salvo',
          'user': jsonEncode(_user.toJson()),
        });
        final api = ApiClient(
          client: MockClient(
            (_) async => throw const SocketException('offline'),
          ),
        );
        final session = SessionController(api, storage);
        addTearDown(api.dispose);
        addTearDown(session.dispose);

        await session.restore();
        expect(session.authenticated, isTrue);
        expect(session.user!.username, 'tecnico');
        expect(api.token, 'token-salvo');
        expect(storage.values['token'], 'token-salvo');
        expect(session.notice, contains('Sem conexão'));
      },
    );

    test('restauração 401 remove credencial revogada no servidor', () async {
      final storage = MemorySessionStorage({
        'server': 'https://escola.example',
        'token': 'token-revogado',
        'user': jsonEncode(_user.toJson()),
      });
      final api = ApiClient(
        client: MockClient(
          (_) async => _json({'detail': 'Sessão inválida.'}, 401),
        ),
      );
      final session = SessionController(api, storage);
      addTearDown(api.dispose);
      addTearDown(session.dispose);

      await session.restore();
      expect(session.authenticated, isFalse);
      expect(session.user, isNull);
      expect(api.token, isNull);
      expect(storage.values['token'], isNull);
      expect(storage.values['user'], isNull);
    });

    test('restauração sem credencial não consulta servidor', () async {
      final api = ApiClient(
        client: MockClient(
          (_) async => fail('Não deve haver HTTP sem token salvo.'),
        ),
      );
      final session = SessionController(api, MemorySessionStorage());
      addTearDown(api.dispose);
      addTearDown(session.dispose);

      await session.restore();
      expect(session.authenticated, isFalse);
      expect(session.error, isNull);
    });

    test('cache corrompido retorna login sem lançar erro de parsing', () async {
      final api = ApiClient(
        client: MockClient(
          (_) async => fail('Cache inválido deve interromper restore.'),
        ),
      );
      final session = SessionController(
        api,
        MemorySessionStorage({
          'server': 'https://escola.example',
          'token': 'token-salvo',
          'user': '{json inválido',
        }),
      );
      addTearDown(api.dispose);
      addTearDown(session.dispose);

      await session.restore();
      expect(session.authenticated, isFalse);
      expect(api.token, isNull);
      expect(session.error, contains('restaurar'));
    });

    test(
      'cache corrompido e login falho não enviam token antigo a nova origem',
      () async {
        final storage = MemorySessionStorage({
          'server': 'https://escola-original.example',
          'token': 'token-da-escola-original',
          'user': '{json inválido',
        });
        final requests = <http.Request>[];
        final api = ApiClient(
          client: MockClient((request) async {
            requests.add(request);
            expect(request.url.host, 'outro-servidor.example');
            expect(request.url.path, '/api/v1/auth/login');
            expect(request.headers['Authorization'], isNull);
            return _json({'detail': 'Usuário ou senha inválidos.'}, 401);
          }),
        );
        final session = SessionController(api, storage);
        addTearDown(api.dispose);
        addTearDown(session.dispose);

        await session.restore();
        expect(storage.values['token'], isNull);
        expect(storage.values['user'], isNull);
        expect(
          await session.login(
            'https://outro-servidor.example',
            'tecnico',
            'errada',
          ),
          isFalse,
        );
        expect(storage.values['server'], 'https://escola-original.example');
        final restarted = SessionController(api, storage);
        addTearDown(restarted.dispose);
        await restarted.restore();
        expect(restarted.authenticated, isFalse);
        expect(requests, hasLength(1));
      },
    );

    test('401 atrasado não invalida token de login mais recente', () async {
      final pending = Completer<http.Response>();
      final started = Completer<void>();
      final api =
          ApiClient(
              client: MockClient((request) async {
                expect(request.headers['Authorization'], 'Bearer token-antigo');
                started.complete();
                return pending.future;
              }),
            )
            ..baseUrl = 'https://escola.example'
            ..token = 'token-antigo';
      final session = SessionController(api, MemorySessionStorage())
        ..user = _user;
      addTearDown(api.dispose);
      addTearDown(session.dispose);
      final assertion = expectLater(
        api.request('GET', '/dashboard'),
        throwsA(
          isA<ApiException>().having((error) => error.status, 'status', 401),
        ),
      );
      await started.future;
      api.token = 'token-novo';
      pending.complete(_json({'detail': 'Token antigo expirou.'}, 401));

      await assertion;
      expect(session.authenticated, isTrue);
      expect(api.token, 'token-novo');
      expect(session.notice, isNull);
    });

    test('logout offline sempre limpa credencial local', () async {
      final storage = MemorySessionStorage({
        'server': 'https://escola.example',
        'token': 'token-salvo',
        'user': jsonEncode(_user.toJson()),
      });
      final api =
          ApiClient(
              client: MockClient((request) async {
                expect(request.method, 'POST');
                expect(request.url.path, '/api/v1/auth/logout');
                throw const SocketException('offline');
              }),
            )
            ..baseUrl = 'https://escola.example'
            ..token = 'token-salvo';
      final session = SessionController(api, storage)..user = _user;
      addTearDown(api.dispose);
      addTearDown(session.dispose);

      await session.logout();
      expect(session.authenticated, isFalse);
      expect(storage.values['token'], isNull);
      expect(storage.values['user'], isNull);
      expect(storage.values['server'], 'https://escola.example');
      expect(session.notice, contains('Servidor indisponível'));
    });
  });

  group('Transporte HTTP', () {
    for (final value in [
      'servidor.local:8000',
      'ftp://escola.example',
      'https://usuario:senha@escola.example',
      'https://escola.example/api/v1',
      'https://escola.example?token=segredo',
      'https://escola.example#chamados',
    ]) {
      test('configuração rejeita URL inválida: $value', () {
        expect(
          () => ApiClient.normalizeBaseUrl(value),
          throwsA(isA<ApiException>()),
        );
      });
    }

    test('timeout cobre conexão cujo send nunca termina', () async {
      final pending = Completer<http.StreamedResponse>();
      final api = ApiClient(
        client: StreamClient((_) => pending.future),
        timeout: const Duration(milliseconds: 15),
      )..baseUrl = 'http://servidor.local';
      addTearDown(api.dispose);

      await expectLater(
        api.request('GET', '/dashboard'),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('demorou'),
          ),
        ),
      );
    });

    test('timeout também cobre corpo HTTP que nunca termina', () async {
      final body = StreamController<List<int>>();
      final api = ApiClient(
        client: StreamClient(
          (_) async => http.StreamedResponse(body.stream, 200),
        ),
        timeout: const Duration(milliseconds: 15),
      )..baseUrl = 'http://servidor.local';
      addTearDown(api.dispose);

      await expectLater(
        api.request('GET', '/dashboard'),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('demorou'),
          ),
        ),
      );
      await body.close();
    });

    test('certificado inválido apresenta erro compreensível', () async {
      final api = ApiClient(
        client: MockClient(
          (_) async =>
              throw const HandshakeException('CERTIFICATE_VERIFY_FAILED'),
        ),
      )..baseUrl = 'https://escola.example';
      addTearDown(api.dispose);

      await expectLater(
        api.request('GET', '/dashboard'),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('Certificado HTTPS'),
          ),
        ),
      );
    });

    test('HTML de servidor incorreto não passa como JSON da API', () async {
      final api = ApiClient(
        client: MockClient(
          (_) async => http.Response('<html>Login</html>', 200),
        ),
      )..baseUrl = 'https://escola.example';
      addTearDown(api.dispose);

      await expectLater(
        api.request('GET', '/dashboard'),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('Resposta inválida'),
          ),
        ),
      );
    });

    test('erro 422 exibe validação devolvida pelo backend', () async {
      final api = ApiClient(
        client: MockClient(
          (_) async => _json({
            'detail': [
              {
                'loc': ['body', 'profile'],
                'msg': 'Input should be A, B or C',
              },
            ],
          }, 422),
        ),
      )..baseUrl = 'https://escola.example';
      addTearDown(api.dispose);

      await expectLater(
        api.request('POST', '/machines', body: {'profile': 'Z'}),
        throwsA(
          isA<ApiException>()
              .having((error) => error.status, 'status', 422)
              .having((error) => error.message, 'message', contains('profile')),
        ),
      );
    });

    test('DELETE sem corpo de resposta aceita 204', () async {
      final api = ApiClient(
        client: MockClient((_) async => http.Response('', 204)),
      )..baseUrl = 'https://escola.example';
      addTearDown(api.dispose);

      expect(await api.request('DELETE', '/machines/7'), isNull);
    });

    test(
      'lista envia filtros escapados e aceita array da API versionada',
      () async {
        final api = ApiClient(
          client: MockClient((request) async {
            expect(request.url.queryParameters, {
              'q': '7º Ano A',
              'profile': 'B',
            });
            return _json([
              {'id': 1, 'machine_name': 'PC-SALA07'},
            ]);
          }),
        )..baseUrl = 'https://escola.example';
        addTearDown(api.dispose);

        final values = await api.list(
          '/machines',
          query: {'q': '7º Ano A', 'profile': 'B'},
        );
        expect(values.single['machine_name'], 'PC-SALA07');
      },
    );
  });

  group('Modelos reais do backend', () {
    test('chamado mantém UTC, diagnóstico e sala do relacionamento', () {
      final ticket = Ticket.fromJson({
        'id': 17,
        'pc_name': 'PC-SALA07',
        'problem': 'Projetor sem imagem',
        'status': 'CLOSED',
        'machine': {'id': 2, 'room_name': '7º Ano A'},
        'reported_user': 'professor.joao',
        'assigned_by': 'tecnico',
        'closed_by': 'tecnico',
        'created_at': '2026-10-23T18:25:00+00:00',
        'assigned_at': '2026-10-23T18:26:00Z',
        'closed_at': '2026-10-23T15:30:00-03:00',
        'resolution_note': 'Cabo substituído',
        'diagnostics_json': '{"rede":"ok"}',
      });
      expect(ticket.id, 17);
      expect(ticket.room, '7º Ano A');
      expect(ticket.createdAt!.isUtc, isTrue);
      expect(ticket.createdAt, DateTime.utc(2026, 10, 23, 18, 25));
      expect(ticket.closedAt, DateTime.utc(2026, 10, 23, 18, 30));
      expect(ticket.assignedBy, 'tecnico');
      expect(ticket.diagnosis, 'Cabo substituído');
      expect(ticket.diagnostics, '{"rede":"ok"}');
    });

    test('chamado sem máquina e datas tolera campos opcionais ausentes', () {
      final ticket = Ticket.fromJson({
        'id': '8',
        'pc_name': 'PC-NOVO',
        'problem': 'Sem rede',
      });
      expect(ticket.id, 8);
      expect(ticket.room, 'Não cadastrada');
      expect(ticket.status, 'OPEN');
      expect(ticket.createdAt, isNull);
      expect(ticket.assignedAt, isNull);
      expect(ticket.closedAt, isNull);
      expect(ticket.diagnosis, isNull);
    });

    test('máquina preserva periféricos com quantidade e hardware', () {
      final machine = Machine.fromJson({
        'id': 3,
        'machine_name': 'PC-SALA02',
        'room_name': '2º Ano A',
        'profile': 'A',
        'room_status': 'ATTENTION',
        'ram_gb': 16,
        'peripherals': [
          {
            'peripheral_code': 'MOUSE',
            'present': true,
            'tested_working': true,
            'quantity': 0,
          },
          {
            'peripheral_code': 'CABO_RCA',
            'present': true,
            'tested_working': false,
            'quantity': 2,
          },
        ],
      });
      expect(machine.id, 3);
      expect(machine.status, 'ATTENTION');
      expect(machine.data['ram_gb'], 16);
      expect(machine.peripherals, hasLength(2));
      expect(machine.peripherals.last['quantity'], 2);
      expect(machine.peripherals.last['tested_working'], isFalse);
      expect(
        () => machine.data['machine_name'] = 'alterado',
        throwsUnsupportedError,
      );
      expect(Machine.fromJson({'id': 4}).peripherals, isEmpty);
    });

    test('heartbeat diferencia usuário logado de tela de login', () {
      final online = OnlineComputer.fromJson({
        'pc_name': 'PC-SALA07',
        'is_online': true,
        'age_seconds': 3,
        'login_active': true,
        'last_user': 'professor.joao',
        'machine': {'room_name': '7º Ano A'},
      });
      final loginScreen = OnlineComputer.fromJson({
        'pc_name': 'PC-SALA08',
        'is_online': true,
        'age_seconds': 1,
        'login_active': false,
        'last_user': null,
      });
      expect(online.online, isTrue);
      expect(online.loginActive, isTrue);
      expect(online.age, 3);
      expect(online.room, '7º Ano A');
      expect(loginScreen.online, isTrue);
      expect(loginScreen.loginActive, isFalse);
      expect(loginScreen.user, isNull);
    });

    test('usuário e sala preservam permissões e estado', () {
      final user = AppUser.fromJson({
        'id': 5,
        'username': 'operador',
        'is_admin': false,
        'is_active': false,
      });
      final room = Room.fromJson({
        'room_name': 'Secretaria',
        'room_status': 'URGENT',
        'machine_count': 4,
      });
      expect(user.isAdmin, isFalse);
      expect(user.isActive, isFalse);
      expect(AppUser.fromJson(user.toJson()).id, 5);
      expect(room.name, 'Secretaria');
      expect(room.status, 'URGENT');
      expect(room.machineCount, 4);
    });
  });
}
