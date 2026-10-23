// push_client.js
// Web Push (notificação mesmo com o navegador fechado) via Service Worker.
// Requisito: HTTPS (secure context). Em rede local por IP (http://10.x.x.x) costuma falhar no celular.

(function () {
  if (typeof window === "undefined") return;

  const btn = () => document.getElementById("push-enable-btn");

  function urlB64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, "+")
      .replace(/_/g, "/");

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function fetchPublicKey() {
    const res = await fetch("/push/public_key");
    const data = await res.json();
    return data.publicKey;
  }

  function setBtnState(state, text) {
    const b = btn();
    if (!b) return;
    b.dataset.state = state;
    b.textContent = text;
  }

  function showSmallToast(msg) {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const el = document.createElement("div");
    el.className = "toast-mini";
    el.innerHTML = `<div class="toast-mini__title">Notificações</div><div class="toast-mini__body"></div>`;
    el.querySelector(".toast-mini__body").textContent = msg;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add("toast-mini--hide");
      setTimeout(() => el.remove(), 250);
    }, 4500);
  }

  async function ensureServiceWorker() {
    if (!("serviceWorker" in navigator)) return null;
    try {
      const reg = await navigator.serviceWorker.register("/sw.js");
      return reg;
    } catch (e) {
      return null;
    }
  }

  async function getOrCreateSubscription(reg) {
    const existing = await reg.pushManager.getSubscription();
    if (existing) return existing;

    const publicKey = await fetchPublicKey();
    const applicationServerKey = urlB64ToUint8Array(publicKey);
    return await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    });
  }

  async function sendSubscriptionToServer(sub) {
    const res = await fetch("/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub),
    });
    if (!res.ok) throw new Error("Falha ao salvar subscription");
  }

  async function enablePushFlow() {
    // HTTPS check (a maioria dos browsers exige)
    if (!window.isSecureContext) {
      showSmallToast("Push do sistema exige HTTPS. Com HTTP, só funciona com a página aberta.");
      return;
    }

    if (!("Notification" in window)) {
      showSmallToast("Este navegador não suporta notificações.");
      return;
    }

    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      showSmallToast("Permissão negada. Sem permissão, não dá pra notificar.");
      return;
    }

    const reg = await ensureServiceWorker();
    if (!reg) {
      showSmallToast("Falha ao registrar Service Worker. (HTTPS?)");
      return;
    }

    const sub = await getOrCreateSubscription(reg);
    await sendSubscriptionToServer(sub);

    setBtnState("enabled", "🔔 Ativo");
    showSmallToast("Notificações ativas neste dispositivo.");
  }

  async function initState() {
    const b = btn();
    if (!b) return;

    // Status inicial
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setBtnState("unsupported", "🔕");
      b.title = "Push não suportado aqui";
      return;
    }

    const reg = await ensureServiceWorker();
    if (!reg) {
      setBtnState("off", "🔔");
      b.title = window.isSecureContext ? "Ativar notificações" : "Ativar notificações (precisa HTTPS)";
      return;
    }

    const sub = await reg.pushManager.getSubscription();
    if (sub) setBtnState("enabled", "🔔 Ativo");
    else setBtnState("off", "🔔");

    b.title = window.isSecureContext ? "Ativar notificações" : "Ativar notificações (precisa HTTPS)";
  }

  document.addEventListener("DOMContentLoaded", () => {
    const b = btn();
    if (!b) return;

    initState();

    b.addEventListener("click", () => {
      enablePushFlow().catch(() => showSmallToast("Não consegui ativar o push neste dispositivo."));
    });
  });
})();
