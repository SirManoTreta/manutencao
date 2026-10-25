Trabalhe no repositório:

https://github.com/SirManoTreta/manutencao

Objetivo desta tarefa:

Implementar a infraestrutura de push notification nativa para o aplicativo Flutter usando Firebase Cloud Messaging (FCM), integrada ao backend FastAPI existente, sem remover nem quebrar o Web Push já utilizado pelo site.

Antes de alterar qualquer arquivo, analise:

- `README.md`
- `CLAUDE.md`
- `app/main.py`
- `app/push.py`
- `app/models.py`
- `app/database.py`
- `app/chamados_socket.py`
- `app/realtime.py`
- `mobile/`, se já existir
- `mobile/pubspec.yaml`, se já existir
- configuração Android atual
- qualquer implementação mobile já criada

Preserve o funcionamento atual do sistema.

## REQUISITO PRINCIPAL

Quando um novo chamado for aberto por um computador de professor, o aplicativo Flutter deverá receber uma notificação nativa mesmo quando:

- estiver em background;
- estiver fechado;
- o celular estiver bloqueado.

A experiência esperada é semelhante a aplicativos como WhatsApp ou Teams:

```text
🔴 Manutenção

Novo chamado — Sala 7º Ano A
Projetor sem imagem
```

Ao tocar na notificação, o aplicativo deverá abrir diretamente o detalhe do chamado correspondente.

O ID do chamado deverá fazer parte do payload da mensagem.

## ARQUITETURA

Preserve a arquitetura existente:

```text
Professor_auto.exe
       ↓
FastAPI
       ↓
SQLite
       ├── Site Web
       ├── WebSocket
       ├── Web Push atual
       └── FCM → Flutter
```

NÃO substitua o Web Push atual.

FCM será usado especificamente para o aplicativo Flutter.

## 1. BACKEND FASTAPI

Adicione suporte ao Firebase Admin SDK.

Inclua a dependência necessária em `requirements.txt`.

Preferencialmente:

```text
firebase-admin
```

Não faça download nem gere credenciais automaticamente.

O backend deverá ler a credencial do Firebase a partir de configuração externa.

Preferência:

```text
GOOGLE_APPLICATION_CREDENTIALS
```

ou outra variável documentada de forma clara.

Exemplo esperado:

```bat
set GOOGLE_APPLICATION_CREDENTIALS=C:\Manutencao\secrets\firebase-service-account.json
```

NUNCA:

- coloque service account JSON no Git;
- coloque chave privada no código;
- coloque segredo real em README;
- comite credenciais.

Revise o `.gitignore` e garanta que arquivos de credenciais Firebase sejam ignorados, caso necessário.

## 2. MODELO DE DISPOSITIVO MOBILE

Crie estrutura persistente para registrar dispositivos móveis.

Pode ser uma tabela equivalente a:

```text
MobileDevice
```

Campos sugeridos:

```text
id
user_id
fcm_token
platform
device_name
is_active
created_at
updated_at
```

Adapte ao padrão do projeto.

O token FCM deve ser único quando apropriado.

Associe o dispositivo ao usuário autenticado.

Considere que:

- um usuário pode usar mais de um celular;
- o mesmo app pode gerar um novo token no futuro;
- tokens inválidos devem poder ser desativados/removidos.

Como o projeto não usa Alembic, implemente a alteração no banco de forma compatível com o mecanismo atual de criação/migração.

Não quebre bancos SQLite existentes.

## 3. ENDPOINTS MOBILE

Crie endpoints protegidos dentro de `/api/v1`.

No mínimo:

```text
POST /api/v1/push/register
POST /api/v1/push/unregister
```

O registro deverá receber algo semelhante a:

```json
{
  "fcm_token": "...",
  "platform": "android",
  "device_name": "Galaxy S..."
}
```

Nunca confie em `user_id` recebido diretamente do cliente.

Use o usuário autenticado pelo token da API.

O unregister deverá desativar/remover o token do usuário atual.

## 4. SERVIÇO DE PUSH

Crie uma camada separada para envio de notificações FCM.

Não coloque toda a lógica diretamente em `main.py`.

Exemplo de organização:

```text
app/
├── services/
│   └── mobile_push.py
```

ou equivalente.

O serviço deverá:

- inicializar Firebase Admin somente quando configurado;
- não derrubar a aplicação caso Firebase não esteja configurado;
- registrar logs claros;
- enviar notificações aos dispositivos ativos;
- tratar tokens inválidos;
- desativar/remover tokens rejeitados quando apropriado.

Não permita que uma falha no Firebase impeça a criação de um chamado.

A criação do chamado é mais importante que a notificação.

O comportamento esperado é:

```text
salvar chamado
↓
broadcast websocket
↓
web push existente
↓
tentar FCM
```

Se o FCM falhar:

```text
chamado continua salvo
site continua funcionando
```

## 5. EVENTO DE NOVO CHAMADO

Localize no código existente o ponto exato em que um novo `Ticket` é criado a partir do `Professor_auto`.

Integre o envio FCM nesse fluxo.

Não duplique criação de Ticket.

Não altere o protocolo TCP sem necessidade.

Quando surgir um novo chamado, envie uma notificação contendo pelo menos:

Título:

```text
Novo chamado — TI
```

Conteúdo semelhante a:

```text
Sala: 7º Ano A
PC: PC-SALA07
Problema: Projetor sem imagem
```

Se não houver sala associada, adapte de forma segura.

Payload de dados:

```json
{
  "type": "new_ticket",
  "ticket_id": "42"
}
```

O `ticket_id` deve ser enviado como string se o FCM exigir.

Para o primeiro MVP, novo chamado é obrigatório.

Notificações de:

```text
ticket_taken
ticket_closed
```

são opcionais.

Não implemente excesso de notificações sem necessidade.

## 6. FLUTTER

No aplicativo Flutter, adicione dependências oficiais necessárias.

Preferencialmente:

```text
firebase_core
firebase_messaging
```

Adicione também uma solução adequada de notificação local se for necessária para notificações em foreground.

Use bibliotecas oficiais ou amplamente mantidas.

Não use dependências obscuras.

Inicialize o Firebase usando a configuração FlutterFire.

Se `firebase_options.dart` ainda não existir, prepare o projeto para receber o resultado de:

```bash
flutterfire configure
```

Não invente os valores do projeto Firebase.

## 7. PERMISSÕES

Implemente solicitação de permissão de notificações corretamente.

Considere Android moderno, incluindo Android 13+.

O app deve:

- solicitar permissão quando apropriado;
- lidar com permissão negada;
- não travar se o usuário recusar;
- permitir tentar novamente futuramente.

## 8. REGISTRO DO TOKEN

Após login bem-sucedido:

```text
Flutter
↓
Firebase Messaging
↓
obter FCM token
↓
POST /api/v1/push/register
```

Associe o token ao usuário autenticado.

Também trate refresh de token.

Quando o Firebase gerar um novo token:

```text
onTokenRefresh
```

registre novamente no backend.

Ao realizar logout:

- execute `/api/v1/push/unregister`;
- remova a sessão/token local da aplicação.

## 9. APP EM FOREGROUND

Quando o Flutter estiver aberto, o sistema deve continuar usando WebSocket para atualização em tempo real.

Se uma mensagem FCM chegar em foreground, não gere comportamento duplicado confuso.

Pode mostrar uma notificação local ou banner apropriado, mas evite:

```text
WebSocket mostra chamado
+
FCM mostra popup duplicado
+
mais outro alerta
```

Defina uma estratégia coerente.

## 10. APP EM BACKGROUND / FECHADO

Configure corretamente os handlers necessários para:

- background;
- app terminado;
- abertura pelo toque na notificação.

Use:

```text
FirebaseMessaging.onMessageOpenedApp
```

e a estratégia correspondente para notificação que iniciou o aplicativo.

## 11. DEEP LINK INTERNO

Ao tocar na notificação com:

```json
{
  "type": "new_ticket",
  "ticket_id": "42"
}
```

o aplicativo deverá navegar para:

```text
Detalhe do chamado #42
```

Se o usuário ainda não estiver autenticado:

```text
notificação
↓
abre app
↓
login
↓
após autenticar
↓
detalhe do chamado
```

Se isso puder ser implementado sem complexidade excessiva, faça corretamente.

Caso contrário, documente a limitação.

## 12. CONFIGURAÇÃO FIREBASE

NÃO tente criar um projeto Firebase automaticamente.

Prepare todo o código possível e crie documentação clara para a etapa manual.

Crie ou atualize:

```text
docs/mobile_push_firebase.md
```

Explique passo a passo:

### Firebase Console

1. Criar projeto Firebase.
2. Adicionar aplicativo Android.
3. Qual applicationId/package name deve ser informado.
4. Onde obter/configurar `google-services.json`, caso necessário.
5. Como executar:

```bash
firebase login
dart pub global activate flutterfire_cli
flutterfire configure
```

6. Como gerar service account para o backend.
7. Onde guardar o JSON.
8. Como configurar `GOOGLE_APPLICATION_CREDENTIALS`.
9. Como testar com mensagem de teste pelo Firebase Console.

Não inclua nenhum segredo real.

## 13. APPLICATION ID

Descubra o applicationId atual do Flutter, se o app já existir.

Não altere o package name sem necessidade.

Caso o aplicativo ainda não tenha um identificador definitivo, utilize um nome profissional e estável.

Por exemplo:

```text
br.com.liceuvivere.manutencao
```

ou outro que seja tecnicamente coerente com o projeto.

Antes de mudar um applicationId já existente, avalie impacto.

Documente exatamente qual package name deve ser cadastrado no Firebase Console.

## 14. TESTES

Implemente testes de backend para:

- registrar token FCM;
- atualizar token existente;
- unregister;
- bloquear acesso sem autenticação;
- garantir associação com usuário correto;
- disparo de notificação em novo chamado;
- falha do Firebase não impedir criação do chamado;
- token inválido ser tratado adequadamente.

Mocke o Firebase Admin SDK.

Os testes NÃO devem enviar push real.

Para Flutter, teste quando viável:

- parsing do payload;
- roteamento por `ticket_id`;
- serviço de registro de token;
- comportamento do logout.

## 15. TESTE MANUAL PREPARADO

Ao terminar, deixe uma sequência clara de validação manual:

```text
1. configurar Firebase
2. executar flutterfire configure
3. colocar service account no servidor
4. iniciar FastAPI
5. instalar app Android
6. fazer login
7. conceder notificações
8. verificar registro FCM no backend
9. colocar app em background
10. enviar mensagem de teste
11. abrir chamado pelo Professor_auto
12. receber push
13. tocar no push
14. abrir detalhe do chamado
```

## 16. SEGURANÇA

Garanta que não sejam versionados:

```text
firebase-service-account.json
service-account*.json
*.pem
*.key
.env
```

A configuração Flutter pública do Firebase não deve ser confundida com a service account privada.

Não exponha credenciais administrativas no app.

## 17. NÃO FAZER

NÃO:

- substitua WebSocket por FCM;
- substitua Web Push atual;
- altere `Professor_auto.py` sem necessidade;
- crie outro backend;
- crie outro banco;
- coloque service account no Flutter;
- coloque secrets no Git;
- faça merge automático na `main`.

Trabalhe em branch apropriada.

## 18. GIT

Antes:

```bash
git status
git branch
git log --oneline -5
```

Se estiver limpo, trabalhe em uma branch como:

```text
feature/mobile-fcm
```

Se já houver branch ativa do desenvolvimento mobile, avalie se faz mais sentido continuar nela.

Faça commits lógicos.

Exemplo:

```text
feat(push): add mobile device registration
feat(push): integrate Firebase Cloud Messaging
feat(mobile): add FCM registration and handlers
feat(mobile): open ticket from notification
test(push): add FCM integration tests
docs: add Firebase setup guide
```

Não faça merge automático na `main`.

## 19. RESULTADO FINAL

Ao terminar, apresente relatório contendo:

### Backend

- arquivos criados;
- arquivos modificados;
- modelo/tabela criada;
- endpoints;
- serviço FCM;
- ponto onde novo chamado dispara push.

### Flutter

- dependências adicionadas;
- handlers configurados;
- registro/refresh do token;
- permissões;
- foreground;
- background;
- terminated;
- abertura por notificação;
- deep link do chamado.

### Firebase

Informe claramente o que ainda depende de configuração manual minha.

Especialmente:

```text
package/applicationId
projeto Firebase
flutterfire configure
service account
GOOGLE_APPLICATION_CREDENTIALS
```

### Testes

Informe:

- testes executados;
- resultados;
- o que não pôde ser testado sem credenciais reais.

### Git

Informe:

- branch;
- commits;
- SHA final.

### IMPORTANTE

Não diga que notificações push reais estão funcionando se você não teve acesso a:

- projeto Firebase configurado;
- app Android registrado;
- service account válida;
- dispositivo Android real.

Nesse caso, diga que:

```text
a implementação está pronta e aguarda configuração externa do Firebase
```

e informe exatamente quais passos manuais faltam.

Objetivo final:

Deixar backend e Flutter prontos para que, após eu configurar o Firebase, um chamado criado pelo `Professor_auto` gere uma notificação nativa no celular mesmo com o aplicativo em segundo plano ou fechado, e que tocar na notificação abra o detalhe daquele chamado.