# Relatório de implementação mobile

Etapa inicial desenvolvida em 23/10/2026, no repositório existente. A entrega acrescenta um cliente Flutter real e uma API; não troca a aplicação usada pela escola. Arquitetura e configuração completa estão em [mobile.md](mobile.md).

## Arquitetura entregue

`Professor_auto` e heartbeat continuam enviando o protocolo TCP existente ao FastAPI. O FastAPI grava no mesmo SQLite, atende o site Jinja2 por sessão/cookie e o Flutter por REST/Bearer. Um único gerenciador publica eventos para os WebSockets web e mobile. Novos chamados também acionam Web Push e FCM de forma independente, após commit.

## Backend

- API modular em `app/api/v1/`: autenticação, dashboard, chamados, máquinas, salas, online e usuários. [Tabela completa de rotas](mobile.md#backend-e-contratos).
- Schemas em `app/schemas/`: autenticação/dispositivo, dashboard, máquina/periférico, sala, chamado, usuário e heartbeat. Saídas explícitas não incluem hashes ou senha HopToDesk.
- Bearer aleatório revogável, digest SHA-256 no banco, expiração configurável e invalidação por desativação ou troca de senha. Login reaproveita PBKDF2 existente. Cookie web preservado.
- Regras extraídas em `app/services/maintenance.py` e `app/security.py`, reutilizadas pelo site e API. Os sete corpos de funções de manutenção foram comparados com a versão anterior durante a revisão.
- Migração aditiva: tabelas `mobile_sessions` e `fcm_devices`; coluna opcional `tickets.resolution_note`. Dados legados preservados e migração idempotente testada.
- Atendimento compartilhado via UPDATE condicional; conflitos retornam 409. Fechamento também condicional. Broadcast somente após commit.
- `/ws/v1/tickets` usa Bearer no header, revalidado antes dos eventos e durante conexão. `/ws/tickets` mantém cookie.
- Registro/remoção de dispositivos FCM por sessão. Envio com sala, PC, problema e ID do chamado; poda de tokens não registrados. Falhas de Firebase não desfazem chamados.

## Flutter

Cliente em `mobile/`, com projetos nativos Android e iOS, UI em português e Material 3. Telas implementadas:

1. Login com servidor configurável, senha oculta e tratamento de erro.
2. Dashboard com indicadores, distribuições e atalhos para registros recentes.
3. Chamados separados em abertos, em atendimento e finalizados.
4. Detalhe de chamado com diagnóstico, responsável, datas e ações assumir/finalizar.
5. Inventário com pesquisa e filtros por perfil, segmento, status, vistoria e checkup.
6. Detalhe da máquina, incluindo hardware, software, periféricos, auditoria e ID remoto.
7. Cadastro/edição de máquina com campos reais, periféricos, datas e confirmação de exclusão.
8. Salas e detalhe com máquinas/status consolidado e alteração de status.
9. Computadores online com heartbeat, usuário e tela de login.
10. Administração de usuários, disponível ao administrador.
11. Vistorias/checkups pendentes como consultas filtradas do inventário.
12. Perfil, servidor, situação de notificações e logout.

Navegação inferior: Início, Chamados, Máquinas, Salas e Mais. `ChangeNotifier` gerencia a sessão; `FutureBuilder` e componente compartilhado tratam carregamento, erro e atualização. Cliente HTTP central usa Bearer, timeout total e mensagens de conexão/TLS. Token e configuração são persistidos com `flutter_secure_storage`.

WebSocket reconecta com espera progressiva, autenticação no header e recarga REST dos chamados/dashboard. Logout remove rotas privadas. FCM usa notificações locais em primeiro plano, handler em background e tratamento de abertura inicial/background. O ID da notificação abre o detalhe interno após autenticação. Cadastro de token é serializado e protegido contra callbacks de sessões antigas.

Versões resolvidas e instruções específicas estão em [mobile/README.md](../mobile/README.md) e `mobile/pubspec.lock`. O cliente mantém a família compatível de `firebase_messaging` para obter tokens aceitos pelo backend Firebase Admin; não atualizar essa dependência para outra major sem revisar o contrato de entrega.

## Testes executados

- Python 3.12: **70 testes de API/regras aprovados** na execução consolidada; **mais 1 teste de startup completo aprovado** separadamente, total **71**.
- A suíte cobre login válido/inválido, endpoints protegidos, `/auth/me`, expiração/logout, permissões, dashboard, inventário, chamados, administração e tokens FCM.
- Concorrência exercitada com duas requisições, duas conexões SQLite e barreira antes do UPDATE: exatamente um atendimento vence e o outro recebe 409.
- Migrações usam banco legado descartável, com dados preservados e segunda execução idempotente.
- Compatibilidade web exercitada com HTML, cookie, APIs antigas, WebSocket web e broadcast compartilhado.
- Startup completo executa lifespan real, servidor TCP em porta temporária, criação de chamado pelo protocolo do professor e entrega aos dois WebSockets. Atendimento mobile aparece no endpoint web antigo.
- FCM usa mocks, sem credenciais ou rede Google: payload, ID para abertura interna, prioridade, usuários/sessões inválidas, poda de token e isolamento de falhas.

- Flutter 3.44.8 / Dart 3.12.2: `flutter analyze` sem problemas; **39 testes aprovados** na suíte final consolidada (29 core, 4 push e 6 widgets).
- Testes Flutter incluem 401 atrasado sem apagar sessão nova, restore offline, timeout de envio/leitura, certificado inválido, navegação privada após expiração, abertura do chamado por notificação, registro FCM atrasado/logout idempotente e dashboard em 320 px com texto ampliado.
- Regressão adicional comprovada: cache de usuário corrompido seguido de login falho em outro servidor não envia o Bearer antigo à nova origem no próximo startup. Persistência grava o token novo por último.
- Total final: **110 testes aprovados**. Android SDK 36, build-tools 36.0.0 e NDK 28.2 foram preparados em pasta isolada, fora do repositório; `flutter doctor` aprovou o toolchain Android. `flutter build apk --debug` gerou APK com sucesso, incluindo a última correção de sessão.
- O primeiro build revelou falha do cache incremental Kotlin quando projeto e Pub Cache estão em discos Windows diferentes. `kotlin.incremental=false` corrigiu o build, sem alterar as fontes do SDK nem ignorar erros de compilação. O build final terminou em 13,1 segundos usando as dependências já preparadas.

### APK de desenvolvimento

- Arquivo local: `dist/mobile/manutencao-ti-debug.apk` (cópia do build final).
- Tamanho: 184.089.374 bytes, aproximadamente 175,6 MiB. APK universal com ARM32, ARM64 e x86_64; tamanho debug não representa o pacote release.
- SHA-256: `9443D0B4CE5FA8DD41918EC52D13721B6AC54368063BAC1D2F0B55C14395917D`.
- `apksigner verify --verbose`: assinatura v2 verificada.
- Manifesto inspecionado: pacote `br.com.manutencao.manutencao_mobile`, nome Manutenção TI, versão 1.0.0+1, Android mínimo API 24 e target API 36, permissões Internet/notificações presentes.
- O binário está ignorado pelo Git; pode ser reproduzido por `flutter build apk --debug`. Para usar, atualize o backend com esta branch e dependências, instale o APK e informe a URL acessível do servidor na tela de login. Use as mesmas contas do site.
- Esse APK foi compilado sem configuração Firebase real. Para ativar push, configure os arquivos nativos e credenciais do backend, compile novamente e execute o roteiro em aparelho físico.

A validação automatizada não substitui o teste em dispositivo com o Firebase configurado. A suíte Python também emitiu avisos de depreciação de padrões herdados (`datetime.utcnow` e assinatura de templates); não foram falhas de teste nem justificaram uma migração de datas fora do escopo.

## Firebase e validação externa

Código disponível, configuração real ainda pendente. Siga [os dez passos de configuração e teste](mobile.md#firebase-cloud-messaging-configuração-manual), incluindo:

- Registrar pacote Android correto no projeto Firebase e gerar configuração FlutterFire/nativa.
- Instalar a configuração Android/iOS localmente, sem versionar arquivos privados.
- Guardar JSON da conta de serviço fora do repositório e definir variáveis no processo FastAPI.
- Conceder permissão no aparelho e verificar foreground, background, bloqueio e toque abrindo o chamado correto.
- Para iOS, configurar APNs/assinatura e compilar em macOS/Xcode.

Nenhuma credencial Firebase foi criada, incluída ou enviada ao Git. Entrega real de push não foi declarada testada. FCM do MVP usa thread após commit, sem fila persistente de reentrega.

## Git

Branch: `codex/mobile-flutter`, criada a partir de `9a5ba36`. Markdown do usuário foi preservado como arquivo não rastreado. Não houve merge na `main`, publicação nem push remoto.

Commits por etapa:

- `2940ac7` — `feat(api): add authenticated mobile endpoints`
- `0aa2133` — `feat(push): deliver ticket alerts through FCM`
- `ee9901e` — `test: cover mobile API and web compatibility`
- `8509059` — `feat(mobile): add Flutter maintenance client`
- `9b426ce` — `chore(build): ignore Kotlin compiler state`
- `3816c14` — `fix(build): support Pub Cache on another drive`
- `9455d4c` — `fix(auth): keep mobile tokens bound to server`

SHA do código validado e compilado: **`9455d4c`**. A documentação é um commit separado posterior; o SHA final da branch consta na mensagem de entrega e em `git log -1`. Principais arquivos: `app/api/v1/`, `app/schemas/`, `app/services/maintenance.py`, `app/security.py`, `app/fcm.py`, modelos/CRUD/migração, `mobile/`, `tests/`, `requirements-dev.txt`, README, CLAUDE e documentação.

## Pendências e limites

- Configuração Firebase e teste de notificações em aparelho físico.
- Validação iOS em macOS/Xcode e aparelho provisionado.
- Assinatura de release e distribuição institucional; build debug serve desenvolvimento.
- Testes físicos de Wi-Fi, certificado HTTPS confiável e políticas de economia de bateria.
- Persistência/reentrega de notificações após falha do processo não implementada neste MVP.
- A família Firebase compatível emite aviso de migração futura do plugin Kotlin no Flutter. Atualizações de Flutter/Firebase precisam revisar conjuntamente esse plugin e o contrato de token FCM.
- Senha HopToDesk segue como dívida técnica do web, deliberadamente ausente da API mobile.

Os dados de produção não foram usados na execução dos testes. O backend da escola precisa ser atualizado normalmente para disponibilizar as novas rotas ao aplicativo.
