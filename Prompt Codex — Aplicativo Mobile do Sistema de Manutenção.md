Você irá trabalhar no repositório:

https://github.com/SirManoTreta/manutencao

Antes de modificar qualquer arquivo, analise cuidadosamente o projeto existente, sua arquitetura, documentação e funcionamento atual.

Leia obrigatoriamente:

- `README.md`
- `CLAUDE.md`
- `app/main.py`
- `app/models.py`
- `app/crud.py`
- `app/database.py`
- `app/constants.py`
- `app/chamados_socket.py`
- `app/realtime.py`
- `app/push.py`
- templates relevantes
- arquivos JavaScript relacionados a chamados, WebSocket e notificações
- demais arquivos que forem necessários para compreender corretamente o sistema

Não presuma como o sistema funciona sem antes verificar o código.

# CONTEXTO

Este projeto é um sistema REAL de manutenção de computadores utilizado em ambiente escolar.

Atualmente existem basicamente dois clientes:

1. Site web utilizado pela equipe de TI.
2. Programa Windows instalado nos computadores dos professores (`Professor_auto.py` e clientes auxiliares).

O backend é atualmente construído com:

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Jinja2
- WebSocket
- Web Push

Existe também um servidor TCP utilizado pelos computadores dos professores para registrar chamados e enviar heartbeats.

O objetivo agora é acrescentar um terceiro cliente ao sistema:

# APLICATIVO MOBILE EM FLUTTER / DART

O aplicativo mobile terá dois objetivos simultâneos:

1. Ser efetivamente utilizado pela equipe de TI no ambiente de trabalho.
2. Ser apresentado como trabalho acadêmico de desenvolvimento mobile na faculdade.

Portanto, o aplicativo não deve ser uma demonstração fictícia ou um projeto separado.

Ele deve ser uma extensão funcional do sistema real existente.

# PRINCÍPIO FUNDAMENTAL

O backend FastAPI deve continuar sendo o centro do sistema.

Arquitetura pretendida:

```text
PC DO PROFESSOR
Professor_auto.exe
        │
        │ TCP / heartbeat / chamados
        ▼
┌─────────────────────────────┐
│       BACKEND FASTAPI       │
│                             │
│ API                         │
│ Regras de negócio           │
│ WebSocket                   │
│ Autenticação                │
│ Notificações                │
└──────────────┬──────────────┘
               │
             SQLite
               │
       ┌───────┴─────────┐
       ▼                 ▼
   SITE WEB          APP FLUTTER
```

O aplicativo Flutter NÃO deve conversar diretamente com os computadores dos professores.

O fluxo deve ser:

```text
Professor_auto
      ↓
FastAPI
      ↓
Flutter
```

e:

```text
Flutter
      ↓
FastAPI
      ↓
Banco / sistema
```

O site web e o aplicativo mobile devem utilizar os mesmos dados e as mesmas regras de negócio.

Exemplo:

- chamado assumido pelo Flutter deve aparecer como assumido no site;
- máquina alterada pelo Flutter deve aparecer atualizada no site;
- chamado criado por um professor deve aparecer tanto no site quanto no aplicativo.

# NÃO QUEBRAR O SISTEMA EXISTENTE

Esta regra é extremamente importante.

O site atual está em uso.

NÃO substitua as rotas HTML existentes.

NÃO altere o comportamento atual do site sem necessidade.

NÃO converta rotas existentes para JSON.

NÃO remova Jinja2.

NÃO remova Web Push atual.

NÃO altere o protocolo utilizado pelo `Professor_auto.py` sem necessidade.

NÃO faça uma reestruturação destrutiva.

A versão web existente deve continuar funcionando.

A nova API deve coexistir com ela.

# API MOBILE

Crie uma API versionada, preferencialmente:

```text
/api/v1/
```

Organize a API em módulos separados.

Evite colocar todas as novas rotas dentro do já grande `app/main.py`.

Uma estrutura aceitável seria:

```text
app/
├── api/
│   └── v1/
│       ├── router.py
│       ├── auth.py
│       ├── dashboard.py
│       ├── machines.py
│       ├── rooms.py
│       ├── tickets.py
│       ├── online.py
│       └── users.py
│
├── schemas/
│   ├── auth.py
│   ├── dashboard.py
│   ├── machine.py
│   ├── room.py
│   ├── ticket.py
│   └── user.py
```

Adapte caso encontre uma arquitetura melhor depois de analisar o projeto.

Não duplique regras de negócio desnecessariamente.

Sempre que possível, reutilize funções e operações existentes.

# AUTENTICAÇÃO MOBILE

O site atualmente utiliza sessão/cookie.

Preserve isso para o site.

Para o aplicativo Flutter, implemente autenticação apropriada para API.

Preferencialmente:

```text
Bearer Token
```

Exemplo:

```text
POST /api/v1/auth/login
```

Entrada:

```json
{
  "username": "usuario",
  "password": "senha"
}
```

Resposta semelhante a:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "usuario",
    "is_admin": true
  }
}
```

As rotas mobile devem validar o token.

Preserve o mecanismo atual de hash de senha, a menos que exista motivo técnico claro para alterar.

Não armazene senha em texto puro.

# ENDPOINTS NECESSÁRIOS

Implemente API suficiente para que o aplicativo Flutter consiga executar as principais funções do site.

No mínimo:

## Autenticação

```text
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

## Dashboard

```text
GET /api/v1/dashboard
```

Reutilize a lógica existente de dashboard.

Deve retornar, quando disponível:

- total de máquinas;
- máquinas online;
- quantidade de salas;
- chamados abertos;
- chamados em atendimento;
- chamados fechados;
- vistorias pendentes;
- checkups pendentes;
- salas em atenção;
- salas urgentes;
- chamados recentes;
- máquinas recentemente alteradas;
- distribuições utilizadas pelo dashboard atual.

## Chamados

```text
GET  /api/v1/tickets
GET  /api/v1/tickets/{id}
POST /api/v1/tickets/{id}/take
POST /api/v1/tickets/{id}/close
```

Preserve a proteção já existente contra duas pessoas assumirem o mesmo chamado.

Não introduza race condition.

O endpoint de assumir chamado deve indicar adequadamente quando outro usuário já assumiu o chamado.

## Máquinas

```text
GET    /api/v1/machines
GET    /api/v1/machines/{id}
POST   /api/v1/machines
PUT    /api/v1/machines/{id}
DELETE /api/v1/machines/{id}
```

Quando apropriado, suporte os filtros já existentes no site:

- busca;
- perfil;
- segmento;
- status;
- vistoria;
- checkup.

Devem ser retornados os dados relevantes existentes no modelo atual, incluindo periféricos quando necessário.

## Salas

Crie endpoints adequados para:

- listar salas;
- obter status;
- listar máquinas da sala;
- alterar status da sala.

## Computadores online

Aproveite a funcionalidade atual de heartbeat.

Algo equivalente a:

```text
GET /api/v1/online
```

Deve permitir visualizar:

- nome do PC;
- máquina relacionada;
- sala;
- status online;
- idade do heartbeat;
- usuário logado;
- login ativo ou tela de login.

## Usuários

Se o usuário autenticado for administrador, disponibilize operações equivalentes às existentes no site.

Usuários não administradores não devem receber permissões administrativas.

# WEBSOCKET / TEMPO REAL

O aplicativo deverá receber atualizações de chamados em tempo real quando estiver aberto.

O projeto já possui:

```text
/ws/tickets
```

Analise a implementação existente.

O WebSocket atual usa autenticação baseada em sessão.

Crie uma estratégia segura para que o Flutter também consiga utilizar realtime autenticado.

Pode ser criada uma rota separada para clientes mobile, caso isso preserve melhor a compatibilidade.

Exemplo conceitual:

```text
/ws/v1/tickets
```

Não prejudique o WebSocket utilizado pelo site.

Quando um professor criar um chamado:

```text
Professor_auto.exe
        ↓
FastAPI
        ↓
Banco
        ↓
WebSocket
        ↓
Flutter aberto atualiza imediatamente
```

# PUSH NOTIFICATION — REQUISITO IMPORTANTE

Este é um requisito principal do aplicativo.

O celular deve receber uma notificação sempre que um novo chamado for criado, inclusive quando:

- Flutter estiver fechado;
- aplicativo estiver em background;
- celular estiver bloqueado.

O WebSocket sozinho NÃO resolve esse requisito.

Implemente uma solução de push notification adequada para Flutter.

Preferencialmente utilize:

```text
Firebase Cloud Messaging (FCM)
```

Não remova nem substitua o Web Push existente utilizado pela aplicação web.

As duas soluções devem coexistir:

```text
FastAPI
 ├── WebSocket → clientes abertos
 ├── Web Push → navegador/PWA
 └── FCM → Flutter
```

Crie no backend uma forma de registrar os tokens FCM dos dispositivos.

Não armazene chaves privadas do Firebase no Git.

Use variáveis de ambiente ou arquivo local ignorado.

Caso seja necessária configuração manual no Firebase Console, implemente todo o código possível e documente exatamente o que deverá ser configurado pelo desenvolvedor.

Quando um novo chamado for criado, a notificação deverá conter informações úteis, por exemplo:

```text
Novo chamado — TI

Sala: 7º Ano A
PC: PC-SALA07
Problema: Projetor sem imagem
```

Inclua no payload o ID do chamado.

Ao tocar na notificação, o Flutter deverá abrir diretamente o detalhe daquele chamado.

Isso deve funcionar como deep link interno do aplicativo.

Para o primeiro MVP, notificações obrigatórias:

```text
NOVO CHAMADO
```

Caso seja simples e coerente adicionar:

```text
CHAMADO ASSUMIDO
CHAMADO FINALIZADO
```

pode ser implementado, mas evite excesso de notificações.

# APLICATIVO FLUTTER

Crie o aplicativo em:

```text
mobile/
```

Não crie outro repositório.

O aplicativo deve utilizar Flutter e Dart.

O objetivo inicial é Android, mas não adote decisões desnecessariamente incompatíveis com iOS.

Organize o código adequadamente.

Uma estrutura possível:

```text
mobile/
├── lib/
│   ├── main.dart
│   ├── app.dart
│   │
│   ├── core/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── storage/
│   │   ├── notifications/
│   │   └── theme/
│   │
│   ├── models/
│   │
│   ├── services/
│   │
│   └── features/
│       ├── auth/
│       ├── dashboard/
│       ├── tickets/
│       ├── machines/
│       ├── rooms/
│       ├── online/
│       └── users/
│
├── android/
├── ios/
├── test/
└── pubspec.yaml
```

Não siga essa estrutura cegamente se houver uma alternativa mais adequada.

O principal é manter boa separação de responsabilidades.

# TELAS DO APLICATIVO

O aplicativo deve possuir mais de três páginas reais e funcionais.

Não crie páginas artificiais apenas para atender esse requisito.

O objetivo é que o aplicativo represente de fato a versão mobile do sistema.

Implemente inicialmente:

## 1. Login

- usuário;
- senha;
- autenticação no FastAPI;
- tratamento de erro;
- armazenamento seguro do token;
- logout.

## 2. Dashboard

Apresentar informações como:

- máquinas;
- PCs online;
- chamados abertos;
- chamados em atendimento;
- salas urgentes;
- salas em atenção;
- vistorias pendentes;
- checkups pendentes.

Interface pensada para celular.

## 3. Chamados

Separar de forma clara:

- abertos;
- em atendimento;
- finalizados.

Atualização em tempo real.

## 4. Detalhe do chamado

Mostrar:

- problema;
- PC;
- sala;
- usuário;
- horário;
- status;
- técnico responsável;
- diagnóstico, quando existir.

Ações:

```text
Assumir chamado
Finalizar chamado
```

conforme status e permissões.

## 5. Máquinas

Lista de máquinas com:

- pesquisa;
- filtros;
- status;
- sala;
- perfil.

## 6. Detalhe da máquina

Apresentar informações existentes no backend, incluindo quando disponíveis:

- nome;
- sala;
- IP;
- MAC;
- usuário;
- status;
- perfil;
- sistema operacional;
- CPU;
- RAM;
- GPU;
- armazenamento;
- Office;
- Kaspersky;
- USB;
- adaptadores;
- periféricos;
- vistoria;
- checkup;
- manutenção;
- informações de acesso remoto.

Não mostre senhas de forma insegura.

## 7. Cadastro / edição de máquina

Permitir realizar pelo app as principais operações disponíveis no site.

## 8. Salas

Listar salas e seus status:

```text
OK
ATTENTION
URGENT
```

Permitir visualizar máquinas da sala e alterar status quando o usuário tiver permissão.

## 9. Computadores online

Exibir o heartbeat recebido dos PCs.

Por exemplo:

```text
🟢 PC-SALA07
Sala: 7º Ano A
Usuário: professor.joao
Heartbeat: 3 segundos
```

ou:

```text
🟢 PC-SALA08
Sala: 8º Ano B
Tela de login
```

## 10. Usuários

Disponível somente para administrador.

Permitir operações administrativas equivalentes ao site quando fizer sentido.

# NAVEGAÇÃO

Utilize uma navegação adequada para mobile.

Uma possibilidade:

```text
┌───────────────────────────────┐
│                               │
│          Tela atual           │
│                               │
├───────────────────────────────┤
│ Início Chamados Máquinas Salas│
└───────────────────────────────┘
```

Outras opções podem ficar em uma área como:

```text
Mais
```

incluindo:

- Online;
- Vistorias;
- Checkups;
- Usuários;
- Perfil;
- Configurações;
- Logout.

Não sobrecarregue a barra inferior.

# UX MOBILE

Não copie diretamente HTML do site.

O Flutter deve possuir interface realmente pensada para celular.

Utilize:

- cards;
- listas;
- badges;
- chips de status;
- bottom navigation;
- pull-to-refresh quando fizer sentido;
- estados de loading;
- estados vazios;
- mensagens de erro;
- confirmação para ações destrutivas;
- Material Design moderno.

Diferencie visualmente:

```text
OK
ATTENTION
URGENT
```

e:

```text
OPEN
IN_PROGRESS
CLOSED
```

Mantenha a UI em português.

# CONFIGURAÇÃO DO SERVIDOR NO APP

O backend atualmente roda na rede local.

Não hardcode um IP específico do ambiente.

Implemente configuração da URL base do servidor.

Por exemplo:

```text
http://192.168.x.x:8000
```

Essa configuração pode ser persistida localmente.

Se for útil, uma tela/configuração de servidor pode ser criada.

O app deve lidar adequadamente com:

- servidor indisponível;
- timeout;
- perda de Wi-Fi;
- backend reiniciado;
- token inválido.

# SEGURANÇA

Considere especialmente:

- armazenamento seguro do token no dispositivo;
- autenticação nas APIs;
- autorização de administrador;
- não expor hashes de senha;
- não retornar informações sensíveis desnecessárias;
- não armazenar Firebase secret no Git;
- validar inputs;
- evitar SQL injection;
- manter as regras atuais do ORM;
- proteger WebSocket mobile.

O projeto possui dívida técnica conhecida:

```text
hoptodesk_password
```

é atualmente armazenada em texto puro.

NÃO faça uma grande migração fora do escopo sem necessidade.

Porém, não exponha essa senha indiscriminadamente na API mobile.

Se ela precisar ser exibida, proteja adequadamente e documente a decisão.

# MIGRAÇÕES

O projeto atualmente não utiliza Alembic.

Analise a estratégia existente antes de criar novas tabelas ou colunas.

Caso sejam necessárias tabelas para:

- tokens FCM;
- sessões/tokens mobile;
- outras funcionalidades;

implemente de maneira compatível com o projeto atual.

Evite quebrar bancos existentes utilizados em produção.

# TESTES

Adicione testes relevantes para a nova API.

No mínimo:

- login válido;
- login inválido;
- endpoint protegido sem token;
- `/auth/me`;
- dashboard;
- listar máquinas;
- obter máquina;
- listar chamados;
- obter chamado;
- assumir chamado;
- duas requisições tentando assumir o mesmo chamado;
- fechar chamado;
- regras administrativas;
- registro de token FCM.

Quando possível, teste regras sem depender de Firebase real.

Utilize mocks para serviços externos.

Para Flutter, implemente pelo menos testes básicos de:

- autenticação;
- parsing de modelos;
- navegação principal ou widgets críticos;
- gerenciamento de estado escolhido.

# DOCUMENTAÇÃO ACADÊMICA

Como o aplicativo também será utilizado em um trabalho de faculdade, mantenha documentação técnica compreensível.

Atualize o README ou crie documentação específica, por exemplo:

```text
docs/mobile.md
```

Explique:

- objetivo do aplicativo;
- problema resolvido;
- arquitetura;
- tecnologias;
- comunicação Flutter ↔ FastAPI;
- comunicação Professor_auto ↔ FastAPI;
- autenticação;
- REST API;
- WebSocket;
- push notification;
- banco;
- execução do Flutter;
- configuração do servidor;
- configuração do Firebase;
- como testar.

Inclua um diagrama simples da arquitetura.

Exemplo conceitual:

```text
Professor_auto.exe
       │
       │ TCP
       ▼
FastAPI
 │  │  │
 │  │  └── SQLite
 │  │
 │  └──── WebSocket / FCM
 │
 ├──────── Site Web
 │
 └──────── Flutter
```

A documentação deverá ser útil tanto para manutenção futura quanto para apresentação acadêmica.

# GIT

Não trabalhe diretamente de forma destrutiva na `main`.

Antes de começar, verifique:

```bash
git status
git branch
git log --oneline -5
```

Se o working tree estiver limpo, crie uma branch de desenvolvimento adequada.

Sugestão:

```text
feature/mobile-flutter
```

ou outra nomenclatura coerente.

Faça commits organizados por etapa.

Exemplos:

```text
feat(api): add mobile authentication
feat(api): add machines and tickets endpoints
feat(api): add mobile realtime support
feat(push): add FCM device registration
feat(mobile): bootstrap Flutter application
feat(mobile): add authentication flow
feat(mobile): add dashboard
feat(mobile): add tickets realtime
feat(mobile): add machines and rooms
test: add API and Flutter tests
docs: document mobile architecture
```

Não faça um commit gigantesco se puder separar logicamente.

NÃO faça merge na `main` automaticamente.

Deixe a branch pronta para revisão.

# ESCOPO E PRIORIDADE

Prioridade 1:

```text
não quebrar o sistema existente
```

Prioridade 2:

```text
API mobile bem estruturada
```

Prioridade 3:

```text
autenticação segura
```

Prioridade 4:

```text
Flutter funcional
```

Prioridade 5:

```text
chamados em tempo real
```

Prioridade 6:

```text
push notification para novos chamados
```

Prioridade 7:

```text
demais funcionalidades do site no mobile
```

Não sacrifique estabilidade para implementar rapidamente todas as telas.

Caso seja necessário escolher entre quantidade de funcionalidades e qualidade da arquitetura, faça primeiro a fundação corretamente.

# RESULTADO ESPERADO

Ao final, queremos ter:

```text
Sistema de Manutenção
│
├── Site Web existente
│
├── Professor_auto / Heartbeat
│
├── FastAPI
│   ├── HTML existente
│   ├── /api/v1
│   ├── autenticação mobile
│   ├── WebSocket
│   └── FCM
│
├── SQLite
│
└── mobile/
    └── Flutter/Dart
```

O aplicativo deverá ser capaz de realizar boa parte das mesmas tarefas do site e funcionar como ferramenta mobile da equipe de TI.

Principalmente:

```text
Login
Dashboard
Chamados
Notificações
Atendimento de chamado
Máquinas
Detalhes de máquina
Cadastro/edição
Salas
Computadores online
Vistorias/checkups
Administração quando autorizado
```

# ANTES DE IMPLEMENTAR

Primeiro faça uma análise do projeto atual e monte um plano de implementação.

Verifique:

- o que já pode ser reutilizado;
- o que precisa ser extraído;
- quais regras podem permanecer no backend atual;
- quais endpoints já existem;
- quais endpoints precisam ser criados;
- quais alterações no banco serão necessárias;
- como integrar FCM sem interferir no Web Push;
- como autenticar WebSocket mobile;
- como preservar compatibilidade com o sistema em produção.

Em seguida, execute a implementação.

Não crie uma segunda aplicação backend.

Não replique o banco.

Não transforme Flutter em um sistema independente.

Ele deve ser um CLIENTE MOBILE do sistema atual.

# RELATÓRIO FINAL

Ao terminar, entregue um relatório contendo:

## Arquitetura

Explique como ficou:

```text
Professor_auto
FastAPI
Site
Flutter
SQLite
WebSocket
FCM
```

## Backend

Liste:

- rotas criadas;
- schemas criados;
- autenticação;
- alterações no banco;
- realtime;
- push.

## Flutter

Liste:

- páginas implementadas;
- navegação;
- gerenciamento de estado utilizado;
- comunicação HTTP;
- WebSocket;
- notificações;
- armazenamento seguro;
- deep linking.

## Testes

Informe:

- testes executados;
- quantidade;
- resultados;
- eventuais limitações.

## Firebase

Se houver configuração manual pendente, explique passo a passo exatamente o que precisa ser feito.

Nunca inclua secrets no relatório.

## Git

Informe:

- branch;
- commits realizados;
- último SHA;
- arquivos principais modificados.

## Pendências

Liste claramente o que ainda não foi implementado ou necessita configuração externa.

Não declare algo como concluído se não tiver sido realmente testado.

O objetivo não é apenas produzir código.

O objetivo é construir uma versão mobile tecnicamente correta, útil no trabalho real e suficientemente bem estruturada e documentada para ser apresentada como projeto acadêmico de desenvolvimento mobile.