A implementação mobile e as notificações Firebase/FCM estão funcionando no ambiente local.

Agora quero publicar o estado atual completo do projeto no GitHub para revisão.

Repositório:

https://github.com/SirManoTreta/manutencao

Antes de qualquer commit ou push, faça:

```bash
git status
git branch --show-current
git log --oneline -10
git remote -v
```

## 1. AUDITORIA DE SEGURANÇA

Antes de executar `git add`, revise cuidadosamente todos os arquivos novos e alterados.

NÃO envie ao GitHub nenhum segredo ou credencial.

Verifique especialmente:

```text
google-services.json
firebase-service-account*.json
service-account*.json
*.pem
*.key
.env
.env.*
data/*.db
*.sqlite
*.sqlite3
```

ATENÇÃO:

`google-services.json` do aplicativo Android não contém a service account administrativa, mas antes de versioná-lo analise a política adotada no projeto e confirme que não existe nele nenhuma credencial privada.

Service account JSON do Firebase JAMAIS deve ser enviado.

Procure também por:

- Firebase private keys;
- tokens;
- senhas;
- secrets;
- credenciais administrativas;
- arquivos de banco reais;
- arquivos de configuração locais contendo IPs ou dados sensíveis;
- APKs e builds gerados;
- caches Flutter/Dart;
- arquivos temporários.

Revise o `.gitignore` e atualize se necessário.

Se encontrar qualquer segredo já staged ou rastreado:

NÃO faça push.

Corrija primeiro e informe o que encontrou.

## 2. TESTES ANTES DO COMMIT

Execute os testes disponíveis para backend e Flutter.

Backend, quando aplicável:

```bash
pytest
```

ou o comando utilizado atualmente pelo projeto.

Flutter:

```bash
cd mobile
flutter analyze
flutter test
```

Se houver outros testes configurados, execute-os.

Também confira:

```bash
flutter pub get
```

Não altere funcionalidades apenas para esconder falhas.

Se algum teste falhar, investigue e informe a causa.

## 3. VERIFICAR IMPLEMENTAÇÃO FCM

Confirme que estão presentes no código, conforme a implementação atual:

- integração Firebase/FCM no Flutter;
- registro do dispositivo no backend;
- refresh do token;
- unregister/logout;
- recebimento em foreground;
- recebimento em background;
- abertura da aplicação pela notificação;
- navegação para o chamado correspondente;
- serviço de envio FCM no FastAPI;
- integração com criação de chamados;
- tratamento de falha do Firebase sem impedir a criação do chamado;
- documentação de configuração do Firebase.

Não refatore desnecessariamente nesta tarefa.

O objetivo agora é publicar exatamente o estado funcional atual.

## 4. BRANCH

NÃO faça merge na `main`.

Mantenha a branch de desenvolvimento atual caso ela já seja apropriada.

Exemplos possíveis:

```text
feature/mobile-flutter
feature/mobile-fcm
```

Se as implementações estiverem divididas em branches e a versão atualmente funcional estiver em apenas uma delas, preserve a branch funcional.

Informe exatamente qual branch será publicada.

## 5. STAGING

Depois da auditoria:

```bash
git add .
git status
```

Analise novamente TODOS os arquivos staged.

Confirme explicitamente que nenhum arquivo de segredo ou banco local está incluído.

## 6. COMMIT

Se houver várias alterações não commitadas relacionadas à implementação atual, faça commits organizados quando isso ainda for razoável.

Caso a implementação já esteja pronta como uma unidade coesa, um commit final de integração também é aceitável.

Sugestões de mensagens:

```text
feat(mobile): implement Flutter maintenance application
feat(push): integrate Firebase Cloud Messaging
feat(api): add mobile API and authentication
test: add mobile and API coverage
docs: document Flutter and Firebase setup
```

Não reescreva commits existentes sem necessidade.

## 7. PUSH

Publique a branch atual no GitHub:

```bash
git push -u origin NOME_DA_BRANCH
```

Não force push.

Não use:

```bash
git push --force
```

Não faça merge na `main`.

## 8. VERIFICAÇÃO PÓS-PUSH

Depois:

```bash
git status
git branch -vv
git log --oneline -10
git remote -v
```

Confirme que a branch local está sincronizada com `origin`.

## 9. RELATÓRIO FINAL

Entregue:

### Git
- branch publicada;
- SHA mais recente;
- commits enviados;
- link da branch no GitHub.

### Flutter
- páginas atualmente implementadas;
- funcionalidades funcionando;
- estado das notificações FCM.

### Backend
- endpoints adicionados;
- autenticação mobile;
- WebSocket/realtime;
- registro de dispositivos;
- integração FCM.

### Firebase
Informe quais arquivos/configurações ficaram propositalmente fora do Git e precisam existir localmente.

### Segurança
Confirme explicitamente que NÃO foram publicados:

- service account Firebase;
- private keys;
- `.env`;
- banco SQLite real;
- tokens;
- senhas;
- outros secrets.

### Testes
Informe os comandos executados e seus resultados.

Objetivo final:

Publicar no GitHub a versão atualmente funcional do aplicativo Flutter + backend mobile + Firebase/FCM, em uma branch de desenvolvimento, sem fazer merge na `main` e sem expor nenhum segredo.