# Aplicativo mobile do Sistema de Manutenção

## Objetivo e análise do sistema existente

O aplicativo Flutter é o terceiro cliente do sistema real de manutenção escolar. A equipe de TI pode consultar o inventário, acompanhar chamados e atender solicitações pelo celular. O mesmo projeto pode ser apresentado academicamente como integração entre cliente nativo, API REST, banco relacional, comunicação em tempo real e notificações push.

Antes da implementação foram examinados README, CLAUDE, modelos, CRUD, rotas HTML, templates, clientes JavaScript, autenticação, servidor TCP, heartbeat, WebSocket e Web Push. As decisões foram:

1. Manter FastAPI e SQLite como única fonte de dados e regras. Não alterar o protocolo dos computadores dos professores.
2. Manter páginas Jinja2, cookies, URLs web e Web Push. Acrescentar `/api/v1` e um WebSocket separado para o aplicativo.
3. Extrair regras de dashboard, vencimento de vistorias/checkups, segmentos, normalização de MAC e senhas para módulos compartilhados. Reutilizar o CRUD de máquinas, usuários e periféricos.
4. Compartilhar a atualização condicional de chamados entre HTML e API para preservar a exclusividade do atendimento.
5. Acrescentar somente duas tabelas e uma coluna, usando a estratégia existente `create_all` + migração SQLite aditiva e idempotente.
6. Separar FCM de Web Push. Implementar código e testes sem exigir credenciais Firebase reais.
7. Construir o cliente Flutter e validar API, compatibilidade web e cliente em ambientes isolados.

## Arquitetura

```text
Professor_auto.exe / TI Heartbeat.exe
             |
             | TCP :5050 (chamado / heartbeat)
             v
       Backend FastAPI :8000
             |
             +-- SQLite: inventário, usuários, chamados, sessões, dispositivos
             +-- Jinja2 + sessão/cookie: site existente
             +-- REST /api/v1 + Bearer: aplicativo Flutter
             +-- /ws/tickets: site com cookie
             +-- /ws/v1/tickets: Flutter com Bearer no handshake
             +-- Web Push / VAPID: navegador/PWA
             +-- Firebase Cloud Messaging: Android / iOS
```

O Flutter nunca conversa com os PCs nem abre o SQLite. REST carrega dados e executa ações; o WebSocket informa eventos para recarregar os dados. FCM entrega notificações quando o aplicativo não está aberto. Receber uma notificação não exige conexão do celular com a LAN, mas abrir o detalhe e operar o sistema exige acesso ao backend, pela rede local ou VPN.

O roteiro atual de push nativo está em [configuração Firebase](mobile_push_firebase.md), incluindo novos endpoints, diagnóstico do registro e teste no aparelho.

## Backend e contratos

Rotas existentes continuam com seu formato anterior. Novas listas REST retornam arrays JSON. Falhas usam `detail`, com HTTP 401 para sessão inválida, 403 para autorização, 404 para recurso ausente, 409 para conflito e 422 para entrada inválida. O contrato tipado também consta em `app/schemas/` e no OpenAPI gerado por FastAPI.

| Método | Rota | Finalidade |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | `{username, password}`, retorna Bearer, validade e usuário |
| GET | `/api/v1/auth/me` | Usuário autenticado |
| POST | `/api/v1/auth/logout` | Revoga sessão atual e remove seus dispositivos FCM |
| GET | `/api/v1/dashboard` | Indicadores, distribuições, máquinas e chamados recentes |
| GET | `/api/v1/tickets` | Filtro `status=OPEN`, `IN_PROGRESS`, `CLOSED` ou `ALL` |
| GET | `/api/v1/tickets/{id}` | Detalhe, diagnóstico do PC e nota de resolução |
| POST | `/api/v1/tickets/{id}/take` | Assume somente se ainda estiver `OPEN` |
| POST | `/api/v1/tickets/{id}/close` | Finaliza `IN_PROGRESS`; corpo opcional `{diagnosis}` |
| GET, POST | `/api/v1/machines` | Listar ou cadastrar máquinas |
| GET, PUT, DELETE | `/api/v1/machines/{id}` | Consultar, atualizar ou excluir máquina |
| GET | `/api/v1/rooms` | Salas e pior status entre suas máquinas |
| GET | `/api/v1/rooms/machines?room_name=...` | Máquinas de uma sala |
| PATCH | `/api/v1/rooms/status` | `{room_name, room_status}` atualiza todas as máquinas da sala |
| GET | `/api/v1/online` | Heartbeat, idade, máquina/sala e usuário logado |
| GET, POST | `/api/v1/users` | Listar/criar usuários; somente administrador |
| PUT, DELETE | `/api/v1/users/{id}` | Alterar/desativar usuário; somente administrador |
| POST | `/api/v1/devices` | Registrar `{token, platform: "android" ou "ios"}` |
| DELETE | `/api/v1/devices` | Corpo `{token}` remove registro da sessão atual |
| POST | `/api/v1/push/register` | Registrar `{fcm_token, platform, device_name?}`; contrato atual do Flutter |
| POST | `/api/v1/push/unregister` | Corpo `{fcm_token}` desativa token do usuário atual |
| GET | `/api/v1/push/status` | Configuração declarada e quantidade de dispositivos ativos do usuário |
| WS | `/ws/v1/tickets` | Header `Authorization: Bearer ...` |

As rotas `/devices` são mantidas para compatibilidade com a primeira versão mobile.

Máquinas aceitam filtros `q`, `profile`, `segment`, `room_status`, `inspected` e `checkup_done`. `PUT` preserva campos omitidos, incluindo periféricos e a senha remota preexistente. Periféricos seguem o catálogo dos perfis A/B/C de `app/constants.py`. Campos de autoria e datas são preenchidos pelo backend. Vistorias e checkups usam o mesmo vencimento de 7/2/1 dias conforme o status, no fuso de Brasília.

O indicador `open_tickets` mantém a definição do dashboard web: todos os chamados ainda não fechados, inclusive em atendimento. `in_progress_tickets` identifica o subconjunto em atendimento. O app deve distinguir essa definição de uma contagem somente de `OPEN`.

`DELETE /users/{id}` desativa a conta, preservando histórico. Não permite desativar a própria conta. Operadores autenticados mantêm as mesmas permissões do site para inventário, salas e atendimento; somente administradores gerenciam usuários. Como no site, qualquer operador autenticado pode finalizar um chamado em atendimento.

### Chamados concorrentes

`crud.take_ticket` executa `UPDATE tickets ... WHERE id = :id AND status = 'OPEN'`. A primeira transição vence; chamadas seguintes recebem 409. A decisão acontece no banco, inclusive quando web e mobile disputam o mesmo chamado. `close_ticket` também usa atualização condicional, e o broadcast só ocorre após commit. Não depende de lock em memória ou de uma verificação prévia de status.

### Autenticação e informações sensíveis

O hash PBKDF2-SHA256 existente foi preservado em `app/security.py`, utilizado pelo site e API. Login retorna um token aleatório de 48 bytes; o banco guarda apenas seu SHA-256. A sessão expira em 30 dias por padrão (`MOBILE_TOKEN_TTL_SECONDS`). Logout revoga somente a sessão atual. Desativar usuário ou alterar seu hash de senha invalida as sessões mobile, inclusive quando a alteração acontece no site.

API mobile exige Bearer e não aceita cookie como substituto. WebSocket nativo usa header no handshake, sem credenciais na URL. Revalida sessão antes de entregar eventos, a cada mensagem e após até 30 segundos de inatividade. O WebSocket web mantém autenticação por cookie.

Respostas usam DTOs com campos permitidos; hashes de senha e `hoptodesk_password` não são retornados, nem dentro de dashboard ou objetos relacionados. O aplicativo não altera nem mostra essa senha. A dívida técnica de armazenamento da senha HopToDesk no sistema web permanece fora do escopo.

O Flutter guarda o Bearer em `flutter_secure_storage`. O URL do servidor é configurável; nenhum IP escolar está fixado. HTTP permite uso na LAN existente, porém transporta senha e Bearer sem criptografia: para uso real com credenciais, configure HTTPS com certificado confiável no dispositivo ou use túnel/VPN confiável. Não há código que ignore erros de certificado. A permissão Android de tráfego HTTP existe para compatibilidade com o servidor LAN atual.

### Banco e migração

Novas tabelas:

- `mobile_sessions`: usuário, digest do Bearer, impressão do hash de senha, criação e expiração.
- `fcm_devices`: token de entrega FCM, digest único, plataforma, nome do aparelho, situação ativa, usuário, sessão, criação e atualização.

Nova coluna: `tickets.resolution_note`, nota opcional de finalização. O diagnóstico técnico original `diagnostics_json`, enviado pelo professor, permanece separado.

`Base.metadata.create_all` cria apenas tabelas ausentes. `_migrate_sqlite()` consulta `PRAGMA table_info` antes de adicionar a coluna. Dados existentes são preservados. Não há Alembic, banco duplicado nem migração destrutiva. Antes de atualizar um servidor em uso, faça o backup habitual de `data/` e pare o processo para atualizar o código e as dependências.

`MANUTENCAO_DATA_DIR` permite ambiente separado de desenvolvimento/testes. Sem essa variável, o caminho continua `data/app.db`. Banco, segredo de cookie e chaves VAPID seguem o mesmo diretório configurado.

## Execução do backend

Use Python 3.12, conforme orientação preexistente do projeto:

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -m app.main
```

Primeiro administrador é criado no site em `/setup`. Contas existentes já funcionam no mobile. O projeto não carrega `.env` automaticamente: `.env.example` é uma referência das variáveis que precisam estar no ambiente do processo.

Para um ambiente de desenvolvimento vazio e isolado:

```powershell
$env:MANUTENCAO_DATA_DIR = Join-Path $env:TEMP 'manutencao-mobile-dev'
py -3.12 -m app.main
```

Não aponte testes para o banco usado pela escola.

## Flutter

O projeto está em `mobile/`, com plataformas Android e iOS. As instruções específicas e organização do cliente estão em [mobile/README.md](../mobile/README.md). Execução:

```powershell
Set-Location mobile
flutter pub get
flutter run
```

Na tela de login, informe o endereço do FastAPI acessível pelo celular. Em emulador Android, `http://10.0.2.2:8000` normalmente representa o host do emulador; aparelho físico usa o endereço LAN do servidor. Essa é uma orientação de execução, não um IP embutido no aplicativo.

O cliente oferece login, dashboard, chamados por status, detalhe/atendimento, inventário com pesquisa/filtros, detalhe e formulário de máquina, salas, heartbeat, administração de usuários e configurações/logout. Navegação usa barra inferior e área Mais. `ChangeNotifier` gerencia sessão, cliente HTTP central trata falhas e armazenamento seguro persiste autenticação. O realtime nativo reconecta e as telas recarregam dados REST. Consulte o README do cliente para detalhes finais e testes.

## Firebase Cloud Messaging: configuração manual

FCM permanece desativado no backend sem credenciais ou ativação explícita. O inventário e atendimento funcionam sem Firebase. Não há chaves particulares no repositório.

1. Crie ou escolha um projeto no [Firebase Console](https://console.firebase.google.com/). Confirme a API Firebase Cloud Messaging HTTP v1 habilitada no projeto Google Cloud correspondente.
2. Registre um aplicativo Android com o `applicationId` real de `mobile/android/app/build.gradle.kts` (o projeto inicial usa `br.com.manutencao.manutencao_mobile`). Não reutilize um JSON de outro pacote/projeto.
3. Instale as ferramentas Firebase CLI e FlutterFire CLI conforme a [configuração oficial FlutterFire](https://firebase.google.com/docs/flutter/setup). Autentique com `firebase login`. Dentro de `mobile/`, execute `flutterfire configure`, selecione o projeto e Android, e selecione iOS se for distribuí-lo. O cliente deve usar os arquivos reais gerados; nenhum placeholder de credencial é suficiente para receber push.
4. Mantenha `google-services.json`, `GoogleService-Info.plist`, `firebase_options.dart` e quaisquer chaves privadas fora do Git. Esses caminhos estão ignorados. Siga também o README mobile para o mecanismo de inicialização adotado.
5. No Firebase Console, Configurações do projeto > Contas de serviço > Firebase Admin SDK, gere uma chave privada para o servidor. Salve o JSON em uma pasta protegida fora do repositório. Ele nunca pertence ao APK, ao Flutter nem ao pacote distribuído aos professores.
6. Configure o processo FastAPI e reinicie:

```powershell
$env:FCM_ENABLED = 'true'
$env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\secrets\firebase-service-account.json'
$env:FIREBASE_PROJECT_ID = 'seu-projeto-firebase'
py -3.12 -m app.main
```

7. O servidor precisa de saída HTTPS para os serviços Google. O celular precisa de internet para FCM e de acesso ao FastAPI para registrar seu token e buscar detalhes.
8. Instale o app em Android com Google Play Services, abra ao menos uma vez, faça login e conceda permissão de notificações (inclusive Android 13+). O token FCM é registrado com Bearer e vinculado à sessão. Renovações são registradas novamente. Logout remove o vínculo no servidor.
9. Crie um chamado usando o cliente real de professor. Verifique aviso com app aberto, em background e com tela bloqueada. Toque na notificação e confirme abertura do chamado correto. Faça também teste iniciando o app pelo toque quando não estava em execução.
10. Para iOS, configure assinatura no Xcode/macOS, capability Push Notifications, Background Modes/Remote notifications e chave APNs no Firebase. Essa validação depende de ambiente Apple e aparelho provisionado.

Comandos de referência para a etapa 3, com Node.js e Flutter/Dart disponíveis no PATH:

```powershell
npm install -g firebase-tools
dart pub global activate flutterfire_cli
firebase login
Set-Location mobile
dart pub global run flutterfire_cli:flutterfire configure --project=seu-projeto-firebase --platforms=android
flutter pub get
flutter run
```

Confirme que `mobile/android/app/google-services.json` foi gerado e corresponde ao pacote. O Gradle aplica o plugin Google Services quando esse arquivo existe; sem ele, o build continua permitindo testar as funções REST. O cliente inicializa Firebase pelas configurações nativas; `firebase_options.dart` gerado pelo FlutterFire não substitui o arquivo nativo nesse fluxo. No iOS, adicione `GoogleService-Info.plist` ao target Runner no Xcode.

O backend envia mensagem com `notification` + `data.type=new_ticket` e `data.ticket_id`, prioridade Android alta e canal `maintenance_tickets`. O sistema operacional pode exibir a notificação com o app fechado; o clique permite buscar o chamado autenticado. Flutter trata aviso em primeiro plano, abertura em background e abertura inicial. `UnregisteredError` desativa tokens rejeitados; erros transitórios mantêm dispositivos válidos. O parser aceita também `ticket_created` legado. O orçamento da mensagem considera escapes JSON para respeitar o limite de tamanho.

FCM depende de configuração, permissões, conectividade e políticas do sistema operacional. Forçar parada do app nas configurações do Android impede recebimento até reabri-lo; no iOS, dispensar o app também afeta mensagens em background. Veja [recebimento oficial no Flutter](https://firebase.google.com/docs/cloud-messaging/flutter/receive-messages). Não confundir essas restrições com simplesmente minimizar o aplicativo.

No MVP, envio FCM ocorre em thread após commit, como o Web Push existente. Não há fila persistente/reentrega após queda do processo. Uma falha de Firebase não desfaz o chamado nem impede WebSocket/Web Push. Somente novos chamados geram FCM, para evitar avisos excessivos.

## Testes e verificação

```powershell
py -3.12 -m pip install -r requirements-dev.txt
$testTemp = Join-Path $env:TEMP ('manutencao-tests-' + [guid]::NewGuid().ToString('N'))
py -3.12 -m pytest tests -q --basetemp $testTemp
Set-Location mobile
flutter analyze
flutter test
flutter build apk --debug
```

A suíte Python isola `MANUTENCAO_DATA_DIR` antes de importar `app.main` e usa SQLite temporário, sem iniciar o listener TCP de produção. Um teste adicional de startup usa subprocesso e TCP/UDP reais em portas efêmeras de loopback. Valida autenticação, permissões, recursos, disputa concorrente com duas conexões SQLite, compatibilidade HTML/cookies, realtime e FCM com mocks. Testes externos não exigem Firebase real. O `--basetemp` único evita conflito de permissões com diretórios temporários antigos do pytest no Windows.

Os resultados executados e limitações desta entrega estão em [relatório de implementação](mobile-implementation-report.md). Testes automatizados e análise estática não comprovam entrega FCM em um aparelho real. A configuração e o roteiro manual acima continuam necessários.

## Arquivos principais

- `app/api/v1/`: API, autenticação, dependências e WebSocket mobile.
- `app/schemas/`: entradas validadas e respostas com campos permitidos.
- `app/services/maintenance.py`: regras extraídas e compartilhadas com HTML.
- `app/security.py`: mesmo hash de senha existente.
- `app/fcm.py`: entrega nativa independente de Web Push.
- `app/models.py`, `app/main.py`: novas tabelas e migração aditiva.
- `app/crud.py`: atendimento atômico compartilhado e CRUD existente.
- `mobile/`: cliente Flutter/Dart Android/iOS.
- `tests/`: integração API e compatibilidade do sistema.
