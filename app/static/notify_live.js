// Notificações em tempo real + alarme persistente de chamados aguardando.
//
// O áudio só é interrompido quando não existe mais nenhum chamado OPEN.
// A transição para IN_PROGRESS acontece pelo botão "Atender o Chamado".

(function () {
  if (typeof window === "undefined") return;

  const STORAGE_KEY = "newTicketsCount";
  const AUDIO_URL = "/static/chamado-notificacao.mp3";

  let openTicketsCount = 0;
  let alarmRequested = false;
  let lastAlertText = "Há chamado aguardando atendimento.";

  const alarmAudio = new Audio(AUDIO_URL);
  alarmAudio.loop = true;
  alarmAudio.preload = "auto";

  function setCount(count) {
    openTicketsCount = Math.max(0, Number(count) || 0);
    localStorage.setItem(STORAGE_KEY, String(openTicketsCount));
    updateBadge();
    updatePageBanner();
  }

  function updateBadge() {
    const badge = document.getElementById("tickets-badge");
    if (!badge) return;
    if (openTicketsCount > 0) {
      badge.textContent = String(openTicketsCount);
      badge.classList.remove("d-none");
    } else {
      badge.classList.add("d-none");
    }
  }

  function updatePageBanner() {
    const banner = document.getElementById("new-ticket-banner");
    if (!banner) return;
    banner.classList.toggle("d-none", openTicketsCount === 0);
  }

  function updateAlarmButton() {
    const button = document.getElementById("alarm-toggle-btn");
    if (!button) return;
    button.textContent = alarmAudio.paused && alarmRequested ? "🔈" : "🔊";
    button.classList.toggle("alarm-on", !alarmAudio.paused);
    button.title = alarmRequested
      ? "O navegador aguarda um clique para liberar o som"
      : "Ativar ou testar o som dos chamados";
  }

  function showAlarmBanner(text) {
    const banner = document.getElementById("alarm-banner");
    if (!banner) return;
    const message = banner.querySelector(".alarm-banner__msg");
    if (message) message.textContent = text;
    banner.classList.remove("d-none");
  }

  function hideAlarmBanner() {
    const banner = document.getElementById("alarm-banner");
    if (banner) banner.classList.add("d-none");
  }

  async function playAlarm() {
    if (!alarmRequested || openTicketsCount === 0) return;
    try {
      await alarmAudio.play();
    } catch (_) {
      // Autoplay pode ser bloqueado até o primeiro gesto do usuário.
    }
    updateAlarmButton();
  }

  function startAlarm(text) {
    alarmRequested = true;
    if (text) lastAlertText = text;
    showAlarmBanner(lastAlertText);
    playAlarm();
  }

  function stopAlarm() {
    alarmRequested = false;
    alarmAudio.pause();
    alarmAudio.currentTime = 0;
    hideAlarmBanner();
    updateAlarmButton();
  }

  async function syncOpenTickets() {
    try {
      const response = await fetch("/api/tickets?status=OPEN", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      const tickets = Array.isArray(data.tickets) ? data.tickets : [];
      setCount(tickets.length);

      if (tickets.length > 0) {
        const newest = tickets[0];
        const text = tickets.length === 1
          ? `${newest.pc_name || "PC"}: ${newest.problem || "Novo chamado"}`
          : `${tickets.length} chamados aguardando atendimento`;
        startAlarm(text);
      } else {
        stopAlarm();
      }
    } catch (_) {
      // A próxima mensagem ou reconexão sincroniza novamente.
    }
  }

  function showToast(message, linkUrl) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const element = document.createElement("div");
    element.className = "toast-mini";
    element.innerHTML = `
      <div class="toast-mini__title">Chamado</div>
      <div class="toast-mini__body"></div>
    `;
    element.querySelector(".toast-mini__body").textContent = message;

    if (linkUrl) {
      const link = document.createElement("a");
      link.href = linkUrl;
      link.textContent = "Abrir";
      link.className = "toast-mini__link";
      element.appendChild(link);
    }

    container.appendChild(element);
    window.setTimeout(() => {
      element.classList.add("toast-mini--hide");
      window.setTimeout(() => element.remove(), 250);
    }, 6000);
  }

  function onTicketCreated(payload) {
    const pc = payload.pc_name || "PC";
    const problem = payload.problem || "Novo chamado";
    const text = `${pc}: ${problem}`;

    setCount(openTicketsCount + 1);
    showToast(text, "/tickets");
    startAlarm(text);

    try {
      if (navigator.vibrate) navigator.vibrate([200, 100, 200, 100, 200]);
    } catch (_) {}

    try {
      if (window.Notification && Notification.permission === "granted") {
        const notification = new Notification("Novo chamado", { body: text });
        notification.onclick = () => {
          window.focus();
          window.location.href = "/tickets";
        };
      }
    } catch (_) {}
  }

  function connectWS() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let ws;

    function open() {
      ws = new WebSocket(`${proto}://${location.host}/ws/tickets`);

      ws.onopen = () => syncOpenTickets();
      ws.onmessage = (event) => {
        let message;
        try {
          message = JSON.parse(event.data);
        } catch (_) {
          return;
        }
        if (!message || !message.type) return;

        if (message.type === "ticket_created") onTicketCreated(message);
        if (message.type === "ticket_taken" || message.type === "ticket_closed") {
          syncOpenTickets();
        }
      };
      ws.onclose = () => window.setTimeout(open, 1500);
      ws.onerror = () => {
        try {
          ws.close();
        } catch (_) {}
      };
    }

    open();
  }

  function testSound() {
    if (openTicketsCount > 0) {
      alarmRequested = true;
      playAlarm();
      return;
    }

    const testAudio = new Audio(AUDIO_URL);
    testAudio.play().catch(() => {});
    window.setTimeout(() => {
      testAudio.pause();
      testAudio.currentTime = 0;
    }, 4000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const storedCount = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
    setCount(Number.isFinite(storedCount) ? storedCount : 0);
    updateAlarmButton();

    // Se o autoplay foi bloqueado, o primeiro gesto libera e retoma o alarme.
    const unlockAudio = () => {
      if (alarmRequested) playAlarm();
    };
    window.addEventListener("pointerdown", unlockAudio);
    window.addEventListener("keydown", unlockAudio);

    const alarmButton = document.getElementById("alarm-toggle-btn");
    if (alarmButton) {
      alarmButton.addEventListener("click", (event) => {
        event.preventDefault();
        testSound();
      });
    }

    window.addEventListener("storage", (event) => {
      if (event.key !== STORAGE_KEY) return;
      const count = parseInt(event.newValue || "0", 10);
      setCount(Number.isFinite(count) ? count : 0);
    });

    syncOpenTickets();
    connectWS();
  });
})();
