function syncTestedBoxes() {
  document.querySelectorAll(".tested-box").forEach((tested) => {
    const presentId = tested.getAttribute("data-present-id");
    const present = document.getElementById(presentId);
    if (!present) return;

    if (!present.checked) {
      tested.checked = false;
      tested.disabled = true;
    } else {
      tested.disabled = false;
    }
  });
}

function syncQtyInputs() {
  document.querySelectorAll(".qty-input").forEach((qty) => {
    const presentId = qty.getAttribute("data-present-id");
    const present = document.getElementById(presentId);
    if (!present) return;

    if (!present.checked) {
      qty.value = 0;
      qty.disabled = true;
    } else {
      qty.disabled = false;
      if (!qty.value || parseInt(qty.value, 10) <= 0) {
        qty.value = 2;
      }
    }
  });
}

function syncInspectionDateRequired() {
  const inspected = document.getElementById("inspected");
  const dateInput = document.getElementById("last_inspection_date");
  if (!inspected || !dateInput) return;
  dateInput.required = inspected.checked;
}

function syncCheckupDateRequired() {
  const checkup = document.getElementById("checkup_done");
  const dateInput = document.getElementById("last_checkup_date");
  if (!checkup || !dateInput) return;
  dateInput.required = checkup.checked;
}

function syncOfficeFields() {
  const office = document.getElementById("office_installed");
  const version = document.getElementById("office_version");
  if (!office || !version) return;

  if (!office.checked) {
    version.value = "";
    version.disabled = true;
  } else {
    version.disabled = false;
  }
}

function syncKasperskyFields() {
  const kas = document.getElementById("kaspersky_installed");
  const upd = document.getElementById("kaspersky_updated");
  if (!kas || !upd) return;

  if (!kas.checked) {
    upd.checked = false;
    upd.disabled = true;
  } else {
    upd.disabled = false;
  }
}

document.addEventListener("change", (ev) => {
  if (ev.target.classList.contains("present-box")) {
    syncQtyInputs();
    syncTestedBoxes();
  }
  if (ev.target.id === "inspected") syncInspectionDateRequired();
  if (ev.target.id === "checkup_done") syncCheckupDateRequired();
  if (ev.target.id === "office_installed") syncOfficeFields();
  if (ev.target.id === "kaspersky_installed") syncKasperskyFields();
});

document.addEventListener("DOMContentLoaded", () => {
  syncQtyInputs();
  syncTestedBoxes();
  syncInspectionDateRequired();
  syncCheckupDateRequired();
  syncOfficeFields();
  syncKasperskyFields();
});

function syncResponsiveChrome() {
  const mobileTopbar = document.getElementById('mobile-topbar');
  const isMobile = window.matchMedia('(max-width: 720px)').matches;

  if (mobileTopbar) {
    mobileTopbar.hidden = !isMobile;
  }

  if (!isMobile) {
    document.body.classList.remove('sidebar-open');
  }
}

function initMobileSidebar() {
  const btn = document.getElementById('mobile-menu-btn');
  const overlay = document.getElementById('sidebar-overlay');
  const sidebar = document.getElementById('app-sidebar');
  if (!btn || !overlay || !sidebar) return;

  const closeMenu = () => document.body.classList.remove('sidebar-open');
  const openMenu = () => document.body.classList.add('sidebar-open');
  const toggleMenu = () => document.body.classList.toggle('sidebar-open');

  btn.addEventListener('click', toggleMenu);
  overlay.addEventListener('click', closeMenu);

  sidebar.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 1100) closeMenu();
    });
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 1100) closeMenu();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  syncResponsiveChrome();
  initMobileSidebar();

  window.addEventListener('resize', syncResponsiveChrome);
});
