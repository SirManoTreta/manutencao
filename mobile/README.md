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

## Configurar Firebase no Android

1. Crie projeto no [Firebase Console](https://console.firebase.google.com/).
2. Registre aplicativo Android com package **`br.com.manutencao.manutencao_mobile`**.
3. Baixe `google-services.json` e salve em `mobile/android/app/google-services.json`. O plugin Gradle Google Services já é aplicado condicionalmente quando esse arquivo existe. Sem arquivo, o aplicativo continua funcionando com push indisponível.
4. Configure credencial de serviço do **mesmo projeto** no backend conforme [documentação principal](../docs/mobile.md). Credencial privada fica somente no servidor, nunca no celular/Git.
5. Compile/reinstale e entre no aplicativo. Aceite permissão de notificações no sistema. Perfil mostra estado do registro; botão Ativar / verificar notificações permite tentar novamente.
6. Use dispositivo/emulador com Google Play Services e conexão à internet. Backend também precisa alcançar os serviços Google para enviar push.
7. Crie chamado pelo Professor_auto e valide foreground, background, tela bloqueada e abertura pelo toque. Payload contém `ticket_id`; canal Android é `maintenance_tickets`. O token é enviado autenticado em `POST /api/v1/devices` e removido no logout.

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

`test/core_test.dart` cobre autenticação, estado, armazenamento, modelos, timeout de envio/leitura, TLS, erros e HTTP 401 atrasado. `test/widget_test.dart` cobre entrada, navegação, atendimento, limpeza de rotas após expiração, destino de notificação e layout de 320 px com texto ampliado. `test/push_test.dart` verifica registro Bearer, permissão negada, logout idempotente e cancelamento de registro atrasado na troca de servidor.

Testes usam HTTP e dispositivo FCM simulados. Push real depende de projeto/credenciais Firebase/APNs, permissões, internet, Google Play Services, políticas de energia e entrega do sistema operacional. Android force-stop e restrições do iOS podem exigir reabrir app; não se promete entrega após fechamento forçado. Valide a matriz em hardware antes do uso em produção.

Arquitetura completa, rotas e operação do servidor: [docs/mobile.md](../docs/mobile.md). Referências primárias: [Flutter](https://docs.flutter.dev/), [Firebase Flutter setup](https://firebase.google.com/docs/flutter/setup), [recebimento FCM](https://firebase.google.com/docs/cloud-messaging/flutter/receive-messages).
