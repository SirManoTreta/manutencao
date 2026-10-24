# Aplicativo Manutenção TI

Cliente Flutter/Dart do FastAPI existente. Android é o alvo inicial; estrutura iOS incluída. O aplicativo usa o mesmo banco, regras e usuários do site. Não existe banco paralelo nem comunicação direta com os PCs dos professores.

## Recursos

- Login Bearer, sessão persistida em armazenamento seguro e logout com revogação.
- Servidor configurável na tela de entrada, sem IP de produção embutido.
- Dashboard com indicadores, chamados recentes, máquinas atualizadas e distribuições.
- Chamados abertos/em atendimento/finalizados, detalhe, assumir e finalizar com diagnóstico.
- WebSocket autenticado, reconexão progressiva, sincronização após reconectar e retomar aplicativo.
- Cadastro, edição, exclusão e detalhes de máquinas, incluindo hardware, software, periféricos, vistorias e checkups.
- Pesquisa e filtros por perfil, segmento, sala/status, vistoria e checkup.
- Salas com pior status das máquinas e alteração coletiva de status.
- Computadores online com heartbeat e usuário/tela de login.
- Administração de usuários para administradores e perfil/configuração de notificações.
- FCM em background/encerrado, aviso local em foreground e abertura do chamado ao tocar. Firebase é opcional para iniciar/login; exige configuração externa para entregar push.

## Executar

SDK utilizado na implementação: Flutter 3.44.8 stable / Dart 3.12.2. Android mínimo 7.0 (API 24); iOS mínimo 15.0. Instale SDK Android, Java compatível e aceite licenças conforme `flutter doctor`.

```powershell
cd mobile
flutter pub get
flutter doctor
flutter run
```

Na entrada informe a origem do servidor, por exemplo `http://192.168.1.10:8000`, usuário e senha já cadastrados no site. O telefone precisa alcançar o FastAPI; configure rede/firewall do servidor. No emulador Android, `http://10.0.2.2:8000` acessa o computador hospedeiro. O endereço não inclui `/api/v1`: o cliente acrescenta esse prefixo.

Acesso HTTP foi habilitado nas plataformas para suportar IPs dinâmicos da LAN existente. Em HTTP, credenciais e tráfego atravessam a rede sem criptografia: use rede confiável e prefira HTTPS com certificado confiável. O cliente não ignora erros de certificado. Para trocar servidor, use Perfil > Sair / trocar servidor e edite o endereço na entrada.

```powershell
flutter analyze
flutter test
flutter build apk --debug
```

O APK de debug aparece em `build/app/outputs/flutter-apk/app-debug.apk`. Publicação exige configurar chave de assinatura de produção; a configuração inicial de release gerada pelo Flutter usa assinatura de desenvolvimento. iOS precisa de macOS/Xcode e assinatura Apple. Não foi validado em hardware físico durante a implementação.

O projeto desativa compilação incremental Kotlin para suportar Windows com Pub Cache e repositório em discos diferentes. Isso evita `this and base files have different roots`; recompilações Kotlin podem demorar mais. A propriedade usada está na [documentação Kotlin](https://kotlinlang.org/docs/gradle-compilation-and-caches.html).

## Configurar Firebase no Android

1. Crie projeto no [Firebase Console](https://console.firebase.google.com/).
2. Registre aplicativo Android com package **`br.com.manutencao.manutencao_mobile`**.
3. Baixe `google-services.json` e salve em `mobile/android/app/google-services.json`. O plugin Gradle Google Services já é aplicado condicionalmente quando esse arquivo existe. Sem arquivo, o aplicativo continua funcionando com push indisponível.
4. Configure credencial de serviço do **mesmo projeto** no backend conforme [guia FCM](../docs/mobile_push_firebase.md). Credencial privada fica somente no servidor, nunca no celular/Git.
5. Compile/reinstale e entre no aplicativo. Aceite permissão de notificações no sistema. Perfil mostra estado do registro; botão Ativar / verificar notificações permite tentar novamente.
6. Use dispositivo/emulador com Google Play Services e conexão à internet. Backend também precisa alcançar os serviços Google para enviar push.
7. Crie chamado pelo Professor_auto e valide foreground, background, tela bloqueada e abertura pelo toque. Payload contém `ticket_id`; canal Android é `maintenance_tickets`. O token é enviado autenticado em `POST /api/v1/push/register` e desativado por `POST /api/v1/push/unregister` no logout.

O aplicativo inicializa Firebase a partir da configuração nativa. Não depende de `firebase_options.dart` nem de projeto Firebase fictício. Arquivos de configuração local estão ignorados no Git. IDs públicos de cliente não substituem a credencial privada do servidor.

## Configurar Firebase no iOS

1. No mesmo projeto Firebase registre app Apple com bundle **`br.com.manutencao.manutencaoMobile`** (bundle gerado para iOS difere do Android).
2. Baixe `GoogleService-Info.plist`, coloque em `mobile/ios/Runner/` e adicione ao target Runner no Xcode, incluindo o arquivo nos recursos do aplicativo.
3. Configure equipe/provisionamento e habilite **Push Notifications** e **Background Modes > Remote notifications** no target Runner. Xcode deve gerar o entitlement `aps-environment` adequado ao perfil de assinatura.
4. Faça upload da chave APNs `.p8`, Key ID e Team ID nas configurações Cloud Messaging do Firebase. Guarde chave privada fora do repositório.
5. Keychain está declarado em `Runner.entitlements`; deployment target 15.0 e modo remote-notification já estão incluídos. Confirme capabilities/assinatura no Mac.
6. Compile no macOS e teste em dispositivo Apple real com permissão de notificações. Autorize acesso à rede local quando solicitado.

## Arquitetura do cliente

`lib/core/api_client.dart` centraliza JSON, Bearer, timeout total de 15 segundos, mensagens de conexão/certificado e HTTP 401. `SessionController` usa `ChangeNotifier` e uma interface de armazenamento testável; implementação nativa usa `flutter_secure_storage` (Android Keystore e Apple Keychain). Senhas não são persistidas. Expiração troca toda navegação privada pela entrada. A API não fornece senha HopToDesk; o aplicativo trabalha apenas com seu ID.

`TicketRealtime` usa cabeçalho Authorization na conexão `ws(s)://servidor/ws/v1/tickets`, ping e reconexão com espera progressiva até 32 segundos. Conectar/reconectar provoca nova consulta dos chamados e dashboard, recuperando eventos perdidos. Background suspende socket; retomar reabre e sincroniza.

`PushService` mantém fila serial de registro/remoção e geração por sessão para impedir que callback atrasado registre dispositivo após logout/troca de conta. `getInitialMessage`, `onMessageOpenedApp` e callback local encaminham `ticket_id` ao detalhe; toque antes do login aguarda autenticação. Logout limpa navegação pendente e notificações locais. O sistema operacional exibe payload `notification` em background; foreground usa `flutter_local_notifications`.

Dependências Firebase foram mantidas na série **firebase_messaging 16.7.x / firebase_core 4.x** e fixadas pelo `pubspec.lock`. A versão 17 muda o registro para FID/direct-send; não atualizar para 17 antes de migrar o envio do backend, que usa token FCM com Firebase Admin. Confira [API 16.7.1](https://pub.dev/documentation/firebase_messaging/16.7.1/firebase_messaging/FirebaseMessaging-class.html) e [histórico oficial](https://pub.dev/packages/firebase_messaging/changelog).

Estados de rede usam loading, vazio, erro com nova tentativa e pull-to-refresh. O armazenamento local mantém somente configuração e sessão, sem replicar dados operacionais. Datas UTC recebidas do servidor são exibidas no fuso do dispositivo.

## Testes e limites

Esta atualização passou em `flutter analyze`, **66 testes Flutter** e `flutter build apk --debug`. O APK atualizado está em `dist/mobile/manutencao-ti-debug.apk`, fora do versionamento. Resultados completos e hash estão no [relatório FCM](../docs/mobile-push-implementation-report.md); configuração e roteiro físico estão no [guia FCM](../docs/mobile_push_firebase.md).

`test/core_test.dart` cobre autenticação, estado, armazenamento, modelos, timeout de envio/leitura, TLS, erros e HTTP 401 atrasado. `test/widget_test.dart` cobre entrada, navegação, atendimento, limpeza de rotas após expiração, destino de notificação e layout de 320 px com texto ampliado. `test/push_test.dart` verifica contrato Bearer e metadados, tipos/IDs inválidos, refresh real por stream, inicialização sem Firebase, foreground sem duplicação, initialMessage/toque/local, permissão negada, diagnóstico seguro, logout idempotente, token de teste guardado e cancelamento de callback atrasado.

Testes usam HTTP e dispositivo FCM simulados. Push real depende de projeto/credenciais Firebase/APNs, permissões, internet, Google Play Services, políticas de energia e entrega do sistema operacional. Android force-stop e restrições do iOS podem exigir reabrir app; não se promete entrega após fechamento forçado. Valide a matriz em hardware antes do uso em produção.

Arquitetura completa, rotas e operação do servidor: [docs/mobile.md](../docs/mobile.md). Referências primárias: [Flutter](https://docs.flutter.dev/), [Firebase Flutter setup](https://firebase.google.com/docs/flutter/setup), [recebimento FCM](https://firebase.google.com/docs/cloud-messaging/flutter/receive-messages).


## Atualização FCM: configuração e contrato

A implementação está pronta e aguarda configuração externa do Firebase. Nenhum projeto, credencial administrativa ou aparelho real foi usado para validar entrega de push nesta etapa. O roteiro completo de configuração e teste está em [docs/mobile_push_firebase.md](../docs/mobile_push_firebase.md).

Depois de criar o projeto e registrar o package existente no Console, instale Firebase CLI/FlutterFire CLI e execute dentro de `mobile/`:

```powershell
firebase login
dart pub global activate flutterfire_cli
flutterfire configure --platforms=android --android-package-name=br.com.manutencao.manutencao_mobile
```

Selecione o projeto real e o aplicativo com o package indicado. Não altere o applicationId para executar esse comando. Confirme `android/app/google-services.json` e correspondência ao app cadastrado. No iOS, mantenha bundle `br.com.manutencao.manutencaoMobile` e adicione `GoogleService-Info.plist` ao target Runner no Xcode.

`firebase_bootstrap.dart` inicializa Firebase com os arquivos nativos gerados pelo FlutterFire, tanto no aplicativo quanto no isolate de background. O `firebase_options.dart` público gerado pela CLI pode ficar no projeto, mas não é importado nesse fluxo Android/iOS; sua ausência não quebra o build. Não há configuração fictícia ou dependência de arquivo gerado inexistente. Se forem adicionadas plataformas Web ou múltiplos projetos Firebase, adapte o bootstrap para usar explicitamente `DefaultFirebaseOptions.currentPlatform` após gerar o arquivo real.

O registro acontece após autenticação e permissão concedida:

```text
POST /api/v1/push/register
{fcm_token, platform, device_name}

POST /api/v1/push/unregister
{fcm_token}

GET /api/v1/push/status
{enabled, credentials_configured, active_devices}
```

As três rotas usam Bearer; `user_id` nunca vem do celular. `device_info_plus` informa fabricante/modelo Android ou modelo e código de hardware Apple, com fallback para plataforma. Nenhum identificador permanente de hardware ou nome pessoal do usuário é coletado. No iOS 16+, o nome pessoal exigiria entitlement extra; ele não é solicitado.

Perfil mostra confirmação de registro e horário, nome do dispositivo e estado do backend. `credentials_configured` indica configuração informada, sem comprovar validade da conta ou entrega. Falha do diagnóstico não desfaz registro nem impede login. Registro só é apresentado como confirmado depois de resposta `{registered:true}`.

Para a mensagem de teste do Firebase Console, builds **debug** mostram a ação explícita **Copiar token de teste** após login e permissão. O token é colocado somente no clipboard local para ser colado no Console, sem print/log/API de consulta pública. Mantenha privado. Builds release não exibem essa ação; leitura assíncrona é descartada se a sessão mudar.

Payload reconhecido:

```json
{"type":"new_ticket","ticket_id":"42"}
```

O parser também aceita o tipo anterior `ticket_created` durante atualização dos servidores. Exige ID decimal positivo em string, dentro do intervalo inteiro; eventos desconhecidos, `ticket_taken`, `ticket_closed` e IDs inválidos não abrem telas nem geram alertas locais. Notificação local guarda o mesmo envelope JSON validado.

WebSocket atualiza listas/dashboard sem produzir alerta nativo. FCM é o único produtor do alerta em foreground, apresentado por `flutter_local_notifications`. Um conjunto limitado aos últimos 256 chamados da sessão evita avisos repetidos do mesmo ID; o conjunto reinicia ao trocar sessão/servidor. Background/encerrado usa a apresentação do sistema operacional, sem notificação local adicional no handler. O toque usa `getInitialMessage`, `onMessageOpenedApp` ou callback local, conforme origem. Destino pendente aguarda login e não atravessa logout ou troca de servidor.

Os testes automatizados usam adaptadores de dispositivo, eventos Firebase e apresentação local simulados. Não enviam push real. Depois de configurar, valide mensagem de teste com `type` e `ticket_id`, depois chamado real do Professor_auto em foreground, background, tela bloqueada e aplicativo encerrado normalmente. Force-stop e políticas do sistema podem exigir reabrir o app.

Referências primárias: [FlutterFire CLI](https://firebase.flutter.dev/docs/cli), [receber mensagens Flutter](https://firebase.google.com/docs/cloud-messaging/flutter/receive-messages), [device_info_plus](https://pub.dev/packages/device_info_plus).
