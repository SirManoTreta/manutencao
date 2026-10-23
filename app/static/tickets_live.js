// Atualização em tempo real da tela /tickets sem recarregar.

(function () {
  function qs(selector) {
    return document.querySelector(selector);
  }

  function fmtDate(iso) {
    if (!iso) return "-";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "-";
    const dd = String(date.getDate()).padStart(2, "0");
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    const hh = String(date.getHours()).padStart(2, "0");
    const mi = String(date.getMinutes()).padStart(2, "0");
    return `${dd}/${mm} ${hh}:${mi}`;
  }

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function fetchJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }

  function renderTickets(tickets) {
    const body = qs("#tickets-body");
    if (!body) return;

    if (!tickets || tickets.length === 0) {
      body.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">Nenhum chamado encontrado.</td></tr>`;
      return;
    }

    body.innerHTML = tickets.map((ticket) => {
      const pc = esc(ticket.pc_name);
      const room = ticket.machine ? esc(ticket.machine.room_name) : "-";
      const computerCell = ticket.machine
        ? `<a href="/machines/${ticket.machine.id}">${pc}</a>`
        : `${pc} <span class="badge text-bg-warning ms-1">não cadastrado</span>`;

      const diagnostics = ticket.diagnostics_json
        ? `<details class="small text-muted"><summary>diagnóstico</summary><pre class="m-0">${esc(ticket.diagnostics_json)}</pre></details>`
        : "";

      const assignedInfo = `${esc(ticket.assigned_by || "")}${
        ticket.assigned_at ? " · " + fmtDate(ticket.assigned_at) : ""
      }`;
      const closedInfo = `${esc(ticket.closed_by || "")}${
        ticket.closed_at ? " · " + fmtDate(ticket.closed_at) : ""
      }`;

      let statusBadge;
      let actionButton = "";
      if (ticket.status === "OPEN") {
        statusBadge = `<span class="badge text-bg-danger">AGUARDANDO</span>`;
        actionButton = `
          <form method="post" action="/tickets/${ticket.id}/take" class="m-0">
            <button class="btn btn-sm btn-primary" type="submit">Atender o Chamado</button>
          </form>`;
      } else if (ticket.status === "IN_PROGRESS") {
        statusBadge = `<span class="badge text-bg-info">EM ATENDIMENTO</span>
          <div class="small text-muted">${assignedInfo}</div>`;
        actionButton = `
          <form method="post" action="/tickets/${ticket.id}/close" class="m-0">
            <button class="btn btn-sm btn-outline-success" type="submit">Fechar</button>
          </form>`;
      } else {
        statusBadge = `<span class="badge text-bg-success">FECHADO</span>
          <div class="small text-muted">${closedInfo}</div>`;
      }

      return `
        <tr>
          <td class="text-nowrap">${fmtDate(ticket.created_at)}</td>
          <td class="text-nowrap">${computerCell}</td>
          <td class="text-nowrap">${room}</td>
          <td style="max-width: 360px;">
            <div class="fw-semibold">${esc(ticket.problem)}</div>
            ${diagnostics}
          </td>
          <td class="text-nowrap">${esc(ticket.reported_user || "-")}</td>
          <td class="text-nowrap">${statusBadge}</td>
          <td class="text-nowrap text-end">${actionButton}</td>
        </tr>`;
    }).join("");
  }

  function renderOnline(online) {
    const body = qs("#online-body");
    if (!body) return;

    if (!online || online.length === 0) {
      body.innerHTML = `<tr><td colspan="3" class="text-center text-muted py-4">Ainda não recebi ping de nenhum PC.</td></tr>`;
      return;
    }

    body.innerHTML = online.map((row) => {
      const pc = esc(row.pc_name);
      const pcCell = row.machine
        ? `<a href="/machines/${row.machine.id}">${pc}</a>
           <div class="small text-muted">${esc(row.machine.room_name)}</div>`
        : `${pc}<div class="small text-muted">(não cadastrado)</div>`;
      const onlineBadge = row.is_online
        ? `<span class="badge text-bg-success">ONLINE</span>`
        : `<span class="badge text-bg-secondary">OFFLINE</span>`;
      const loginBadge = row.login_active
        ? `<span class="badge text-bg-info">👤 ${esc(row.last_user || "logado")}</span>`
        : `<span class="badge text-bg-secondary">🔒 sem login</span>`;

      return `
        <tr>
          <td class="text-nowrap">${pcCell}</td>
          <td class="text-nowrap">${onlineBadge}
            <div class="small text-muted">${row.age_seconds}s atrás</div>
          </td>
          <td class="text-nowrap">${loginBadge}</td>
        </tr>`;
    }).join("");
  }

  let refreshInFlight = false;
  async function refreshAll(status, threshold) {
    if (refreshInFlight) return;
    refreshInFlight = true;
    try {
      const [tickets, online] = await Promise.all([
        fetchJSON(`/api/tickets?status=${encodeURIComponent(status)}`),
        fetchJSON(`/api/online?threshold=${encodeURIComponent(threshold)}`),
      ]);
      renderTickets(tickets.tickets);
      renderOnline(online.online);
    } catch (_) {
      // O indicador do WebSocket comunica uma eventual desconexão.
    } finally {
      refreshInFlight = false;
    }
  }

  function connectWS(status, threshold) {
    const statusElement = qs("#ws-status");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/tickets`);
    let pingTimer = null;

    ws.onopen = () => {
      if (statusElement) statusElement.textContent = "Ao vivo ✅";
      refreshAll(status, threshold);
      pingTimer = window.setInterval(() => {
        try {
          ws.send("ping");
        } catch (_) {}
      }, 25000);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (
          message &&
          ["ticket_created", "ticket_taken", "ticket_closed"].includes(message.type)
        ) {
          refreshAll(status, threshold);
        }
      } catch (_) {}
    };

    ws.onclose = () => {
      if (statusElement) {
        statusElement.textContent = "Desconectado (tentando reconectar…)";
      }
      if (pingTimer) window.clearInterval(pingTimer);
      window.setTimeout(() => connectWS(status, threshold), 1500);
    };
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = qs("#tickets-page");
    if (!root) return;
    const status = root.getAttribute("data-status") || "OPEN";
    const threshold = root.getAttribute("data-threshold") || "15";

    window.setInterval(() => {
      fetchJSON(`/api/online?threshold=${encodeURIComponent(threshold)}`)
        .then((online) => renderOnline(online.online))
        .catch(() => {});
    }, 10000);

    connectWS(status, threshold);
  });
})();
