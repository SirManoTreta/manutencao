# Site de Controle de Manutenção (LAN)

## Objetivo
Sistema de manutenção e chamados de computadores, com backend Python/FastAPI.
Site hospedado na sua máquina, acessível pelo celular na mesma rede, com armazenamento local (SQLite).

## Requisitos
- Python 3.12 instalado (a versão utilizada pelo `run.bat`).

## Instalação
1) Abra um terminal na pasta do projeto
2) (Opcional) Ambiente virtual:
   - Windows:
     - `python -m venv .venv`
     - `.venv\Scripts\activate`
3) Instale dependências:
   - `python -m pip install -r requirements.txt`

## Executar
- `python -m app.main`
ou
- clique em `run.bat`

Servidor:
- `http://127.0.0.1:8000` (no PC)
- `http://IP_DO_PC:8000` (no celular na mesma rede)

## Acessar pelo celular
1) Descubra o IP do PC:
   - Windows: `ipconfig` → "Endereço IPv4"
2) No celular (mesmo Wi-Fi), acesse:
   - `http://IP_DO_PC:8000`

## Firewall (Windows)
Se o celular não acessar, libere a porta 8000 no Firewall do Windows para rede privada.

## Banco de dados
- Arquivo: `data/app.db` (criado automaticamente)
- Bancos, backups, chaves de sessão/VAPID, arquivos `.env` e caches são locais e não
  são versionados. Após clonar, a aplicação cria o banco e as chaves necessários;
  acesse `/setup` para criar o primeiro administrador.

## Clientes Windows

Os fontes dos clientes e os scripts de instalação em `dist/` são versionados.
Os executáveis gerados não são enviados ao Git. Para recriá-los, instale o
PyInstaller no ambiente de desenvolvimento e execute na raiz do projeto:

```bat
py -3.12 -m pip install pyinstaller
py -3.12 -m PyInstaller "Relatar Problema - TI.spec"
py -3.12 -m PyInstaller "TI Watchdog.spec"
py -3.12 -m PyInstaller "TI Heartbeat.spec"
```

A versão mobile em Flutter/Dart será desenvolvida posteriormente neste mesmo projeto.


## Notificações (Web Push)

- A tela atualiza em tempo real via WebSocket com a página aberta.
- Um novo chamado toca `app/static/chamado-notificacao.mp3` em loop em todas as telas
  autenticadas. O som para quando alguém clica em **Atender o Chamado** e não há outro chamado
  aguardando atendimento.
- Navegadores podem exigir um primeiro clique na página para liberar a reprodução de áudio.
- Para receber notificação do sistema (inclusive com o navegador fechado), o navegador exige **HTTPS**.

### Como ativar HTTPS local (Windows)
1) Instale o mkcert (recomendado) e gere um certificado para o IP ou domínio local.
2) Defina as variáveis de ambiente e rode o servidor.

Exemplo:

```bat
set SSL_CERTFILE=C:\caminho\cert.pem
set SSL_KEYFILE=C:\caminho\key.pem
python -m app.main
```

Depois acesse por `https://...` e, no site, clique no botão 🔔 para registrar o dispositivo.

As chaves VAPID são geradas automaticamente em `data/vapid_private.pem` e `data/vapid_public.txt`.
Se você apagar essas chaves, será necessário reativar o push nos dispositivos.
