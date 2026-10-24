# CLAUDE.md

Orientações para o Claude Code ao trabalhar neste projeto.

## Visão geral

Sistema web de **controle de manutenção de computadores de uma escola**, feito para rodar
na máquina local e ser acessado pelo celular na mesma rede (LAN). Stack: **FastAPI + SQLite +
Jinja2**, servido por **uvicorn**. Idioma do código e da UI: **português**.

São dois componentes:

1. **O site** (`app/`) — a TI cadastra máquinas, salas e periféricos, acompanha chamados em
   tempo real e exporta relatório em Excel.
2. **`Professor_auto.py`** — app de desktop (Tkinter) instalado nos PCs das salas. O professor
   clica num problema ("Sem internet", "Projetor sem imagem"…) e isso vira um chamado no site.
   Também manda um heartbeat periódico ("status_online") para indicar que o PC está ligado.

## Como rodar

> **Use Python 3.12.** O Jinja2 atual (3.1.x) quebra no **Python 3.14** com
> `TypeError: cannot use 'tuple' as a dict key` no cache de templates — toda página dá HTTP 500.
> Os `.bat` já chamam `py -3.12`. Rode com 3.12 até o Jinja2 ter suporte estável ao 3.14.

```bat
py -3.12 -m pip install -r requirements.txt
py -3.12 -m app.main    REM ou clique em run.bat
```

- Servidor em `http://127.0.0.1:8000` (PC) / `http://IP_DO_PC:8000` (celular na mesma rede).
- `clean8000.bat` libera a porta 8000 no Firewall do Windows.
- Primeiro acesso vai para `/setup` para criar o usuário admin (só funciona enquanto não
  existir nenhum usuário).
- O `__main__` sobe com `reload=True`. O banco `data/app.db` é criado automaticamente.

### Variáveis de ambiente úteis
- `PORT` (default 8000) — porta do site.
- `CHAMADOS_HOST` / `CHAMADOS_PORT` (default `0.0.0.0:5050`) — servidor TCP de chamados.
- `ONLINE_THRESHOLD_SECONDS` (default 15) — janela para considerar um PC "online".
- `AUTO_RESET_LOOP_SECONDS` (default 3600) — frequência do loop de auto-reset.
- `SSL_CERTFILE` / `SSL_KEYFILE` — para HTTPS (necessário para Web Push real no celular).

## Arquitetura / fluxo de chamados

```
Professor_auto.py (PC da sala)
   │  descobre o servidor na rede (scan /24, cache em chamados_server_cache.json)
   │  envia JSON via TCP :5050
   ▼
app/chamados_socket.py  (servidor TCP rodando em thread, iniciado no startup do FastAPI)
   │  grava Ticket + MachineHeartbeat no SQLite
   ├──► realtime.py ──► WebSocket /ws/tickets ──► atualiza /tickets sem reload
   └──► push.py ──────► Web Push (Service Worker; exige HTTPS para funcionar de fato)
   ▼
app/main.py  (FastAPI :8000) ──► templates Jinja2 + static (PWA)
   ▼
data/app.db (SQLite)
```

Detalhe importante de threading: o servidor TCP roda fora do event loop. Para notificar a UI
ele usa `realtime.broadcast_from_thread()`, que reentra no loop principal capturado no startup
via `set_main_loop()`. Não chame corrotinas async diretamente da thread TCP.

### Cliente compilado (`Professor_auto.py` → .exe)

Distribuído como `dist/Relatar Problema - TI.exe` (PyInstaller `--onefile --windowed`,
ícone `Professor_auto.ico`). Recompilar: `py -3.12 -m PyInstaller "Relatar Problema - TI.spec"`.
Pontos importantes do cliente:
- **Não pode ser fechado pelo professor**: o X e o Alt+F4 (`WM_DELETE_WINDOW` → `_on_close`)
  apenas **minimizam** (com aviso), para o heartbeat continuar. Fechar de verdade é só pela TI
  com **Ctrl+Shift+Q** (`_real_exit` → `os._exit(0)`). Há hotkey global (`keyboard`) + fallback
  Tkinter (`bind_all`) caso `keyboard` precise de admin. Task Manager ainda mata o processo.
- Atalho de emergência: **Ctrl+Shift+E** envia um chamado de "tela travada".
- Arquivos ao lado do .exe usam `_base_dir()` (frozen-aware): no .exe gravam na pasta do
  executável, não na pasta temporária do PyInstaller. É assim que `chamados_server_cache.json`
  persiste.

### Watchdog + início automático (deploy nos PCs)

A pasta `dist/` é o pacote de distribuição (copiar inteira para cada PC). Contém:
- `Relatar Problema - TI.exe` — a GUI do professor.
- `TI Watchdog.exe` — vigia (`watchdog.py`): a cada 5s, se a GUI não estiver rodando,
  reabre. Cobre o caso de matarem a GUI pelo Gerenciador de Tarefas.
- `instalar_inicializacao.bat` (+ `.ps1`) — registra a Tarefa Agendada **`TI Monitor Manutencao`**
  (`Register-ScheduledTask`, gatilho **AtLogOn** p/ grupo Usuários SID `S-1-5-32-545`, `RunLevel
  Highest`, `RestartCount 999`/1min, `ExecutionTimeLimit PT0S`). Auto-eleva (UAC).
- `desinstalar_inicializacao.bat` — remove a tarefa (`schtasks /Delete`).

Cadeia de resiliência: Agendador reinicia o **watchdog** se ele cair → watchdog reabre a **GUI**
se ela cair. **Início é no LOGON, não antes** — GUI Tkinter não roda em Sessão 0 (antes do login).

### Heartbeat de boot (online antes do login) + "login feito sim/não"

`TI Heartbeat.exe` (`heartbeat_boot.py`) é um cliente **headless** (sem janela) que roda como
**SYSTEM desde o boot** (tarefa `instalar_heartbeat_boot.bat` → trigger AtStartup, principal
`S-1-5-18`). Assim a máquina aparece online no painel já na **tela de login**. Ele detecta se há
usuário logado via `psutil.users()` e manda no heartbeat: `usuario` = nome do logado ou `None`.
- O servidor grava em `MachineHeartbeat.last_user`. `GET /api/online` expõe `login_active`
  (`bool(last_user)`) e `last_user`.
- O painel "Computadores online" (coluna **Login**, em `tickets_list.html` + `tickets_live.js`)
  mostra `👤 <usuário>` (logado) ou `🔒 sem login` (tela de login).
- Reusa o mesmo protocolo de descoberta (constantes duplicadas em `heartbeat_boot.py` — manter em
  sincronia com `chamados_socket.py`). Cache próprio: `chamados_server_cache_boot.json`.
- Coexiste com a GUI: ambos atualizam o mesmo heartbeat (chave `pc_name`), sem duplicar linhas.

### Descoberta de servidor (cliente ↔ servidor na mesma rede)

O `chamados_socket.py` sobe, além do TCP, um **respondedor de descoberta UDP** na mesma porta
(5050). Protocolo (constantes precisam bater entre `chamados_socket.py` e `Professor_auto.py`):
- **Broadcast UDP**: o cliente manda `MANUT_DISCOVER?` para o broadcast da rede; o servidor
  responde `MANUT_HERE ` + JSON (`{"service":"manutencao_chamados","tcp_port":5050}`). O cliente
  aprende o IP pelo endereço de origem do pacote.
- **Ping TCP com ACK**: o cliente manda `{"ping":1}`, dá `shutdown(SHUT_WR)` (o servidor lê até
  EOF) e lê de volta `{"service":"manutencao_chamados","ok":true}`. Serve para confirmar que é o
  servidor *certo* (e não outro processo na 5050).
- Ordem de descoberta no cliente: `CHAMADOS_SERVER` forçado → broadcast UDP → cache → varredura
  /24. O heartbeat re-descobre sozinho se a conexão cair (`_rediscover`).

## Mapa dos arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | Rotas, login/sessão, dashboard, CRUD de máquinas e usuários, relatório XLSM, timezone, auto-reset de vistorias/checkups. É o arquivo grande. |
| `app/models.py` | Modelos SQLAlchemy: `User`, `Machine`, `MachinePeripheral`, `MachineAudit`, `Ticket`, `MachineHeartbeat`, `PushSubscription`. |
| `app/crud.py` | Operações de banco e sincronização de periféricos por perfil. |
| `app/constants.py` | Perfis A/B/C e os periféricos de cada um. |
| `app/database.py` | Engine SQLite (`data/app.db`), `SessionLocal`, `get_db()`. |
| `app/chamados_socket.py` | Servidor TCP que recebe chamados/heartbeats do `Professor_auto.py`. |
| `app/realtime.py` | `ConnectionManager` de WebSocket + broadcast a partir de thread. |
| `app/push.py` | Chaves VAPID, subscriptions e envio de Web Push. |
| `app/reporting.py` | Geração do relatório `.xlsm` (openpyxl), agrupado por segmento de ensino. |
| `app/templates/` | Páginas Jinja2 (dashboard, máquinas, salas, tickets, usuários, login, setup). |
| `app/static/` | `app.js`, service worker (`sw.js`), clientes de push e realtime, CSS, manifest PWA. |
| `Professor_auto.py` | Cliente desktop Tkinter para as salas. |

## Conceitos do domínio

- **Perfis de máquina** (`constants.py`): `A` = Infantil + Fund I, `B` = Fund II + Médio,
  `C` = Administrativo. Cada perfil define um conjunto de periféricos diferente. Mudar o perfil
  de uma máquina re-sincroniza os periféricos relevantes (`upsert_peripherals_for_machine`).
- **Segmento** (`derive_segment` em `main.py`): tag derivada do nome da sala (INFANTIL, FUND1,
  FUND2, EM, ADMIN, OUTRO). É calculada em memória, nem sempre dá para filtrar via SQL.
- **room_status**: `OK` / `ATTENTION` / `URGENT`. O status de uma sala é o pior status entre
  suas máquinas.
- **Auto-reset**: `apply_auto_reset_checks()` desmarca `inspected`/`checkup_done` quando vencem
  (OK=7 dias, ATTENTION=2, URGENT=1). NÃO apaga as datas, só desmarca os checkboxes. Roda num
  loop de background e também a cada GET de `/machines` e do dashboard.

## Convenções

- **Timezone**: o banco guarda tudo em **UTC** (`datetime.utcnow`). A exibição converte para
  `America/Sao_Paulo` via os filtros Jinja `dt_br`, `time_br`, `date_br`. A API (`/api/tickets`)
  devolve ISO com offset UTC e o front converte. Mantenha esse padrão ao adicionar datas.
- **Migrações**: não há Alembic. Colunas novas em `machines`/`machine_peripherals` são
  adicionadas manualmente em `_migrate_sqlite()` (`main.py`) com `ALTER TABLE ... IF NOT EXISTS`
  manual via `PRAGMA table_info`. Ao adicionar um campo no modelo, adicione o `ALTER` aqui também.
- **Senhas**: PBKDF2-SHA256 com salt (`hash_password`/`verify_password` em `main.py`). Nunca
  guarde senha em texto puro (exceção atual conhecida: `hoptodesk_password`, ver abaixo).
- **Auth**: middleware `auth_guard` protege tudo exceto `/static`, `/login`, `/logout`, `/setup`.
  Sessão via cookie (`SessionMiddleware`, segredo em `data/session_secret.key`).

## Alarme sonoro de novos chamados (front-end)

`static/notify_live.js` toca `static/chamado-notificacao.mp3` em loop e mostra um **banner
vermelho piscando** (`#alarm-banner` no `base.html`) enquanto existir chamado com status `OPEN`.
Pontos:
- Navegadores **bloqueiam áudio** até o primeiro gesto do usuário. O primeiro
  `pointerdown`/`keydown` e o botão `#alarm-toggle-btn` (🔊) liberam ou testam a reprodução.
- Abrir `/tickets`, clicar na notificação ou trocar de página não silencia o áudio.
- O botão **Atender o Chamado** faz a transição atômica `OPEN -> IN_PROGRESS`, registra
  `assigned_by`/`assigned_at` e publica `ticket_taken` no WebSocket.
- Ao receber `ticket_taken` ou `ticket_closed`, todos os clientes consultam novamente os
  chamados `OPEN`; o som só para quando nenhum deles estiver aguardando.
- A tela separa os estados `OPEN`, `IN_PROGRESS` e `CLOSED`.

## Pegadinhas conhecidas / dívida técnica

- `hoptodesk_password` é salvo em **texto puro** no banco.
- O servidor TCP `:5050` aceita JSON **sem autenticação** de qualquer host da LAN. Aceitável
  para rede interna confiável; não exponha à internet.
- `data/` contém bancos extras (`app - Copia.db`, `appteste.db`) — não são usados; o banco real
  é `app.db`. Não confundir.
- Web Push do sistema (notificação com navegador fechado) só funciona sob **HTTPS**. Em HTTP por
  IP local funciona apenas o tempo-real via WebSocket com a página aberta.

## Banco de dados

- Arquivo: `data/app.db` (SQLite). Criado e migrado automaticamente no import de `main.py`.
- Arquivos sensíveis em `data/`: `session_secret.key`, `vapid_private.pem`, `vapid_public.txt`.
  Apagar as chaves VAPID obriga a reativar push em todos os dispositivos.

## Cliente Flutter / API mobile

- `mobile/` é cliente Flutter Android/iOS do mesmo backend e banco. Consulte `docs/mobile.md`.
- `app/api/v1/` mantém REST `/api/v1` separado das rotas HTML. Dependências Bearer validam
  sessão, expiração, usuário ativo e impressão do hash de senha. Cookies não autorizam a API.
- `app/security.py` contém as funções PBKDF2 originais, importadas também por `main.py`.
- `app/services/maintenance.py` contém regras compartilhadas de dashboard, segmentos,
  auto-reset, status de salas e MAC. Evite duplicá-las no cliente ou nas rotas.
- Atendimento usa `crud.take_ticket` / `crud.close_ticket`, com UPDATE condicional e broadcast
  após commit. Não substituir por leitura de status seguida de gravação sem condição.
- Tabelas `mobile_sessions` e `fcm_devices` são criadas via metadata. A coluna
  `tickets.resolution_note` é adicionada pela migração existente e separa nota de resolução
  de `diagnostics_json` (diagnóstico do PC).
- `/ws/v1/tickets` usa Authorization no handshake e revalida sessão durante conexão.
  `/ws/tickets` mantém cookie do site. Ambos recebem eventos do mesmo manager.
- `app/fcm.py` envia push nativo após commit do chamado TCP. Coexiste com `push.py`/VAPID.
  Firebase é opcional até configuração externa; chaves privadas nunca entram no Git/APK.
- DTOs em `app/schemas/` nunca expõem `password_hash` ou `hoptodesk_password`.
- `MANUTENCAO_DATA_DIR` muda diretório de banco/chaves para testes. Padrão permanece `data/`.
  Nunca importar `app.main` em teste antes de isolar essa variável: import migra o banco.
- Testes Python em `tests/`, dependências em `requirements-dev.txt`. Flutter: analyze/test.
