Você deverá preparar e publicar este projeto no GitHub.

O objetivo é colocar a versão atual do sistema de manutenção/chamados sob controle de versão para que posteriormente seja desenvolvida, dentro do mesmo projeto, uma versão mobile utilizando Flutter e Dart.

IMPORTANTE:
- Não altere o funcionamento atual da aplicação.
- Não faça refatorações desnecessárias.
- Não remova funcionalidades.
- Neste momento, sua tarefa é principalmente preparar o projeto para Git/GitHub e realizar a publicação com segurança.
- Antes de qualquer `git add`, faça uma auditoria para garantir que arquivos sensíveis, bancos de dados, caches e arquivos locais não sejam enviados ao GitHub.

## 1. Analise o projeto atual

Primeiro, identifique a raiz real do projeto.

A estrutura esperada contém aproximadamente:

```text
requirements.txt
run.bat
README.md
Professor_auto.py
app/
data/
```

Dentro de `app/` existem arquivos Python, templates HTML, arquivos estáticos e componentes do backend.

Não presuma que a estrutura é exatamente essa: examine o diretório real antes de executar qualquer operação Git.

## 2. Segurança antes do Git

Faça uma busca por arquivos que não devem ser publicados.

Dê atenção especial a:

```text
*.db
*.sqlite
*.sqlite3

*.key
*.pem
*.p12
*.pfx

.env
.env.*

__pycache__/
*.pyc

chamados_server_cache.json
```

Já sabemos que versões anteriores deste projeto podem conter arquivos semelhantes a:

```text
data/app.db
data/appteste.db
data/session_secret.key
data/vapid_private.pem
chamados_server_cache.json
```

Esses arquivos NÃO devem entrar no Git.

Também verifique se existem:

- senhas;
- tokens;
- secrets;
- chaves privadas;
- credenciais;
- dados pessoais;
- IPs ou configurações estritamente locais que não deveriam ser públicos;
- bancos SQLite reais;
- caches;
- arquivos temporários;
- ambientes virtuais Python.

Se encontrar algum segredo hardcoded dentro do código-fonte, NÃO publique imediatamente.

Nesse caso:
1. informe exatamente onde está;
2. remova o segredo do versionamento da forma apropriada, preferencialmente usando variável de ambiente;
3. preserve o funcionamento do programa;
4. crie `.env.example` se fizer sentido;
5. nunca coloque o valor real do segredo no `.env.example`.

Se o segredo estiver apenas em um arquivo local ignorável, simplesmente garanta que ele fique no `.gitignore`.

## 3. Criar ou revisar `.gitignore`

Crie um `.gitignore` apropriado para Python, FastAPI e para a futura aplicação Flutter.

Ele deve contemplar pelo menos:

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class

# Virtual environments
.venv/
venv/
env/

# Databases and local runtime data
data/*
!data/.gitkeep

*.db
*.sqlite
*.sqlite3

# Secrets
*.key
*.pem
*.p12
*.pfx

.env
.env.*
!.env.example

# Application local cache
chamados_server_cache.json

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Flutter / Dart
.dart_tool/
.flutter-plugins
.flutter-plugins-dependencies
.packages
.pub-cache/
.pub/
build/

# Android
android/.gradle/
android/local.properties

# iOS
ios/Pods/
ios/.symlinks/
```

Adapte caso a estrutura real do projeto exija.

Se `data/` precisar existir para que a aplicação funcione corretamente após um clone, crie:

```text
data/.gitkeep
```

mas não envie o banco de dados real.

## 4. Revise o README

Verifique o README existente.

Não reescreva documentação que já esteja correta apenas por estilo.

Garanta pelo menos que seja possível entender:

- o que é o projeto;
- que se trata de um sistema de manutenção/chamados;
- que o backend atual utiliza Python;
- como instalar dependências;
- como iniciar o projeto.

A execução atual utiliza, se ainda for válido:

```bash
python -m app.main
```

As dependências são instaladas por:

```bash
python -m pip install -r requirements.txt
```

Se essas informações já estiverem documentadas corretamente, preserve-as.

Não documente credenciais reais.

## 5. Verifique o estado do Git

Antes de inicializar um novo repositório, execute algo equivalente a:

```bash
git status
```

ou verifique se `.git/` já existe.

### Se já existir um repositório Git

Não execute `git init` cegamente.

Primeiro analise:

```bash
git status
git branch
git remote -v
git log --oneline -10
```

Preserve histórico existente.

### Se ainda não existir

Inicialize:

```bash
git init
git branch -M main
```

## 6. Faça uma verificação ANTES do primeiro commit

Execute:

```bash
git status
```

Verifique cuidadosamente o que será rastreado.

NÃO prossiga se aparecerem arquivos como:

```text
data/app.db
data/*.db
*.key
*.pem
.env
chamados_server_cache.json
__pycache__/
*.pyc
```

Faça também uma verificação adicional com:

```bash
git check-ignore -v <arquivo>
```

quando necessário.

Se algum arquivo sensível já estiver staged, retire-o do stage antes do commit.

Se algum arquivo sensível já tiver entrado em commits locais ainda não publicados, remova-o corretamente do histórico antes do push.

## 7. Teste básico antes da publicação

Sem alterar dados reais e sem causar efeitos colaterais, faça verificações básicas de sanidade.

Por exemplo:

```bash
python -m compileall app
```

Caso exista uma suíte de testes, execute-a.

Não bloqueie a publicação apenas porque não existe suíte automatizada.

Se for seguro iniciar o backend localmente, você pode fazer um smoke test, mas não deixe processos desnecessários rodando ao terminar.

Não modifique o projeto apenas para fazer os testes passarem se isso fugir do escopo desta tarefa.

## 8. Primeiro commit

Depois de confirmar que o projeto está seguro para publicação:

```bash
git add .
git status
```

Confira novamente o conteúdo staged.

Então crie o commit inicial.

Sugestão:

```bash
git commit -m "feat: versão inicial do sistema de manutenção"
```

Se já existir histórico Git, preserve-o e faça apenas o commit necessário para as alterações desta preparação.

## 9. Publicação no GitHub

Use o GitHub CLI (`gh`) se estiver instalado e autenticado.

Verifique:

```bash
gh auth status
```

O repositório deve ser criado como:

```text
manutencao
```

Preferencialmente:

```text
PRIVATE
```

Não crie como público sem autorização explícita.

Se o nome `manutencao` já estiver ocupado na conta, utilize:

```text
sistema-manutencao
```

ou informe o conflito.

Se puder criar automaticamente:

```bash
gh repo create manutencao --private --source=. --remote=origin --push
```

Adapte o comando caso já exista `origin`.

Se o repositório remoto já existir, NÃO crie outro.

Confira:

```bash
git remote -v
```

e publique:

```bash
git push -u origin main
```

## 10. Não faça ainda

NÃO crie o aplicativo Flutter nesta tarefa.

NÃO reorganize todo o backend.

NÃO migre SQLite para outro banco.

NÃO altere arquitetura.

NÃO transforme endpoints.

NÃO altere interfaces HTML.

NÃO remova funcionalidades existentes.

A estrutura futura provavelmente será algo semelhante a:

```text
manutencao/
├── app/
│   └── backend Python/FastAPI atual
│
├── mobile/
│   └── futuramente Flutter/Dart
│
├── data/
├── requirements.txt
├── README.md
└── ...
```

Mas a pasta `mobile/` será criada posteriormente, quando começarmos o desenvolvimento Flutter.

## 11. Verificação pós-push

Depois da publicação, confirme:

```bash
git status
git remote -v
git log --oneline -5
```

O resultado esperado deve ser algo semelhante a:

```text
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

Verifique também que os arquivos sensíveis continuam fora do repositório.

## 12. Relatório final

Ao terminar, apresente um relatório curto contendo:

### GitHub
- nome do repositório;
- URL do repositório;
- visibilidade;
- branch principal.

### Git
- hash do último commit;
- mensagem do commit;
- remote configurado.

### Segurança
Informe quais tipos de arquivo foram adicionados ao `.gitignore`.

Confirme explicitamente se ficaram fora do Git:

```text
bancos SQLite
session_secret
chaves VAPID
arquivos .env
chaves privadas
caches Python
chamados_server_cache.json
```

### Alterações
Liste os arquivos que você modificou para preparar a publicação.

### Validação
Informe os testes/verificações realizados e seus resultados.

Se alguma etapa não puder ser concluída por falta de autenticação do GitHub, não invente credenciais nem tente contornar autenticação.

Pare nesse ponto e me informe exatamente o comando que preciso executar para autenticar ou concluir a publicação.

Objetivo final:

Ter o sistema atual preservado e funcionando, versionado com segurança em um repositório GitHub privado, na branch `main`, pronto para iniciarmos posteriormente o desenvolvimento da versão mobile em Flutter/Dart.