# Publicação da implementação mobile no GitHub

Verificação de 24/10/2026. O objetivo desta etapa é publicar o estado funcional existente para revisão, sem refatorar funcionalidades e sem fazer merge na `main`.

## Git

- Repositório: [SirManoTreta/manutencao](https://github.com/SirManoTreta/manutencao), mantido **privado**.
- Branch: **`codex/mobile-flutter`**.
- [Abrir branch no GitHub](https://github.com/SirManoTreta/manutencao/tree/codex/mobile-flutter).
- Código existente validado nesta rodada: `945c2aa`.
- A etapa de publicação acrescenta somente os três prompts de requisitos e este relatório. Nenhuma funcionalidade foi alterada para obter aprovação nos testes.
- O SHA final, incluindo esse commit de documentação, consta na mensagem de entrega e em `git log -1`. A sincronização é conferida por `git status`, upstream e SHA da referência remota após o push.

Commits existentes enviados com a branch, em ordem de implementação:

| SHA | Mensagem |
| --- | --- |
| `2940ac7` | `feat(api): add authenticated mobile endpoints` |
| `0aa2133` | `feat(push): deliver ticket alerts through FCM` |
| `ee9901e` | `test: cover mobile API and web compatibility` |
| `8509059` | `feat(mobile): add Flutter maintenance client` |
| `9b426ce` | `chore(build): ignore Kotlin compiler state` |
| `3816c14` | `fix(build): support Pub Cache on another drive` |
| `9455d4c` | `fix(auth): keep mobile tokens bound to server` |
| `763c9ad` | `docs: document mobile setup and validation` |
| `9533648` | `feat(push): complete native FCM infrastructure` |
| `462ea0d` | `test(push): cover registration and payload limits` |
| `81b2f5e` | `feat(mobile): finish native push lifecycle` |
| `9ec905a` | `docs: add Firebase setup and device test guide` |
| `945c2aa` | `fix(startup): load local Firebase settings` |

O push usa o transporte Git normal, sem `--force`. Histórico e branch funcional são preservados; `main` não recebe merge nesta tarefa.

## Flutter

Páginas e fluxos implementados:

- Login, URL de servidor configurável, perfil/configurações e logout.
- Dashboard com indicadores, distribuições e registros recentes.
- Chamados por status, detalhe, assumir e finalizar com nota de resolução.
- Inventário com pesquisa/filtros, detalhe, cadastro/edição, periféricos e exclusão confirmada.
- Salas, máquinas da sala e atualização de status.
- Computadores online com heartbeat e usuário/tela de login.
- Usuários para administradores.
- Vistorias e checkups pendentes por filtros do inventário.

Cliente HTTP centralizado, Bearer em armazenamento seguro, tratamento de erro/reconexão e navegação Material 3 em português. Os dados operacionais permanecem no mesmo backend/SQLite do site.

FCM foi conferido no código: bootstrap nativo FlutterFire, registro autenticado com nome do aparelho, refresh, unregister/logout, foreground com deduplicação, handler de background, `getInitialMessage`, `onMessageOpenedApp`, callback local e navegação ao chamado por ID. Tipos/IDs inválidos são rejeitados e destinos pendentes têm proteção de sessão/origem.

O usuário informou funcionamento do mobile e das notificações no ambiente local. Nesta rodada de publicação foram executados testes automatizados com transporte Firebase simulado; não foi enviado um novo push nem repetida validação em aparelho físico. A configuração real da instalação permanece fora do Git.

## Backend

FastAPI continua atendendo o site Jinja2 por cookie e o Flutter por `/api/v1` com Bearer revogável. O hash PBKDF2 existente é compartilhado; sessões verificam expiração, usuário ativo e alteração de senha. Administração de usuários exige administrador.

Grupos de endpoints adicionados:

- `/api/v1/auth/login`, `/auth/me`, `/auth/logout`.
- `/api/v1/dashboard`.
- `/api/v1/tickets` e detalhe, assumir e finalizar.
- `/api/v1/machines` e detalhe/CRUD.
- `/api/v1/rooms`, `/rooms/machines`, `/rooms/status`.
- `/api/v1/online`.
- `/api/v1/users` e administração autorizada.
- `/api/v1/push/register`, `/push/unregister`, `/push/status`.
- `/api/v1/devices` mantido para compatibilidade com a primeira versão mobile.

`/ws/v1/tickets` autentica o cliente nativo e compartilha os eventos com `/ws/tickets`, preservado para o site. Atendimento usa UPDATE condicional para impedir dois operadores de assumirem o mesmo chamado.

`app/services/mobile_devices.py` registra/atualiza dispositivos por token único e usuário autenticado. `app/fcm.py` envia somente para registros/sessões válidos, limita JSON, trata rejeições e não registra segredos. A criação pelo Professor_auto confirma o commit antes de tentar WebSocket, Web Push e FCM; falha de qualquer transporte não desfaz o chamado nem bloqueia os demais. Não foi criado outro backend ou banco.

## Segurança e arquivos locais

Auditoria anterior ao staging verificou os 187 arquivos rastreados, os 13 commits locais existentes, 215 blobs históricos únicos e os três prompts novos. Incluiu comparação sanitizada com segredos locais, sem imprimir seus valores, e análise dos arquivos staged antes do commit.

**Nenhuma service account Firebase, chave privada, senha/token real, `.env` ou banco SQLite de produção é incluído na publicação.** Senhas/tokens fictícios das fixtures são dados de testes; nomes de campos e funções de autenticação são código, não credenciais.

Permanecem ignorados/localmente necessários:

- `secrets/`, service accounts `firebase-service-account*.json`, `service-account*.json`, `*firebase-adminsdk*.json`.
- `run.local.bat`: caminho da credencial e configuração apenas desta instalação.
- `mobile/android/app/google-services.json` e `mobile/lib/firebase_options.dart`.
- `mobile/ios/Runner/GoogleService-Info.plist`, quando iOS for configurado.
- `.env`, `.env.*` privados, `*.pem`, `*.key`, `*.p8` e arquivos de assinatura.
- `data/`: banco, backups, chaves de sessão/VAPID, logs e validações locais.
- APKs, AABs, executáveis gerados, caches Flutter/Dart/Gradle/Kotlin e diretórios de build.

`.env.example` é versionado deliberadamente e contém somente configuração de exemplo, sem valores privados. O JSON público do app Android foi mantido fora do Git conforme política já adotada; ele não foi confundido com a service account administrativa. Quem clonar precisa configurar seu ambiente seguindo [guia Firebase](mobile_push_firebase.md).

Um commit antigo contém somente o nome de um marcador Kotlin `.salive` **vazio, de 0 bytes**, removido no commit seguinte e ausente do estado atual. Não contém cache de compilação ou segredo. O histórico foi preservado, sem reescrita desnecessária. Nenhum conteúdo de banco, build ou credencial foi encontrado nos blobs a enviar.

## Testes desta publicação

Backend, Python 3.12:

```powershell
$env:FCM_ENABLED = 'false'
$testTemp = Join-Path $env:TEMP ('manutencao-publish-pytest-' + [guid]::NewGuid().ToString('N'))
py -3.12 -m pytest tests -q --basetemp $testTemp -W ignore::DeprecationWarning
```

**107 testes aprovados, 32,40 s.** Banco temporário isolado, sem usar o SQLite de produção. A integração de startup usa subprocesso com portas efêmeras somente em localhost e FCM desativado. Cobertura inclui autenticação/administração, CRUD, migrações legadas, concorrência com duas conexões SQLite, WebSocket, registro FCM, payloads/limites e isolamento de falhas após commit.

Flutter 3.44.8 / Dart 3.12.2:

```powershell
Set-Location mobile
flutter pub get
flutter analyze
flutter test
```

`pub get` aprovado e `pubspec.lock` preservado; `analyze` sem problemas; **66 testes aprovados** (29 core, 30 push e 7 widgets). Total desta rodada: **173 testes aprovados**. Nenhuma outra suíte ou workflow CI está configurado no repositório nesta etapa.

Nenhum teste enviou push real. Entrega Google/APNs, estado físico do aparelho e permissões do sistema não foram revalidados nesta publicação. Não se declara uma nova validação de entrega somente porque os testes passaram.

O APK local continua disponível para a instalação configurada, mas não é anexado ao Git ou publicado como Release nesta tarefa. Instruções para reproduzir build/configuração estão em [mobile/README.md](../mobile/README.md) e [guia FCM](mobile_push_firebase.md).
