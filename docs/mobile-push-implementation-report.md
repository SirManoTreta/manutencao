# Relatório: configuração de push nativo FCM

Etapa de 24/10/2026. A implementação foi testada inicialmente com Firebase simulado. Na continuação da configuração local, os arquivos fornecidos pelo usuário foram conferidos, a credencial existente autenticou por OAuth e o APK foi recompilado com configuração Firebase real. **Entrega de notificação em aparelho ainda não foi validada.**

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

## Firebase: configuração local e validação pendente

Package Android mantido: **`br.com.manutencao.manutencao_mobile`**. Bundle iOS mantido: `br.com.manutencao.manutencaoMobile`.

Na continuação desta instalação:

1. Arquivos Android/Dart existentes conferidos: package, project ID, sender ID e app ID correspondem.
2. Service account existente, fornecida pelo usuário, conferida e autenticada por OAuth; nenhum push enviado.
3. `run.local.bat` ignorado preparado com caminho da credencial, FCM ativado e projeto correspondente. `run.bat` carrega configuração local sem alterar variáveis globais do Windows.
4. Banco existente copiado para backup local antes do startup; usuários preservados. FastAPI iniciado, login HTTP 200, API protegida HTTP 401 sem Bearer, portas 8000/5050 ativas e configuração FCM habilitada no startup.
5. APK recompilado e assinatura verificada; recursos nativos conferem com o projeto configurado. Usuário escolheu instalação manual no celular.

Falta instalar o APK atualizado, fazer login e conceder notificações; depois verificar registro, testar Console e chamado real do Professor_auto, com background, encerramento normal, bloqueio e toque abrindo o detalhe. Nenhum Android estava conectado por ADB durante essa continuação.

O passo a passo, comandos e sequência completa de 14 verificações estão em [docs/mobile_push_firebase.md](mobile_push_firebase.md). Para iOS, ainda são necessários APNs, assinatura e validação macOS/Xcode/aparelho Apple.

`credentials_configured=true` sozinho significa caminho informado. Nesta instalação houve também validação OAuth separada e conferência dos recursos Firebase reais no APK, que não comprovam entrega FCM no aparelho ou permissão efetiva de envio. Nenhum segredo administrativo está no app ou no Git. Resumo local das verificações em `data/fcm-local-validation.json`, ignorado pelo Git.

## Testes e artefato

- **107 testes Python aprovados**, execução consolidada em 25,71 s, Python 3.12, SQLite temporário e Firebase simulado.
- Cobertura: registro/atualização/unregister, associação ao usuário, várias sessões/dispositivos, negação sem Bearer, metadados, compatibilidade `/devices`, migração legada, payload nativo, rejeições e falhas do provedor, logs seguros e fluxo TCP/WebSocket/Web Push.
- SDK Firebase real usado para validar objetos/serialização; envio foi mockado, sem rede ou credencial real.
- Três regressões reproduziram mensagens JSON acima do limite com aspas/barras/controles; passaram após corrigir o orçamento serializado.
- **66 testes Flutter aprovados**: 29 core, 30 push e 7 widgets; streams de refresh/foreground/toque, parser, permissão, registro/logout, deduplicação, diagnóstico, token debug e navegação.
- `flutter analyze`: sem problemas. **Total: 173 testes aprovados.**
- `flutter build apk --debug`: aprovado em 34,6 s com SDK Android 36. Mantido aviso conhecido do plugin Firebase/Kotlin para evolução futura; não houve erro de compilação.
- `apksigner verify`: assinatura v2 verificada; manifesto confirma package existente, API mínima 24, target 36 e versão 1.0.0+1.

APK local atualizado com configuração Firebase: `dist/mobile/manutencao-ti-debug.apk`, 184.227.593 bytes (~175,7 MiB). Cópia para download LAN em `app/static/manutencao-ti-debug.apk`; ambos ignorados pelo Git.

SHA-256 do APK:

```text
75FE0B662014CE66378635E8CCCF8EE1A87299AA9B08D2597DEE5A89E0C1E738
```

Não testados: entrega real pelo Google/APNs, notificações em aparelho físico/bloqueado e build iOS. O envio continua em thread após commit, sem fila persistente de reentrega. Force-stop e restrições do sistema operacional não equivalem a encerramento normal.

## Git

Branch continuada: **`codex/mobile-flutter`**. Base desta etapa: `763c9ad`. Os dois prompts markdown do usuário permanecem não rastreados e preservados.

Commits de código/testes desta etapa:

- `9533648` — `feat(push): complete native FCM infrastructure`
- `462ea0d` — `test(push): cover registration and payload limits`
- `81b2f5e` — `feat(mobile): finish native push lifecycle`

SHA do código validado e compilado: **`81b2f5e`**. O commit de documentação é posterior; SHA final consta na mensagem de entrega e em `git log -1`. Nenhum merge na main ou push remoto foi executado.
