# Relatório: configuração de push nativo FCM

Etapa de 24/10/2026. **A implementação está pronta e aguarda configuração externa do Firebase.** Entrega real não foi validada: nenhum projeto configurado, conta de serviço válida ou aparelho Android real foi usado nos testes desta etapa.

## Backend

Arquivos criados:

- `app/api/v1/push.py`: rotas autenticadas de registro, desativação e diagnóstico.
- `app/schemas/push.py`: entradas validadas e respostas sem tokens.
- `app/services/mobile_devices.py`: persistência compartilhada e upsert atômico.

Arquivos modificados: `app/models.py`, `app/main.py`, `app/fcm.py`, `app/chamados_socket.py`, `app/api/v1/auth.py`, `app/api/v1/router.py`, `.env.example` e `.gitignore`.

O Firebase Admin SDK já estava declarado em `requirements.txt` (`firebase-admin>=7.1,<8`); não foi duplicado nem substituído. `app/fcm.py` continua como serviço de entrega separado de `main.py` e do Web Push.

Endpoints novos, todos com Bearer:

| Método | Endpoint | Comportamento |
| --- | --- | --- |
| POST | `/api/v1/push/register` | Recebe `fcm_token`, `platform` e `device_name` opcional; registra/atualiza e reativa |
| POST | `/api/v1/push/unregister` | Desativa token pertencente ao usuário autenticado; operação idempotente |
| GET | `/api/v1/push/status` | Retorna `enabled`, `credentials_configured`, `active_devices`; sem token ou caminho privado |

`user_id` no payload é rejeitado. O usuário vem da sessão autenticada. `/api/v1/devices` permanece compatível com a primeira entrega mobile e usa o mesmo serviço de registro.

Não foi criada outra tabela ou banco. A tabela `fcm_devices` recebeu `device_name`, `is_active` e `created_at`. Migração SQLite aditiva preserva tokens/associações anteriores, preenche criação a partir da atualização existente e pode executar novamente sem duplicar colunas ou dados. O digest único evita duplicação do mesmo token; um usuário continua podendo registrar vários aparelhos.

Credencial externa preferida: `GOOGLE_APPLICATION_CREDENTIALS`. Alias `FIREBASE_CREDENTIALS` preservado, com menor prioridade. Firebase Admin só é inicializado quando configurado e há tentativa de envio; ausência/falha de configuração não interrompe o sistema. Nenhuma credencial foi gerada ou baixada pelo código.

O ponto de integração é `app/chamados_socket.py`, em `_TicketTCPHandler.handle`, **após `db.commit()`**. O fluxo tenta WebSocket, Web Push e FCM nessa ordem, com falhas isoladas. Nenhum Ticket duplicado e nenhuma alteração em `Professor_auto.py` ou no protocolo TCP.

FCM entrega título “Novo chamado — TI”, sala/PC/problema e dados `type="new_ticket"`, `ticket_id` string. WebSocket/Web Push mantêm o evento `ticket_created` anterior. Prioridade Android alta, canal `maintenance_tickets` e configuração APNs preservados.

O envio considera usuário/dispositivo ativos, sessão não expirada e hash de senha ainda correspondente. Tokens rejeitados são desativados; erros genéricos/transitórios não desativam registros válidos. Resposta tardia não desativa token renovado durante envio. Limite de tamanho considera JSON escapado, inclusive aspas, barras e controles. Logs registram configuração declarada, contagens e classe das falhas, sem segredos nem token.

## Flutter

Arquivos criados:

- `mobile/lib/core/firebase_bootstrap.dart`: inicialização nativa FlutterFire compartilhada.
- `mobile/lib/core/push_platform.dart`: adaptadores Firebase Messaging e notificações locais.
- `mobile/lib/models/ticket_notification.dart`: parsing tipado do evento e payload local.

Atualizados `push_service.dart`, `app.dart`, `pubspec.yaml`/lock, testes de push/widgets e README mobile.

`firebase_core` 4.x, `firebase_messaging` 16.x e `flutter_local_notifications` já existiam. Foi acrescentado `device_info_plus` 13.3.0 para fabricante/modelo do Android e identificação de hardware iOS, sem exigir o nome pessoal do aparelho.

- Login registra token e nome do dispositivo nas rotas novas. `onTokenRefresh` registra o novo e desativa o anterior.
- Permissão solicitada pelo SDK, incluindo Android moderno; recusa mantém o app utilizável e permite nova tentativa pelo Perfil.
- Foreground: WebSocket somente recarrega dados; FCM exibe um aviso local, com deduplicação de até 256 IDs por sessão/origem.
- Background: handler de nível superior com `@pragma('vm:entry-point')`; notificação de sistema fica a cargo do Android/iOS, evitando duplicação.
- App encerrado: `getInitialMessage`; retorno do background: `onMessageOpenedApp`; aviso local: callback do plugin.
- Payload aceito: `new_ticket` e `ticket_created` legado, com ID positivo em string. Tipo desconhecido/ID inválido não provoca navegação.
- Toque antes do login mantém destino pendente; após autenticação abre o detalhe. Guards de sessão/origem impedem destino já pendente de atravessar logout/troca de servidor.
- Registro, refresh e limpeza são serializados e protegidos contra callbacks atrasados. Logout chama unregister e limpa token nativo, alertas e sessão.
- Perfil mostra permissão, nome, confirmação e diagnóstico seguro do backend. Apenas no debug há ação explícita **Copiar token de teste**, sem imprimir token em logs ou exibi-lo em texto.

O bootstrap consome arquivos nativos produzidos pelo FlutterFire. Não há import de `firebase_options.dart` inexistente nem valores fictícios. A documentação explica onde o arquivo gerado pode ficar e por que o JSON/Plist nativo continua necessário neste fluxo.

## Firebase: ações manuais pendentes

Package Android mantido: **`br.com.manutencao.manutencao_mobile`**. Bundle iOS mantido: `br.com.manutencao.manutencaoMobile`.

Falta você:

1. Criar/escolher projeto Firebase e registrar o Android com o package exato.
2. Fazer `firebase login`, instalar FlutterFire CLI e executar `flutterfire configure`.
3. Colocar `google-services.json` real em `mobile/android/app/` e recompilar/reinstalar o app.
4. Gerar service account no projeto correto, guardá-la somente no servidor e configurar `GOOGLE_APPLICATION_CREDENTIALS` e `FCM_ENABLED=true` no processo FastAPI.
5. Conceder notificações, verificar registro, testar Console e depois chamado real do Professor_auto, com background, encerramento normal, bloqueio e toque abrindo o detalhe.

O passo a passo, comandos e sequência completa de 14 verificações estão em [docs/mobile_push_firebase.md](mobile_push_firebase.md). Para iOS, ainda são necessários APNs, assinatura e validação macOS/Xcode/aparelho Apple.

`credentials_configured=true` significa caminho informado, não prova de chave válida ou de entrega. O APK desta entrega foi compilado sem `google-services.json`/Plist reais; ainda precisa do novo build após configuração. Nenhum segredo administrativo está no app ou no Git.

## Testes e artefato

- **107 testes Python aprovados**, execução consolidada em 25,71 s, Python 3.12, SQLite temporário e Firebase simulado.
- Cobertura: registro/atualização/unregister, associação ao usuário, várias sessões/dispositivos, negação sem Bearer, metadados, compatibilidade `/devices`, migração legada, payload nativo, rejeições e falhas do provedor, logs seguros e fluxo TCP/WebSocket/Web Push.
- SDK Firebase real usado para validar objetos/serialização; envio foi mockado, sem rede ou credencial real.
- Três regressões reproduziram mensagens JSON acima do limite com aspas/barras/controles; passaram após corrigir o orçamento serializado.
- **66 testes Flutter aprovados**: 29 core, 30 push e 7 widgets; streams de refresh/foreground/toque, parser, permissão, registro/logout, deduplicação, diagnóstico, token debug e navegação.
- `flutter analyze`: sem problemas. **Total: 173 testes aprovados.**
- `flutter build apk --debug`: aprovado em 34,6 s com SDK Android 36. Mantido aviso conhecido do plugin Firebase/Kotlin para evolução futura; não houve erro de compilação.
- `apksigner verify`: assinatura v2 verificada; manifesto confirma package existente, API mínima 24, target 36 e versão 1.0.0+1.

APK local atualizado: `dist/mobile/manutencao-ti-debug.apk`, 184.231.671 bytes (~175,7 MiB). Binário ignorado pelo Git.

SHA-256 do APK:

```text
283A56E73DF75100823EA59223BD2248BFC5CF12C8F1AD49F8B712C5BC1770CC
```

Não testados: entrega real pelo Google/APNs, notificações em aparelho físico/bloqueado e build iOS. O envio continua em thread após commit, sem fila persistente de reentrega. Force-stop e restrições do sistema operacional não equivalem a encerramento normal.

## Git

Branch continuada: **`codex/mobile-flutter`**. Base desta etapa: `763c9ad`. Os dois prompts markdown do usuário permanecem não rastreados e preservados.

Commits de código/testes desta etapa:

- `9533648` — `feat(push): complete native FCM infrastructure`
- `462ea0d` — `test(push): cover registration and payload limits`
- `81b2f5e` — `feat(mobile): finish native push lifecycle`

SHA do código validado e compilado: **`81b2f5e`**. O commit de documentação é posterior; SHA final consta na mensagem de entrega e em `git log -1`. Nenhum merge na main ou push remoto foi executado.
