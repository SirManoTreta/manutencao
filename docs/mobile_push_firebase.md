# Push nativo com Firebase Cloud Messaging

## Situação desta entrega

A implementação está pronta para configuração externa do Firebase. Os testes automatizados usam transporte simulado. Nenhum projeto Firebase foi criado, nenhuma service account foi gerada/baixada e nenhum push real foi enviado durante o desenvolvimento. Validar entrega em celular real exige os passos abaixo.

O app Android mantém o identificador existente **`br.com.manutencao.manutencao_mobile`**. Use exatamente esse package no Firebase Console. Não é necessário trocar o applicationId nem recriar o aplicativo mobile.

```text
Professor_auto.exe
       | TCP existente :5050
       v
FastAPI grava Ticket no SQLite e confirma commit
       +-- WebSocket: site e Flutter abertos recarregam dados
       +-- Web Push/VAPID: navegador/PWA
       +-- Firebase Admin: FCM nativo Android/iOS
                                  |
                                  v
                         toque abre chamado pelo ID
```

Os três transportes são independentes. Falha de Firebase, inclusive na inicialização ou criação da thread, não desfaz o chamado nem impede WebSocket/Web Push. Flutter nunca se conecta diretamente ao computador do professor.

## 1. Preparar Firebase Console e Android

No [Firebase Console](https://console.firebase.google.com/), crie ou escolha um projeto e adicione um app Android. Informe **`br.com.manutencao.manutencao_mobile`** no campo Android package name; apelido é opcional. Baixe a configuração pública `google-services.json` e coloque em:

```text
mobile/android/app/google-services.json
```

Confirme que o JSON pertence ao projeto escolhido e ao mesmo package. O Gradle já aplica Google Services quando o arquivo existe. Sem ele o app compila e atende operações REST, mas informa que push não está configurado. [Configuração oficial Flutter](https://firebase.google.com/docs/flutter/setup).

Os arquivos `google-services.json`, `GoogleService-Info.plist` e `firebase_options.dart` descrevem o cliente Firebase; **não são a chave administrativa do servidor**. Neste repositório ficam locais/ignorados para não vincular todo clone a um ambiente específico. A service account privada nunca deve entrar no Flutter ou no APK.

## 2. Executar FlutterFire

Com Node.js, Flutter e Dart no PATH, execute em PowerShell:

```powershell
npm install -g firebase-tools
firebase login
dart pub global activate flutterfire_cli
Set-Location F:\Claudezin\manutencao_site_ATT\mobile
dart pub global run flutterfire_cli:flutterfire configure --project=SEU_PROJECT_ID --platforms=android
flutter pub get
```

Substitua `SEU_PROJECT_ID` pelo ID real do projeto. Se preferir seleção interativa, use `flutterfire configure` após incluir o diretório de executáveis do Pub no PATH. Selecione o projeto existente e o app com package acima; não aceite alterar o package por engano.

Confira a presença de `android/app/google-services.json`. O FlutterFire pode gerar também `lib/firebase_options.dart`. O bootstrap atual usa `Firebase.initializeApp()` com as configurações nativas de Android/iOS; não importa um arquivo Dart inexistente nem contém valores fictícios. Portanto, o arquivo Dart gerado pode permanecer disponível para evolução futura, mas não substitui os recursos nativos nesse fluxo. Reexecute a configuração ao acrescentar plataforma/produto Firebase. [Fluxo oficial FlutterFire](https://firebase.google.com/docs/flutter/setup).

Dependências compatíveis estão em `pubspec.lock`: `firebase_core` 4.x, `firebase_messaging` 16.x, `flutter_local_notifications` e `device_info_plus`. A major 17 de Messaging altera o contrato de registro; não atualizar isoladamente sem adaptar o backend Firebase Admin. Consulte também [mobile/README.md](../mobile/README.md).

## 3. Preparar credencial privada do backend

No projeto Firebase, abra Configurações do projeto > Contas de serviço > Firebase Admin SDK e gere uma chave privada para o servidor. Salve o JSON fora do repositório, por exemplo:

```text
C:\Manutencao\secrets\firebase-service-account.json
```

A conta precisa de permissão para enviar mensagens no mesmo projeto do app. Confirme que a API Firebase Cloud Messaging HTTP v1 está habilitada no projeto Google Cloud correspondente. Não copie o JSON para `mobile/`, não envie pela API e não inclua em commits. [Configuração oficial do Admin SDK](https://firebase.google.com/docs/admin/setup).

No terminal que iniciará o backend:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\Manutencao\secrets\firebase-service-account.json'
$env:FCM_ENABLED = 'true'
# Opcional: deve corresponder ao projeto da conta e do app.
$env:FIREBASE_PROJECT_ID = 'SEU_PROJECT_ID'
Set-Location F:\Claudezin\manutencao_site_ATT
py -3.12 -m pip install -r requirements.txt
py -3.12 -m app.main
```

Em `cmd.exe`, o equivalente é:

```bat
set GOOGLE_APPLICATION_CREDENTIALS=C:\Manutencao\secrets\firebase-service-account.json
set FCM_ENABLED=true
py -3.12 -m app.main
```

As variáveis precisam existir no processo que roda o FastAPI. Se iniciar por serviço ou tarefa agendada, configure o ambiente e as permissões de leitura da conta executora. Reinicie o backend após mudar a credencial. O projeto não carrega `.env` automaticamente.

Para manter configuração somente nesta instalação, `run.bat` carrega um arquivo opcional `run.local.bat`, ignorado pelo Git, antes de iniciar Python. Você pode guardar nele os comandos `set "GOOGLE_APPLICATION_CREDENTIALS=CAMINHO_DO_JSON"` e `set "FCM_ENABLED=true"`. O inicializador usa sua própria pasta como diretório e mantém essas variáveis no processo, sem alterar configurações globais do Windows. Não coloque a chave privada no batch: ele contém apenas o caminho do JSON. Nesta instalação esse arquivo local já foi preparado; nos próximos inícios use `run.bat`.

`GOOGLE_APPLICATION_CREDENTIALS` tem prioridade sobre o alias legado `FIREBASE_CREDENTIALS`. Sem caminho e sem ativação explícita, FCM fica desativado. `FCM_ENABLED=false` desativa mesmo com caminho informado. ADC gerenciado é suportado quando FCM é ativado explicitamente, mas não é necessário para esta instalação Windows.

O backend inicializa Firebase Admin somente ao precisar enviar. Não baixa nem gera credenciais. Falhas registram classe do erro e contexto, sem conteúdo da credencial, caminho completo ou token de dispositivo. O servidor precisa de saída HTTPS para os serviços Google.

## 4. Compilar, instalar e registrar o aparelho

Depois de colocar o JSON nativo real:

```powershell
Set-Location F:\Claudezin\manutencao_site_ATT\mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

Instale `mobile/build/app/outputs/flutter-apk/app-debug.apk` no Android. O APK compilado antes da configuração Firebase deve ser substituído pelo novo build. Para desenvolvimento conectado, `flutter run` também serve.

Use aparelho com Google Play Services, internet e acesso ao FastAPI pela LAN/VPN. Abra o app, informe servidor e conta existente do site, faça login e permita notificações. Android 13+ exige autorização em tempo de execução. Recusa não bloqueia inventário/atendimento; use Perfil > Ativar / verificar notificações para nova tentativa e, se o sistema não voltar a perguntar, habilite nas configurações Android do app.

No login, o cliente obtém token FCM e registra `platform` e nome do aparelho. `onTokenRefresh` atualiza o registro e desativa o token anterior. Logout solicita unregister e revoga a sessão; limpeza nativa também interrompe entrega quando o backend está indisponível.

Em Perfil, verifique confirmação do registro e estado do backend. O endpoint protegido `GET /api/v1/push/status` retorna:

```json
{
  "enabled": true,
  "credentials_configured": true,
  "active_devices": 1
}
```

`credentials_configured` significa somente que um caminho foi informado, **não valida a chave nem comprova entrega**. `active_devices` conta dispositivos do usuário com sessão válida e token ativo; um usuário pode ter vários celulares. A API nunca retorna os tokens completos.

## 5. Testar pelo Firebase Console

1. Faça login e ative notificações no aparelho de desenvolvimento.
2. Em Perfil, use **Copiar token de teste**, disponível somente em build debug autenticado. O token FCM identifica esse aparelho; mantenha-o privado e cole somente no projeto Firebase correspondente. A ação não copia senha, Bearer da API ou service account.
3. Coloque o app em background.
4. No Firebase Console, abra Messaging, crie uma notificação com título/corpo de teste e use a opção de enviar mensagem de teste para um token de registro.
5. Cole o token e envie. Confira notificação na bandeja/tela bloqueada. A nomenclatura das telas pode variar; o procedimento de teste é descrito no [guia oficial FCM para Flutter](https://firebase.google.com/docs/cloud-messaging/flutter/get-started).

Uma mensagem do Console sem dados `type`/`ticket_id` testa apenas entrega nativa, não abertura de chamado. Para testar o detalhe, acrescente os campos abaixo nas opções de dados, se disponíveis, ou use o chamado real da próxima etapa. O ID deve existir no backend selecionado no app:

```json
{"type": "new_ticket", "ticket_id": "42"}
```

O app também aceita o tipo legado `ticket_created`. Tipos desconhecidos, IDs ausentes/inválidos e payloads locais malformados não abrem um chamado arbitrário.

## 6. Validar o fluxo real Professor_auto

Execute a sequência completa:

1. Configure projeto Firebase e app Android com o package correto.
2. Execute `flutterfire configure` e confira o JSON nativo.
3. Guarde a service account somente no servidor.
4. Inicie FastAPI com `GOOGLE_APPLICATION_CREDENTIALS` e FCM ativado.
5. Compile e instale o app Android com a configuração real.
6. Faça login.
7. Conceda notificações.
8. Verifique registro no Perfil e `/api/v1/push/status`.
9. Coloque app em background.
10. Envie uma mensagem de teste pelo Console.
11. Abra um chamado pelo `Professor_auto` de um PC cadastrado.
12. Confira notificação com sala, PC e problema.
13. Toque na notificação.
14. Confira abertura do detalhe com o mesmo ID do chamado no site.

Repita com o app aberto, encerrado normalmente e com celular bloqueado. Em foreground, WebSocket recarrega listas/dashboard; FCM produz um único aviso local por chamado. Nenhum popup adicional é criado pelo WebSocket. Ao reconectar, o app busca o estado REST atual.

Teste também toque antes do login: app deve aguardar autenticação e então abrir o chamado. Logout/troca de servidor invalida navegação pendente da sessão anterior. Repita renovação de token, permissão negada e servidor temporariamente indisponível.

Não confunda app encerrado normalmente com **Forçar parada** nas configurações Android. Forçar parada pode impedir recebimento até reabertura; restrições do iOS e economia de bateria também afetam entrega. O celular precisa de internet para FCM e acesso ao FastAPI para consultar o detalhe. [Comportamento oficial de recebimento](https://firebase.google.com/docs/cloud-messaging/flutter/receive-messages).

## Contrato implementado

| Método | Endpoint | Corpo / resposta |
| --- | --- | --- |
| POST | `/api/v1/push/register` | `{fcm_token, platform, device_name?}`; `{registered: true}` |
| POST | `/api/v1/push/unregister` | `{fcm_token}`; `{unregistered: true}` |
| GET | `/api/v1/push/status` | `{enabled, credentials_configured, active_devices}` |

Todas as rotas exigem Bearer. `user_id` extra é rejeitado; associação vem da sessão validada. O registro faz upsert atômico por digest único do token, preserva criação e reativa registro anterior. Unregister é idempotente e só desativa token do usuário autenticado.

A tabela existente `fcm_devices` foi ampliada com `device_name`, `is_active` e `created_at`, mantendo `user_id`, `session_id`, token/digest, plataforma e atualização. Migração SQLite adiciona campos e preenche criação dos registros antigos sem apagar tokens. Nenhum banco ou backend novo foi criado. `/api/v1/devices` permanece disponível para clientes anteriores.

FCM envia `notification` e dados com `type="new_ticket"` e `ticket_id` string, canal Android `maintenance_tickets` e prioridade alta. Sala não associada recebe descrição segura. Somente usuários ativos, dispositivos ativos e sessões ainda válidas recebem o evento. Ainda não há envio FCM para assumir/finalizar chamado.

Tokens `UNREGISTERED` são desativados. `INVALID_ARGUMENT` só desativa quando a resposta estruturada identifica rejeição FCM e não há diagnóstico de payload inválido; erros genéricos, de permissão e transitórios mantêm o dispositivo. Resposta antiga não desativa token registrado novamente durante o envio. [Erros FCM](https://firebase.google.com/docs/cloud-messaging/error-codes) e [gestão de tokens](https://firebase.google.com/docs/cloud-messaging/manage-tokens).

Os logs mostram configuração declarada no startup, contagens por chamado/lote e falhas por classe. Nunca registram JSON privado, token ou valor bruto da exceção do provedor. Envio usa thread após commit; não existe fila persistente nem garantia de reentrega após queda do processo.

## Diagnóstico rápido

- **Firebase não configurado no app:** confira JSON nativo, package, projeto e reinstale build novo.
- **`enabled=false`:** confira ambiente do processo FastAPI e `FCM_ENABLED`.
- **`credentials_configured=false`:** confira `GOOGLE_APPLICATION_CREDENTIALS`; em ADC gerenciado, ausência de caminho é esperada.
- **`active_devices=0`:** entre novamente, conceda permissão e tente ativar; usuário/sessão precisam estar válidos.
- **Permissão negada:** ajuste notificações do aplicativo nas configurações Android/iOS.
- **`PermissionDeniedError` / `SenderIdMismatchError`:** confirme permissão da conta e que cliente/servidor pertencem ao mesmo projeto.
- **Console entrega, chamado não entrega:** confira registro autenticado, backend com credencial e logs FCM após criar chamado.
- **Push chega, detalhe não abre:** confirme dados `type` e `ticket_id`, autenticação e alcance LAN/VPN do FastAPI.
- **Foreground sem duplicação:** um aviso local FCM; WebSocket somente recarrega dados.

## iOS e segurança

O bundle iOS existente é `br.com.manutencao.manutencaoMobile`, diferente do package Android. Cadastre-o separadamente no mesmo projeto, adicione `GoogleService-Info.plist` ao target Runner, configure APNs/assinatura e capabilities Push Notifications e Background Modes/Remote notifications no Xcode. Compilar e validar iOS exige macOS e dispositivo provisionado; não foi feito neste ambiente Windows.

`.gitignore` protege `firebase-service-account*.json`, `service-account*.json`, arquivos `*firebase-adminsdk*.json`, pasta `secrets/`, `.env`, `*.pem`, `*.key` e chaves APNs `*.p8`. Configurações públicas locais de cliente também estão ignoradas por opção de ambiente. Nunca coloque chave privada em `firebase_options.dart` ou em qualquer recurso Flutter.

Para repetir testes sem Firebase real:

```powershell
py -3.12 -m pip install -r requirements-dev.txt
$testTemp = Join-Path $env:TEMP ('manutencao-push-' + [guid]::NewGuid().ToString('N'))
py -3.12 -m pytest tests -q --basetemp $testTemp
Set-Location mobile
flutter analyze
flutter test
```

Resultados e commits desta etapa constam em [relatório FCM](mobile-push-implementation-report.md).
