// ── Estado global ────────────────────────────────────────────────────────────
const state = {
  currentPath: null,
  currentName: "",
  breadcrumb:  [],
  navStack:    [],   // [{name, storage_path}] — pilha exata de navegação, sem reconstrução de path
  expanded:    new Set(),
};

// ── Diálogos customizados ─────────────────────────────────────────────────────
function showConfirm(message, { title = "Confirmar", okLabel = "Confirmar", danger = true } = {}) {
  return new Promise(resolve => {
    const overlay = document.getElementById("confirmOverlay");
    document.getElementById("confirmTitle").textContent   = title;
    document.getElementById("confirmMessage").textContent = message;
    const okBtn     = document.getElementById("confirmOkBtn");
    const cancelBtn = document.getElementById("confirmCancelBtn");
    okBtn.textContent = okLabel;
    okBtn.className   = danger ? "modal-btn danger" : "modal-btn confirm";
    overlay.style.display = "flex";
    function cleanup(result) {
      overlay.style.display = "none";
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      overlay.removeEventListener("click", onBg);
      resolve(result);
    }
    const onOk     = () => cleanup(true);
    const onCancel = () => cleanup(false);
    const onBg     = e => { if (e.target === overlay) cleanup(false); };
    okBtn.addEventListener("click",     onOk);
    cancelBtn.addEventListener("click", onCancel);
    overlay.addEventListener("click",   onBg);
  });
}

// ── pywebview ────────────────────────────────────────────────────────────────
function pyReady() {
  return new Promise(resolve => {
    if (window.pywebview) return resolve();
    window.addEventListener("pywebviewready", resolve, { once: true });
  });
}
const api = () => window.pywebview?.api;

// ── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  await pyReady();

  // Se veio com sessão do processo pai (CTk), vai direto pro app
  const session = await api().get_session();
  if (!session.tenant_id) {
    showActivation();
    return;
  }
  await applySidebarLogo();
  if (session.user?.id) {
    showApp();
    showHomeView();
    await loadSession();
    await loadSidebar();
    await checkOffline();
    startConnectivityWatcher();
  } else {
    showLogin();
  }
}

function showActivation() {
  document.getElementById("activationScreen").style.display = "flex";
  document.getElementById("loginScreen").style.display      = "none";
  document.getElementById("appShell").style.display         = "none";
  document.getElementById("activationCode").focus();
}

function initActivation() {
  const btn   = document.getElementById("activationBtn");
  const input = document.getElementById("activationCode");
  const errEl = document.getElementById("activationError");

  async function doActivate() {
    const code = input.value.trim();
    if (!code) { errEl.textContent = "Informe o código de ativação."; return; }
    btn.disabled = true; btn.textContent = "Ativando..."; errEl.textContent = "";
    try {
      const res = await api().license_activate(code);
      if (!res.ok) { errEl.textContent = res.error || "Código de ativação inválido."; return; }
      document.getElementById("activationScreen").style.display = "none";
      await applySidebarLogo();
      showLogin();
    } catch (e) {
      errEl.textContent = "Erro ao ativar. Verifique sua conexão e tente novamente.";
    } finally {
      btn.disabled = false; btn.textContent = "Ativar";
    }
  }

  btn.addEventListener("click", doActivate);
  input.addEventListener("keydown", e => { if (e.key === "Enter") doActivate(); });
}

async function checkOffline() {
  const banner = document.getElementById("offlineBanner");
  if (!banner) return;
  const offline = await api().is_offline();
  banner.style.display = offline ? "" : "none";
}

let _connectivityTimer = null;
function startConnectivityWatcher() {
  if (_connectivityTimer) return;
  let wasOffline = false;
  _connectivityTimer = setInterval(async () => {
    const banner = document.getElementById("offlineBanner");
    if (!banner) return;
    const offline = await api().check_connectivity();
    banner.style.display = offline ? "" : "none";
    if (wasOffline && !offline) {
      // voltou a conexão: recarrega a visão atual para refletir dados reais
      await loadSidebar();
      if (state.currentPath) await loadGrid(state.currentPath);
    }
    wasOffline = offline;
  }, 6000);
}

function showLogin() {
  document.getElementById("loginScreen").style.display = "flex";
  document.getElementById("appShell").style.display    = "none";
  document.getElementById("loginEmail").focus();
}

function showApp() {
  document.getElementById("loginScreen").style.display    = "none";
  document.getElementById("changePwScreen").style.display = "none";
  document.getElementById("appShell").style.display       = "flex";
}

const ALL_VIEWS = ["homeView","folderView","recentView","favoritesView","sharedView","trashView","settingsView"];

function showView(id) {
  ALL_VIEWS.forEach(v => {
    const el = document.getElementById(v);
    if (el) el.style.display = "none";
  });
  const target = document.getElementById(id);
  if (target) target.style.display = "";
  closeDetail();
}

function showHomeView() {
  showView("homeView");
  state.currentPath = null;
  state.breadcrumb  = [];
  state.navStack    = [];
  document.getElementById("breadcrumb").innerHTML = "<strong>Início</strong>";
  setActiveNav("navDocumentos");
  loadHomeDashboard();
}

async function loadHomeDashboard() {
  // Carrega stats, recentes e favoritos em paralelo
  const [stats, recents, favs] = await Promise.all([
    api().get_tenant_stats().catch(() => ({})),
    api().get_recent_files().catch(() => []),
    api().get_favorites().catch(() => []),
  ]);

  // ── Stats ──────────────────────────────────────────────────────────────────
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set("hsTotalFiles",   stats.file_count   ?? "—");
  set("hsTotalFolders", stats.folder_count ?? "—");
  set("hsTotalSize",    stats.total_size   ?? "—");
  set("hsLastChange",   stats.last_change  ? fmtDate(stats.last_change) : "—");
  // reusa os stats já carregados para atualizar a barra de armazenamento
  if (stats.total_size) updateStorageBar(stats);

  // ── Recentes ───────────────────────────────────────────────────────────────
  const recentSection = document.getElementById("homeRecentSection");
  if (recents.length) {
    recentSection.style.display = "";
    renderFlatList("homeRecentList", recents.slice(0, 6), {
      emptyMsg: "",
      metaFn: item => item.last_action_at ? fmtDate(item.last_action_at) : "",
    });
  } else {
    recentSection.style.display = "none";
  }

  // ── Favoritos ──────────────────────────────────────────────────────────────
  const favSection = document.getElementById("homeFavSection");
  if (favs.length) {
    favSection.style.display = "";
    renderFlatList("homeFavList", favs.slice(0, 6), {
      emptyMsg: "",
      metaFn: item => item.updated_at ? fmtDate(item.updated_at) : "",
    });
  } else {
    favSection.style.display = "none";
  }
}

function showFolderView() {
  showView("folderView");
  // folderView uses flex
  const fv = document.getElementById("folderView");
  if (fv) fv.style.display = "flex";
}

// ── Login ─────────────────────────────────────────────────────────────────────
function initLogin() {
  const btn   = document.getElementById("loginBtn");
  const email = document.getElementById("loginEmail");
  const pw    = document.getElementById("loginPassword");
  const errEl = document.getElementById("loginError");

  async function doLogin() {
    const e = email.value.trim();
    const p = pw.value;
    if (!e || !p) { errEl.textContent = "Preencha e-mail e senha."; return; }
    btn.disabled = true; btn.textContent = "Entrando..."; errEl.textContent = "";
    try {
      const res = await api().login(e, p);
      if (!res.ok) { errEl.textContent = res.error || "Credenciais inválidas."; return; }
      if (res.must_change_password) {
        document.getElementById("loginScreen").style.display       = "none";
        document.getElementById("changePwScreen").style.display    = "flex";
        document.getElementById("changePwCancelBtn").style.display = "none";
        document.getElementById("newPw1").focus();
        return;
      }
      showApp();
      showHomeView();
      await loadSession();
      await loadSidebar();
      await applySidebarLogo();
      await checkOffline();
      startConnectivityWatcher();
    } catch(e) {
      errEl.textContent = "Erro ao conectar. Tente novamente.";
    } finally {
      btn.disabled = false; btn.textContent = "Entrar";
    }
  }

  btn.addEventListener("click", doLogin);
  [email, pw].forEach(el => el.addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); }));

  // histórico de e-mails
  const emailInput = document.getElementById("loginEmail");
  const historyBox = document.getElementById("emailHistory");

  async function showEmailHistory() {
    try {
      const history = await api().get_email_history();
      if (!history.length) return;
      historyBox.innerHTML = history.map(e => `
        <div class="email-history-item" data-email="${e}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          ${e}
        </div>`).join("");
      historyBox.classList.add("open");

      historyBox.querySelectorAll(".email-history-item").forEach(item => {
        item.addEventListener("mousedown", e => {
          e.preventDefault(); // evita blur antes do click
          emailInput.value = item.dataset.email;
          historyBox.classList.remove("open");
          document.getElementById("loginPassword").focus();
        });
      });
    } catch(e) { /* silencioso */ }
  }

  emailInput.addEventListener("focus", showEmailHistory);
  emailInput.addEventListener("blur",  () => setTimeout(() => historyBox.classList.remove("open"), 150));
  emailInput.addEventListener("input", () => {
    const q = emailInput.value.toLowerCase();
    historyBox.querySelectorAll(".email-history-item").forEach(item => {
      item.style.display = item.dataset.email.includes(q) ? "" : "none";
    });
    const anyVisible = [...historyBox.querySelectorAll(".email-history-item")].some(i => i.style.display !== "none");
    historyBox.classList.toggle("open", anyVisible);
  });

  // toggle senha
  const toggle = document.getElementById("pwToggle");
  toggle.addEventListener("click", () => {
    const isText = pw.type === "text";
    pw.type = isText ? "password" : "text";
    document.getElementById("eyeOpen").style.display   = isText ? "" : "none";
    document.getElementById("eyeClosed").style.display = isText ? "none" : "";
  });
}

function initChangePw() {
  const btn   = document.getElementById("changePwBtn");
  const errEl = document.getElementById("changePwError");

  btn.addEventListener("click", async () => {
    const p1 = document.getElementById("newPw1").value;
    const p2 = document.getElementById("newPw2").value;
    if (!p1 || p1.length < 6) { errEl.textContent = "Mínimo 6 caracteres."; return; }
    if (p1 !== p2) { errEl.textContent = "As senhas não coincidem."; return; }
    btn.disabled = true; btn.textContent = "Salvando..."; errEl.textContent = "";
    try {
      const res = await api().change_password(p1);
      if (!res.ok) { errEl.textContent = res.error || "Erro ao salvar."; return; }
      showApp();
      showHomeView();
      await loadSession();
      await loadSidebar();
    } catch(e) {
      errEl.textContent = "Erro ao salvar. Tente novamente.";
    } finally {
      btn.disabled = false; btn.textContent = "Salvar e entrar";
    }
  });
}

// ── Sessão ───────────────────────────────────────────────────────────────────
async function loadSession() {
  try {
    const s = await api().get_session();
    if (!s.user?.name) return;
    state.user = s.user;
    const initials = s.user.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
    document.querySelectorAll(".user-avatar").forEach(el => el.textContent = initials);
    document.querySelectorAll(".user-name").forEach(el => el.textContent = s.user.name);
    const at = document.getElementById("userAvatarTop");
    const nt = document.getElementById("userNameTop");
    if (at) at.textContent = initials;
    if (nt) nt.textContent = s.user.name;
    // atualiza dropdown sidebar; badge de notificações com delay para não
    // competir com as queries do dashboard na inicialização
    updateUserMenu(s);
    setTimeout(() => checkNotifBadge(), 2500);
  } catch(e) { console.warn("sem sessão:", e); }
}

// ── Logo da empresa (sidebar, login, troca de senha) ──────────────────────────
function _applyLogoTo(url, iconId, imgId, textId) {
  const icon = document.getElementById(iconId);
  const img  = document.getElementById(imgId);
  const text = document.getElementById(textId);
  if (url) {
    img.src = url;
    img.style.display  = "";
    if (icon) icon.style.display = "none";
    if (text) text.style.display = "none";
  } else {
    img.style.display  = "none";
    if (icon) icon.style.display = "";
    if (text) text.style.display = "";
  }
}

async function applySidebarLogo() {
  let url = "";
  try { url = await api().get_tenant_logo_url(); } catch (e) { /* sem logo */ }
  _applyLogoTo(url, "sidebarLogoIcon", "sidebarLogoImg", null);
  const sidebarText = document.querySelector(".sidebar-logo .logo-text");
  if (sidebarText) sidebarText.style.display = url ? "none" : "";
  _applyLogoTo(url, "loginLogoIcon", "loginLogoImg", "loginLogoText");
  _applyLogoTo(url, "changePwLogoIcon", "changePwLogoImg", "changePwLogoText");
}

async function loadSidebar() {
  const tree = document.getElementById("folderTree");
  tree.innerHTML = '<div class="tree-loading">Carregando...</div>';
  try {
    const folders = await api().get_root_folders();
    tree.innerHTML = "";
    if (!folders.length) {
      tree.innerHTML = '<div class="tree-empty">Nenhuma pasta</div>';
    } else {
      folders.forEach(f => tree.appendChild(buildTreeNode(f, 0)));
    }
    await loadHomeGrid(folders);
    await checkOffline();
  } catch(e) {
    tree.innerHTML = `<div class="tree-empty">Erro ao carregar</div>`;
    console.error(e);
  }
}

async function loadHomeGrid(folders) {
  const grid = document.getElementById("homeGrid");
  grid.innerHTML = "";

  if (!folders.length) {
    grid.innerHTML = `
      <div class="home-grid-empty">
        <div class="home-grid-empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        </div>
        <h3>Nenhuma pasta criada</h3>
        <p>Organize seus documentos criando a primeira pasta. Você pode criar quantas quiser e estruturar do seu jeito.</p>
        <button class="home-grid-empty-btn" id="homeGridEmptyBtn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Criar primeira pasta
        </button>
      </div>`;
    document.getElementById("homeGridEmptyBtn").addEventListener("click", () => openModal("folder"));
    return;
  }

  folders.forEach(f => {
    const card = document.createElement("div");
    card.className = "home-folder-card";
    card.innerHTML = `
      <svg viewBox="0 0 24 24">
        <path d="M3 7C3 5.9 3.9 5 5 5h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"
              fill="#bfdbfe" stroke="#3b82f6" stroke-width=".6"/>
        <path d="M3 10h18" stroke="#93c5fd" stroke-width=".8"/>
      </svg>
      <span class="home-folder-label">${f.name}</span>`;
    card.addEventListener("click", () => {
      showFolderView();
      const node = document.querySelector(`.tree-node[data-path="${f.storage_path}"]`);
      selectNode(node || makeVirtualNode(f.storage_path), f);
      if (node && !state.expanded.has(f.storage_path)) toggleNode(node, f, 0);
    });
    grid.appendChild(card);
  });
}

function makeVirtualNode(path) {
  const n = document.createElement("div");
  n.dataset.path = path;
  const r = document.createElement("div");
  r.className = "tree-row";
  n.appendChild(r);
  return n;
}

function buildTreeNode(folder, depth) {
  const wrap = document.createElement("div");
  wrap.className = "tree-node";
  wrap.dataset.path = folder.storage_path;

  const row = document.createElement("div");
  row.className = "tree-row";
  row.style.paddingLeft = `${12 + depth * 14}px`;

  // chevron (rotaciona ao expandir)
  const chevron = document.createElement("span");
  chevron.className = "tree-chevron";
  chevron.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>`;

  // ícone de pasta
  const icon = document.createElement("span");
  icon.className = "tree-folder-icon";
  icon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;

  const label = document.createElement("span");
  label.className = "tree-label";
  label.textContent = folder.name;

  row.appendChild(chevron);
  row.appendChild(icon);
  row.appendChild(label);
  wrap.appendChild(row);

  // container de filhos (começa fechado)
  const children = document.createElement("div");
  children.className = "tree-children";
  wrap.appendChild(children);

  // clique no chevron → expande/colapsa
  chevron.addEventListener("click", async (e) => {
    e.stopPropagation();
    await toggleNode(wrap, folder, depth);
  });

  // clique na linha → abre a pasta no grid
  row.addEventListener("click", async () => {
    await selectNode(wrap, folder);
    // se ainda não expandido, expande também
    if (!state.expanded.has(folder.storage_path)) {
      await toggleNode(wrap, folder, depth);
    }
  });

  return wrap;
}

async function toggleNode(wrap, folder, depth) {
  const children = wrap.querySelector(".tree-children");
  const chevron  = wrap.querySelector(".tree-chevron");
  const path     = folder.storage_path;

  if (state.expanded.has(path)) {
    // colapsa
    state.expanded.delete(path);
    chevron.classList.remove("open");
    children.innerHTML = "";
  } else {
    // expande — carrega subpastas
    state.expanded.add(path);
    chevron.classList.add("open");
    children.innerHTML = '<div class="tree-loading sub">Carregando...</div>';
    try {
      const subs = await api().get_subfolders(path);
      children.innerHTML = "";
      if (subs.length) {
        subs.forEach(sub => children.appendChild(buildTreeNode(sub, depth + 1)));
      } else {
        chevron.classList.add("leaf"); // sem filhos
      }
    } catch(e) {
      children.innerHTML = '<div class="tree-empty sub">Erro</div>';
    }
  }
}

async function selectNode(wrap, folder) {
  showFolderView();

  document.querySelectorAll(".tree-row.active").forEach(r => r.classList.remove("active"));
  const row = wrap.querySelector(".tree-row");
  if (row) row.classList.add("active");

  // Mantém a pilha de navegação usando os storage_paths exatos do banco.
  // Se a pasta já está na pilha (navegação para trás via breadcrumb), trunca até ela.
  // Caso contrário, empurra como novo nível.
  const existingIdx = state.navStack.findIndex(n => n.storage_path === folder.storage_path);
  if (existingIdx >= 0) {
    state.navStack = state.navStack.slice(0, existingIdx + 1);
  } else {
    state.navStack.push({ name: folder.name, storage_path: folder.storage_path });
  }

  state.currentPath = folder.storage_path;
  state.currentName = folder.name;
  // breadcrumb derivado direto da pilha — sem reconstrução por split de string
  state.breadcrumb  = state.navStack.map(n => ({ name: n.name, path: n.storage_path }));

  updateBreadcrumb();
  updateFolderTitle(folder.name);
  await loadGrid(folder.storage_path);
  await loadStats(folder.storage_path);
}


// ── Breadcrumb ───────────────────────────────────────────────────────────────
function updateBreadcrumb() {
  const bc     = document.getElementById("breadcrumb");
  const crumbs = [{ name: "Início", path: null }, ...state.breadcrumb];
  bc.innerHTML = crumbs.map((c, i) => {
    const isLast = i === crumbs.length - 1;
    if (isLast) return `<strong>${c.name}</strong>`;
    return `<a href="#" data-path="${c.path ?? ""}" data-name="${c.name}">${c.name}</a><span class="sep">›</span>`;
  }).join("");

  bc.querySelectorAll("a").forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      if (a.dataset.path === "") {
        // voltar para home
        showHomeView();
        document.querySelectorAll(".tree-row.active").forEach(r => r.classList.remove("active"));
        return;
      }
      const node = document.querySelector(`.tree-node[data-path="${a.dataset.path}"]`);
      const folder = { storage_path: a.dataset.path, name: a.dataset.name };
      selectNode(node || makeVirtualNode(a.dataset.path), folder);
    });
  });
}

function updateFolderTitle(name) {
  const h1 = document.getElementById("folderName");
  if (h1) h1.textContent = name;
}

// ── Renomear ──────────────────────────────────────────────────────────────────
function startRename(item) {
  modalMode = "rename";
  const label = item.type === "folder" ? "pasta" : "arquivo";
  document.getElementById("modalTitle").textContent   = `Renomear ${label}`;
  document.getElementById("modalLabel").textContent   = "Novo nome";
  document.getElementById("modalInput").value         = item.name;
  document.getElementById("modalError").textContent   = "";
  document.getElementById("fileTypeGroup").style.display = "none";
  document.getElementById("modalConfirm").textContent = "Renomear";
  document.getElementById("modalOverlay").classList.add("open");
  const input = document.getElementById("modalInput");
  input.focus();
  // seleciona só o nome sem a extensão para arquivos
  const dot = item.name.lastIndexOf(".");
  input.setSelectionRange(0, dot > 0 ? dot : item.name.length);

  // troca o handler do botão confirmar temporariamente
  const confirmBtn = document.getElementById("modalConfirm");
  const originalHandler = confirmBtn.onclick;
  confirmBtn.onclick = null;

  async function doRename() {
    const newName = document.getElementById("modalInput").value.trim();
    const errEl   = document.getElementById("modalError");
    if (!newName) { errEl.textContent = "Digite um nome."; return; }
    confirmBtn.disabled    = true;
    confirmBtn.textContent = "Salvando...";
    try {
      const fn  = item.type === "folder" ? "rename_folder" : "rename_file";
      const res = await api()[fn](item.id, newName);
      if (!res.ok) { errEl.textContent = res.error || "Erro ao renomear."; return; }
      closeModal();
      showToast(`Renomeado para "${newName}".`, "ok");
      await loadGrid(state.currentPath);
      await loadSidebar();
    } finally {
      confirmBtn.disabled    = false;
      confirmBtn.textContent = "Renomear";
      confirmBtn.onclick     = originalHandler;
    }
  }

  confirmBtn.onclick = doRename;
  document.getElementById("modalInput").onkeydown = e => { if (e.key === "Enter") doRename(); };
}

// ── Dropdown de ações da linha ────────────────────────────────────────────────
function closeRowDropdown() {
  document.querySelector(".row-dropdown")?.remove();
}

function openRowDropdown(e, item) {
  closeRowDropdown();
  const isFile   = item.type === "file";
  const isFolder = item.type === "folder";

  const actions = [];

  if (isFile) actions.push({
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
    label: "Abrir", action: () => openFile(item.storage_path, item.name),
  });

  if (isFolder) actions.push({
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
    label: "Abrir pasta", action: () => {
      let node = document.querySelector(`.tree-node[data-path="${item.storage_path}"]`);
      if (!node) { node = document.createElement("div"); node.dataset.path = item.storage_path; node.appendChild(document.createElement("div")).className = "tree-row"; }
      closeDetail();
      selectNode(node, item);
    },
  });

  actions.push({
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
    label: "Renomear", action: () => startRename(item),
  });

  if (isFile) actions.push({
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`,
    label: "Compartilhar", action: () => {
      openDetail(item);
      document.querySelector(".detail-btn.share")?.click();
    },
  });

  actions.push({
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
    label: "Favoritar", action: async () => {
      const res = await api().toggle_favorite(item.storage_path);
      showToast(res.is_favorite ? "Adicionado aos favoritos." : "Removido dos favoritos.", "ok");
    },
  });

  actions.push({ sep: true });

  actions.push({
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>`,
    label: "Mover para lixeira", danger: true, action: async () => {
      const label = item.type === "folder" ? "pasta" : "arquivo";
      const ok = await showConfirm(`Mover ${label} "${item.name}" para a lixeira?`, { title: "Excluir item", okLabel: "Excluir" });
      if (!ok) return;
      const res = await api().delete_item(item.type, item.id, item.storage_path);
      if (res.ok) {
        showToast(`"${item.name}" movido para a lixeira.`, "ok");
        closeDetail();
        await loadGrid(state.currentPath);
        await loadStats(state.currentPath);
        await loadSidebar();
      } else {
        showToast(res.error || "Erro ao excluir.", "error");
      }
    },
  });

  const menu = document.createElement("div");
  menu.className = "row-dropdown";
  menu.innerHTML = actions.map((a, i) => a.sep
    ? `<div class="row-dropdown-sep"></div>`
    : `<div class="row-dropdown-item${a.danger ? " danger" : ""}" data-idx="${i}">${a.icon}${a.label}</div>`
  ).join("");

  document.body.appendChild(menu);

  // posiciona próximo ao botão
  const btn = e.currentTarget;
  const rect = btn.getBoundingClientRect();
  const mw = 190, mh = menu.offsetHeight || 240;
  let top  = rect.bottom + 4;
  let left = rect.right - mw;
  if (top + mh > window.innerHeight) top = rect.top - mh - 4;
  if (left < 8) left = 8;
  menu.style.top  = `${top}px`;
  menu.style.left = `${left}px`;

  menu.querySelectorAll(".row-dropdown-item").forEach(el => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.idx);
      closeRowDropdown();
      actions[idx].action();
    });
  });

  setTimeout(() => document.addEventListener("click", closeRowDropdown, { once: true }), 0);
}

// ── Grid ─────────────────────────────────────────────────────────────────────
async function loadGrid(path) {
  const tbody = document.getElementById("fileList");
  tbody.innerHTML = '<tr><td colspan="5" class="loading-cell">Carregando...</td></tr>';
  try {
    const items = await api().get_children(path);
    await checkOffline();
    const footer = document.querySelector(".file-list-footer");
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">Pasta vazia</td></tr>';
      if (footer) footer.textContent = "0 itens";
      return;
    }
    tbody.innerHTML = items.map(item => {
      const icon = item.type === "folder"
        ? `<span class="grid-icon folder-ic"><svg viewBox="0 0 24 24" fill="#fbbf24" stroke="#d97706" stroke-width="1.2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></span>`
        : `<span class="grid-icon file-ic ${fileExt(item.name)}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>`;
      const size = item.type === "folder" ? "—" : (item.size || "—");
      const date = item.updated_at ? fmtDate(item.updated_at) : "—";
      return `
        <tr class="item-row" data-type="${item.type}" data-path="${item.storage_path}" data-name="${item.name}">
          <td class="name-cell">${icon}<span>${item.name}</span></td>
          <td>${item.type === "folder" ? "Pasta" : extLabel(item.name)}</td>
          <td>${size}</td>
          <td>${date}</td>
          <td><button class="btn-more">⋮</button></td>
        </tr>`;
    }).join("");

    tbody.querySelectorAll(".item-row").forEach(row => {
      const item = items.find(i => i.storage_path === row.dataset.path);

      // clique simples → seleciona + abre painel de detalhes
      row.addEventListener("click", e => {
        if (e.target.closest(".btn-more")) return;
        tbody.querySelectorAll(".item-row").forEach(r => r.classList.remove("selected"));
        row.classList.add("selected");
        if (item) openDetail(item);
      });

      // duplo clique em pasta → navega; em arquivo → abre
      row.addEventListener("dblclick", async e => {
        if (e.target.closest(".btn-more")) return;
        if (row.dataset.type === "folder") {
          const folder = { storage_path: row.dataset.path, name: row.dataset.name };
          let node = document.querySelector(`.tree-node[data-path="${row.dataset.path}"]`);
          if (!node) {
            node = document.createElement("div");
            node.dataset.path = row.dataset.path;
            node.appendChild(document.createElement("div")).className = "tree-row";
          }
          closeDetail();
          await selectNode(node, folder);
        } else {
          await openFile(row.dataset.path, row.dataset.name);
        }
      });

      // botão ⋮ → dropdown de ações
      row.querySelector(".btn-more")?.addEventListener("click", e => {
        e.stopPropagation();
        openRowDropdown(e, item);
      });
    });

    if (footer) footer.textContent = `${items.length} ${items.length === 1 ? "item" : "itens"}`;
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">Erro: ${e}</td></tr>`;
  }
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats(path) {
  try {
    const s = await api().get_folder_stats(path);
    const fc = s.file_count   ?? "—";
    const fo = s.folder_count ?? "—";
    const sz = s.total_size   ?? "—";
    // stats cards
    const cards = document.querySelectorAll(".stat-value");
    if (cards[0]) cards[0].textContent = fc;
    if (cards[1]) cards[1].textContent = fo;
    if (cards[2]) cards[2].textContent = sz;
    const lc = document.getElementById("statLastChange");
    if (lc) lc.textContent = s.last_change ? fmtDate(s.last_change) : "—";
    // folder meta (topbar)
    const mf = document.getElementById("metaFiles");
    const mfo = document.getElementById("metaFolders");
    const ms = document.getElementById("metaSize");
    if (mf)  mf.textContent  = `${fc} arquivo(s)`;
    if (mfo) mfo.textContent = `${fo} pasta(s)`;
    if (ms)  ms.textContent  = sz;
  } catch(e) { /* silencioso */ }
}

// ── Painel de detalhes ────────────────────────────────────────────────────────
let detailItem = null;

function openDetail(item) {
  detailItem = item;
  const panel = document.getElementById("detailPanel");
  panel.classList.add("open");

  // ícone
  const iconEl = document.getElementById("detailIcon");
  if (item.type === "folder") {
    iconEl.innerHTML = `<svg viewBox="0 0 24 24" fill="#fbbf24" stroke="#d97706" stroke-width="1"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
  } else {
    const colors = { pdf:"#ef4444", doc:"#3b82f6", img:"#22c55e", xls:"#16a34a", txt:"#64748b", generic:"#94a3b8" };
    const ext = fileExt(item.name);
    const c = colors[ext] || colors.generic;
    iconEl.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  }

  document.getElementById("detailName").textContent = item.name;
  document.getElementById("dType").textContent      = item.type === "folder" ? "Pasta" : extLabel(item.name);
  document.getElementById("dLocation").textContent  = maskPath(item.storage_path.split("/").slice(0, -1).join("/")) || "Raiz";
  document.getElementById("dSize").textContent      = item.type === "folder" ? "—" : (item.size || "—");
  document.getElementById("dCreated").textContent   = item.updated_at ? fmtDate(item.updated_at) : "—";
  document.getElementById("dModified").textContent  = item.updated_at ? fmtDate(item.updated_at) : "—";

  // atualiza estado do botão favoritar
  const favBtn = document.getElementById("detailFavBtn");
  if (favBtn) {
    api().is_favorite(item.storage_path).then(isFav => {
      favBtn.classList.toggle("active", isFav);
      favBtn.querySelector("svg").setAttribute("fill", isFav ? "#f59e0b" : "none");
    });
  }
}

function closeDetail() {
  detailItem = null;
  document.getElementById("detailPanel").classList.remove("open");
  // reseta para aba Detalhes
  document.querySelectorAll(".detail-tab").forEach((t, i) => t.classList.toggle("active", i === 0));
  document.getElementById("detailBody").style.display     = "";
  document.getElementById("detailActivity").style.display = "none";
}

async function loadItemActivity(name) {
  const list = document.getElementById("activityList");
  list.innerHTML = '<p class="activity-empty">Carregando...</p>';
  try {
    const items = await api().get_item_activity(name);
    if (!items.length) {
      list.innerHTML = '<p class="activity-empty">Nenhuma atividade registrada.</p>';
      return;
    }
    list.innerHTML = items.map(a => `
      <div class="activity-item">
        <div class="activity-dot"></div>
        <div class="activity-info">
          <span class="activity-action"><strong>${a.user_name}</strong> ${a.action}</span>
          <span class="activity-meta">${fmtDate(a.created_at)}</span>
        </div>
      </div>`).join("");
  } catch(e) {
    list.innerHTML = `<p class="activity-empty">Erro ao carregar.</p>`;
  }
}

async function openFile(storagePath, filename) {
  showToast(`Abrindo ${filename}…`, "info");
  try {
    const res = await api().open_file(storagePath, filename);
    if (!res.ok) showToast(`Erro ao abrir: ${res.error}`, "error");
  } catch(e) {
    showToast(`Erro ao abrir: ${e}`, "error");
  }
}

function initDetailTabs() {
  document.querySelectorAll(".detail-tab").forEach(tab => {
    tab.addEventListener("click", async () => {
      document.querySelectorAll(".detail-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const isActivity = tab.dataset.tab === "activity";
      document.getElementById("detailBody").style.display     = isActivity ? "none" : "";
      document.getElementById("detailActivity").style.display = isActivity ? "" : "none";
      if (isActivity && detailItem) await loadItemActivity(detailItem.name);
    });
  });

  document.getElementById("detailDeleteBtn")?.addEventListener("click", async () => {
    if (!detailItem) return;
    const label = detailItem.type === "folder" ? "pasta" : "arquivo";
    const ok = await showConfirm(`Excluir ${label} "${detailItem.name}"?\nEsta ação moverá o item para a lixeira.`, { title: "Excluir item", okLabel: "Excluir" });
    if (!ok) return;
    try {
      const res = await api().delete_item(detailItem.type, detailItem.id, detailItem.storage_path);
      if (res.ok) {
        showToast(`${detailItem.name} excluído.`, "success");
        closeDetail();
        await loadGrid(state.currentPath);
        await loadStats(state.currentPath);
      } else {
        showToast(`Erro: ${res.error}`, "error");
      }
    } catch(e) {
      showToast(`Erro: ${e}`, "error");
    }
  });
}

// ── Search ────────────────────────────────────────────────────────────────────
function initSearch() {
  const input = document.querySelector(".search-box input");
  if (!input) return;
  input.addEventListener("input", () => {
    const q = input.value.toLowerCase();
    document.querySelectorAll(".item-row").forEach(row => {
      row.style.display = row.dataset.name.toLowerCase().includes(q) ? "" : "none";
    });
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// Remove o primeiro segmento do path (tenant ID UUID) e formata para exibição
function maskPath(path) {
  if (!path) return "";
  const parts = path.split("/").filter(Boolean);
  // se o primeiro segmento parece um UUID (tenant), remove
  if (parts.length > 0 && /^[0-9a-f-]{36}$/i.test(parts[0])) {
    parts.shift();
  }
  return parts.join(" / ");
}

function fileExt(name) {
  const ext = name.split(".").pop().toLowerCase();
  const map = { pdf:"pdf", txt:"txt", doc:"doc", docx:"doc",
                png:"img", jpg:"img", jpeg:"img", xlsx:"xls", xls:"xls" };
  return map[ext] || "generic";
}
function extLabel(name) {
  return name.split(".").pop().toUpperCase() || "Arquivo";
}
function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day:"2-digit", month:"2-digit", year:"numeric",
      hour:"2-digit", minute:"2-digit"
    });
  } catch { return iso; }
}

// ── Dropdown Novo ─────────────────────────────────────────────────────────────
function initNewDropdown() {
  // dropdown dentro do folderView
  const dd       = document.getElementById("newDropdown");
  const btnNew   = document.getElementById("btnNew");
  const btnCaret = document.getElementById("btnNewCaret");
  function toggle() { dd.classList.toggle("open"); }
  function close()  { dd.classList.remove("open"); }
  btnNew.addEventListener("click",   toggle);
  btnCaret.addEventListener("click", toggle);
  document.getElementById("ddNewFolder").addEventListener("click", () => { close(); openModal("folder"); });
  document.getElementById("ddNewFile").addEventListener("click",   () => { close(); openModal("file"); });

  // dropdown na home (só "Nova pasta")
  const ddHome       = document.getElementById("newDropdownHome");
  const btnNewHome   = document.getElementById("btnNewHome");
  const btnCaretHome = document.getElementById("btnNewCaretHome");
  function toggleHome() { ddHome.classList.toggle("open"); }
  function closeHome()  { ddHome.classList.remove("open"); }
  btnNewHome.addEventListener("click",   toggleHome);
  btnCaretHome.addEventListener("click", toggleHome);
  document.getElementById("ddNewFolderHome").addEventListener("click", () => { closeHome(); openModal("folder"); });

  // fecha ambos ao clicar fora
  document.addEventListener("click", e => {
    if (!e.target.closest("#btnNewGroup"))     close();
    if (!e.target.closest("#btnNewGroupHome")) closeHome();
  });
}

// ── Modal criar ───────────────────────────────────────────────────────────────
let modalMode = "folder";

function openModal(mode) {
  modalMode = mode;
  document.getElementById("modalTitle").textContent = mode === "folder" ? "Nova pasta" : "Novo arquivo";
  document.getElementById("modalLabel").textContent = mode === "folder" ? "Nome da pasta" : "Nome do arquivo";
  document.getElementById("modalInput").value = "";
  document.getElementById("modalError").textContent = "";
  document.getElementById("fileTypeGroup").style.display = mode === "file" ? "" : "none";
  // reseta seleção para .txt
  const radios = document.querySelectorAll("input[name='fileType']");
  radios.forEach(r => { r.checked = r.value === ".txt"; });
  document.getElementById("modalOverlay").classList.add("open");
  document.getElementById("modalInput").focus();
}

function closeModal() {
  document.getElementById("modalOverlay").classList.remove("open");
  if (modalMode === "rename") modalMode = "folder";
}

async function confirmModal() {
  if (modalMode === "rename") return; // tratado pelo startRename
  const name = document.getElementById("modalInput").value.trim();
  const errEl = document.getElementById("modalError");
  if (!name) { errEl.textContent = "Digite um nome."; return; }

  const btn = document.getElementById("modalConfirm");
  btn.disabled = true;
  btn.textContent = "Criando...";
  errEl.textContent = "";

  const parentPath = state.currentPath ?? "";
  try {
    let res;
    if (modalMode === "folder") {
      res = await api().create_folder(name, parentPath);
    } else {
      const ext      = document.querySelector("input[name='fileType']:checked")?.value || ".txt";
      const fullName = name.includes(".") ? name : name + ext;
      res = await api().create_file(fullName, parentPath);
    }
    if (!res.ok) { errEl.textContent = res.error || "Erro ao criar."; return; }
    closeModal();
    if (parentPath === "") {
      // estamos na home — recarrega a grid de pastas raiz
      const folders = await api().get_root_folders();
      loadHomeGrid(folders);
      await loadSidebar();
    } else {
      await loadGrid(parentPath);
      await loadStats(parentPath);
    }
    showToast(`"${name}" criado com sucesso!`);
  } catch(e) {
    errEl.textContent = `Erro: ${e}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Criar";
  }
}

function initModal() {
  document.getElementById("modalClose").addEventListener("click",   closeModal);
  document.getElementById("modalCancel").addEventListener("click",  closeModal);
  document.getElementById("modalConfirm").addEventListener("click", confirmModal);
  document.getElementById("modalInput").addEventListener("keydown", e => {
    if (e.key === "Enter") confirmModal();
    if (e.key === "Escape") closeModal();
  });
  document.getElementById("modalOverlay").addEventListener("click", e => {
    if (e.target === document.getElementById("modalOverlay")) closeModal();
  });
}

// ── Upload ────────────────────────────────────────────────────────────────────
function initUpload() {
  const btnUpload = document.getElementById("btnUpload");
  const fileInput = document.getElementById("fileInput");

  btnUpload.addEventListener("click", () => {
    if (!state.currentPath) return showToast("Selecione uma pasta primeiro.", "warn");
    fileInput.click();
  });

  fileInput.addEventListener("change", async () => {
    const files = Array.from(fileInput.files);
    if (!files.length) return;
    fileInput.value = "";

    const overlay  = document.getElementById("uploadOverlay");
    const nameEl   = document.getElementById("uploadFilename");
    const barEl    = document.getElementById("uploadBarFill");
    const countEl  = document.getElementById("uploadCounter");

    overlay.classList.add("open");
    let done = 0;
    let failed = 0;
    let lastError = "";

    for (const file of files) {
      nameEl.textContent  = file.name;
      countEl.textContent = `${done} / ${files.length}`;

      try {
        // lê o arquivo como base64 e manda pro Python
        const b64 = await toBase64(file);
        const res = await api().upload_file(file.name, b64, state.currentPath);
        if (!res.ok) { failed++; lastError = res.error || ""; }
      } catch(e) {
        failed++;
        console.warn("upload error:", file.name, e);
      }

      done++;
      barEl.style.width = `${(done / files.length) * 100}%`;
      countEl.textContent = `${done} / ${files.length}`;
    }

    nameEl.textContent = "Concluído!";
    await new Promise(r => setTimeout(r, 900));
    overlay.classList.remove("open");
    barEl.style.width = "0%";
    await loadGrid(state.currentPath);
    await loadStats(state.currentPath);
    if (failed) {
      showToast(lastError || `${failed} arquivo(s) não puderam ser enviados.`, "warn");
    } else {
      showToast(`${done} arquivo(s) enviado(s) com sucesso!`);
    }
  });
}

function toBase64(file) {
  return new Promise((res, rej) => {
    const reader = new FileReader();
    reader.onload  = () => res(reader.result.split(",")[1]); // remove "data:...;base64,"
    reader.onerror = rej;
    reader.readAsDataURL(file);
  });
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = "ok") {
  let toast = document.getElementById("zynorToast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "zynorToast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className   = `toast toast-${type} show`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => toast.classList.remove("show"), 3000);
}

// ── Notificações ─────────────────────────────────────────────────────────────
function initNotifications() {
  const btn      = document.getElementById("btnNotif");
  const dropdown = document.getElementById("notifDropdown");
  const badge    = document.getElementById("notifBadge");
  if (!btn) return;

  btn.addEventListener("click", async e => {
    e.stopPropagation();
    const isOpen = dropdown.style.display !== "none";
    dropdown.style.display = isOpen ? "none" : "block";
    if (!isOpen) {
      badge.style.display = "none";
      await loadNotifications();
    }
  });
  document.addEventListener("click", () => { dropdown.style.display = "none"; });
}

async function loadNotifications() {
  const list = document.getElementById("notifList");
  list.innerHTML = '<p class="notif-empty">Carregando...</p>';
  const items = await api().get_notifications(15).catch(() => []);
  if (!items.length) {
    list.innerHTML = '<p class="notif-empty">Nenhuma atividade recente.</p>';
    return;
  }
  list.innerHTML = items.map(n => {
    const actionMap = {
      "abriu": "abriu", "criou": "criou", "fez upload": "enviou",
      "excluiu": "excluiu", "renomeou": "renomeou", "compartilhou": "compartilhou",
    };
    const verb = actionMap[n.action] || n.action;
    return `
      <div class="notif-item">
        <div class="notif-dot"></div>
        <div class="notif-text">
          <strong>${n.user_name}</strong> ${verb}
          <em>${n.target_name || ""}</em>
        </div>
        <span class="notif-time">${fmtDate(n.created_at)}</span>
      </div>`;
  }).join("");
}

// Mostra badge se houver atividade recente
async function checkNotifBadge() {
  const badge = document.getElementById("notifBadge");
  if (!badge) return;
  const items = await api().get_notifications(1).catch(() => []);
  badge.style.display = items.length ? "inline-block" : "none";
}

// ── Menu de usuário (sidebar) ────────────────────────────────────────────────
function initUserMenu() {
  const trigger  = document.getElementById("userTopbar");
  const dropdown = document.getElementById("userDropdown");
  if (!trigger) return;

  trigger.addEventListener("click", e => {
    e.stopPropagation();
    const isOpen = dropdown.style.display !== "none";
    dropdown.style.display = isOpen ? "none" : "block";
  });
  document.addEventListener("click", () => { if (dropdown) dropdown.style.display = "none"; });

  // Trocar senha — reutiliza a tela de change password
  document.getElementById("btnChangePw")?.addEventListener("click", () => {
    dropdown.style.display = "none";
    document.getElementById("appShell").style.display          = "none";
    document.getElementById("changePwScreen").style.display    = "flex";
    document.getElementById("changePwCancelBtn").style.display = "";
    document.getElementById("newPw1").focus();
  });

  document.getElementById("changePwCancelBtn")?.addEventListener("click", () => {
    document.getElementById("newPw1").value = "";
    document.getElementById("newPw2").value = "";
    document.getElementById("changePwError").textContent = "";
    document.getElementById("changePwScreen").style.display = "none";
    document.getElementById("appShell").style.display       = "flex";
  });

  // Sair
  document.getElementById("btnLogout")?.addEventListener("click", async () => {
    dropdown.style.display = "none";
    const ok = await showConfirm("Deseja sair do sistema?", { title: "Sair", okLabel: "Sair", danger: false });
    if (!ok) return;
    await api().logout().catch(() => {});
    document.getElementById("appShell").style.display    = "none";
    document.getElementById("loginScreen").style.display = "flex";
    document.getElementById("loginEmail").focus();
    // limpa estado
    state.currentPath = null;
    state.navStack    = [];
    state.breadcrumb  = [];
  });
}

// Actualiza dados de usuário no dropdown da sidebar
function updateUserMenu(session) {
  if (!session?.user) return;
  const u = session.user;
  const initials = u.name?.split(" ").map(w => w[0]).slice(0,2).join("").toUpperCase() || "?";
  const roleMap  = { admin: "Administrador", user: "Usuário" };

  const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  setTxt("userAvatarTop", initials);
  setTxt("userNameTop",   u.name  || "");
  setTxt("userAvatarDd",  initials);
  setTxt("userNameDd",    u.name  || "");
  setTxt("userEmailDd",   u.email || "");
}

// ── Armazenamento real na sidebar ────────────────────────────────────────────
const PLAN_LIMIT_GB = 100;

async function updateStorageBar(stats) {
  try {
    if (!stats) stats = await api().get_tenant_stats();
    const usedRaw = stats.total_size || "0 B";
    // converte para GB para calcular %
    const toBytes = s => {
      const [n, u] = s.split(" ");
      const m = { B:1, KB:1024, MB:1024**2, GB:1024**3, TB:1024**4 };
      return parseFloat(n) * (m[u] || 1);
    };
    const usedBytes = toBytes(usedRaw);
    const limitBytes = PLAN_LIMIT_GB * 1024 ** 3;
    const pct = Math.min((usedBytes / limitBytes) * 100, 100).toFixed(1);

    const label = document.getElementById("storageUsedLabel");
    const fill  = document.getElementById("storageFill");
    if (label) label.textContent = `${usedRaw} de ${PLAN_LIMIT_GB} GB`;
    if (fill)  fill.style.width  = `${pct}%`;
  } catch(e) { /* silencioso */ }
}

// ── Modal de planos ───────────────────────────────────────────────────────────
function initPlanModal() {
  const openModal = async () => {
    const overlay = document.getElementById("planOverlay");
    overlay.style.display = "flex";
    try {
      const stats = await api().get_tenant_stats();
      const toBytes = s => {
        const [n, u] = (s || "0 B").split(" ");
        const m = { B:1, KB:1024, MB:1024**2, GB:1024**3, TB:1024**4 };
        return parseFloat(n) * (m[u] || 1);
      };
      const usedBytes = toBytes(stats.total_size);
      const limitBytes = PLAN_LIMIT_GB * 1024 ** 3;
      const pct = Math.min((usedBytes / limitBytes) * 100, 100).toFixed(1);

      const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
      set("planFiles",          stats.file_count   || 0);
      set("planFolders",        stats.folder_count || 0);
      set("planSize",           stats.total_size   || "0 B");
      set("planStorageDetail",  `${stats.total_size || "0 B"} de ${PLAN_LIMIT_GB} GB`);
      const fill = document.getElementById("planStorageFill");
      if (fill) fill.style.width = `${pct}%`;
    } catch(e) { /* silencioso */ }
  };

  document.getElementById("btnManagePlan")?.addEventListener("click", openModal);
  const close = () => { document.getElementById("planOverlay").style.display = "none"; };
  document.getElementById("planClose")?.addEventListener("click",    close);
  document.getElementById("planCloseBtn")?.addEventListener("click", close);
  document.getElementById("planOverlay")?.addEventListener("click",  e => { if (e.target.id === "planOverlay") close(); });
}

// ── Compartilhar ──────────────────────────────────────────────────────────────
function initShare() {
  const overlay   = document.getElementById("shareOverlay");
  const linkWrap  = document.getElementById("shareLinkWrap");
  const linkInput = document.getElementById("shareLinkInput");
  const errorEl   = document.getElementById("shareError");
  const noteEl    = document.getElementById("shareExpireNote");
  const genBtn    = document.getElementById("shareGenBtn");

  function closeShare() {
    overlay.classList.remove("open");
    linkWrap.style.display = "none";
    linkInput.value = "";
    errorEl.textContent = "";
    genBtn.disabled = false;
    genBtn.textContent = "Gerar link";
  }

  document.getElementById("shareClose").addEventListener("click",  closeShare);
  document.getElementById("shareCancel").addEventListener("click", closeShare);
  overlay.addEventListener("click", e => { if (e.target === overlay) closeShare(); });

  genBtn.addEventListener("click", async () => {
    if (!detailItem || detailItem.type !== "file") return;
    genBtn.disabled = true;
    genBtn.textContent = "Gerando...";
    errorEl.textContent = "";
    const hours = parseInt(document.querySelector("input[name='shareExpire']:checked")?.value || "24");
    const res = await api().share_file(detailItem.storage_path, detailItem.name, hours);
    genBtn.disabled = false;
    genBtn.textContent = "Gerar link";
    if (!res.ok) { errorEl.textContent = res.error; return; }
    linkInput.value = res.url;
    linkWrap.style.display = "";
    const label = hours < 24 ? `${hours}h` : hours === 24 ? "24 horas" : "7 dias";
    noteEl.textContent = `Este link expira em ${label}.`;
  });

  document.getElementById("shareCopyBtn").addEventListener("click", () => {
    if (!linkInput.value) return;
    navigator.clipboard.writeText(linkInput.value).then(() => showToast("Link copiado!", "ok"));
  });

  // abre o modal ao clicar em Compartilhar no painel de detalhes
  document.querySelector(".detail-btn.share").addEventListener("click", () => {
    if (!detailItem || detailItem.type !== "file") {
      showToast("Selecione um arquivo para compartilhar.", "warn"); return;
    }
    linkWrap.style.display = "none";
    linkInput.value = "";
    errorEl.textContent = "";
    document.querySelector("input[name='shareExpire'][value='24']").checked = true;
    overlay.classList.add("open");
  });
}

// ── Nav active state ──────────────────────────────────────────────────────────
function setActiveNav(activeId) {
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  const el = document.getElementById(activeId);
  if (el) el.classList.add("active");
}

// ── Flat list renderer ────────────────────────────────────────────────────────
function renderFlatList(containerId, items, opts = {}) {
  const el = document.getElementById(containerId);
  if (!items.length) {
    el.innerHTML = `<p class="flat-empty">${opts.emptyMsg || "Nenhum item encontrado."}</p>`;
    return;
  }
  el.innerHTML = items.map(item => {
    const isFolder = item.type === "folder";
    const icon = isFolder
      ? `<svg viewBox="0 0 24 24" fill="#fbbf24" stroke="#d97706" stroke-width="1"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
    const meta = opts.metaFn ? opts.metaFn(item) : (item.updated_at ? fmtDate(item.updated_at) : "");
    const actions = opts.actionsFn ? opts.actionsFn(item) : "";
    return `
      <div class="flat-item" data-path="${item.storage_path}" data-type="${item.type}" data-name="${item.name}">
        <div class="flat-item-icon">${icon}</div>
        <div class="flat-item-info">
          <div class="flat-item-name">${item.name}</div>
          ${meta ? `<div class="flat-item-meta">${meta}</div>` : ""}
        </div>
        <span class="flat-item-size">${item.size || ""}</span>
        <div class="flat-item-actions">${actions}</div>
      </div>`;
  }).join("");

  el.querySelectorAll(".flat-item").forEach(row => {
    row.addEventListener("dblclick", async () => {
      if (row.dataset.type === "file") {
        await openFile(row.dataset.path, row.dataset.name);
      } else {
        showFolderView();
        const node = document.querySelector(`.tree-node[data-path="${row.dataset.path}"]`) || makeVirtualNode(row.dataset.path);
        await selectNode(node, { storage_path: row.dataset.path, name: row.dataset.name });
      }
    });
  });
}

// ── Recentes ──────────────────────────────────────────────────────────────────
async function loadRecentView() {
  showView("recentView");
  setActiveNav("navRecent");
  document.getElementById("recentList").innerHTML = '<p class="flat-empty">Carregando...</p>';
  const items = await api().get_recent_files();
  renderFlatList("recentList", items, {
    emptyMsg: "Nenhum arquivo acessado recentemente.",
    metaFn: item => `${item.last_action} em ${fmtDate(item.last_action_at)}`,
  });
}

// ── Favoritos ─────────────────────────────────────────────────────────────────
async function loadFavoritesView() {
  showView("favoritesView");
  setActiveNav("navFavorites");
  document.getElementById("favoritesList").innerHTML = '<p class="flat-empty">Carregando...</p>';
  const items = await api().get_favorites();
  renderFlatList("favoritesList", items, {
    emptyMsg: "Nenhum favorito ainda. Clique em ★ Favoritar no painel de detalhes.",
    metaFn: item => item.updated_at ? fmtDate(item.updated_at) : "",
    actionsFn: item => `<button onclick="removeFav('${item.storage_path}')">Remover</button>`,
  });
}

async function removeFav(storage_path) {
  await api().toggle_favorite(storage_path);
  await loadFavoritesView();
}

// ── Compartilhados ────────────────────────────────────────────────────────────
async function loadSharedView() {
  showView("sharedView");
  setActiveNav("navShared");
  document.getElementById("sharedList").innerHTML = '<p class="flat-empty">Carregando...</p>';
  const items = await api().get_shared_files();
  renderFlatList("sharedList", items, {
    emptyMsg: "Nenhum arquivo foi compartilhado ainda.",
    metaFn: item => `Compartilhado por ${item.shared_by} em ${fmtDate(item.shared_at)}`,
    actionsFn: item => `<button onclick="reshareFile('${item.storage_path}','${item.name.replace(/'/g,"\\'")}')" >Copiar link</button>`,
  });
}

async function reshareFile(storage_path, name) {
  const btn = event.currentTarget || event.target;
  btn.disabled = true;
  btn.textContent = "Gerando...";
  try {
    const res = await api().share_file(storage_path, name, 24);
    if (!res.ok) { showToast(res.error || "Erro ao gerar link.", "error"); return; }
    await navigator.clipboard.writeText(res.url);
    showToast("Link copiado! Válido por 24 horas.", "ok");
  } catch(e) {
    showToast("Erro ao copiar link.", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Copiar link";
  }
}

// ── Lixeira ───────────────────────────────────────────────────────────────────
async function loadTrashView() {
  showView("trashView");
  setActiveNav("navTrash");
  document.getElementById("trashList").innerHTML = '<p class="flat-empty">Carregando...</p>';
  const items = await api().get_trash();
  const el = document.getElementById("trashList");
  if (!items.length) {
    el.innerHTML = '<p class="flat-empty">A lixeira está vazia.</p>';
    return;
  }
  el.innerHTML = items.map(item => {
    const icon = item.type === "folder"
      ? `<svg viewBox="0 0 24 24" fill="#fbbf24" stroke="#d97706" stroke-width="1"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
    return `
      <div class="flat-item" data-path="${item.storage_path}">
        <div class="flat-item-icon">${icon}</div>
        <div class="flat-item-info">
          <div class="flat-item-name">${item.name}</div>
          <div class="flat-item-meta">Excluído em ${fmtDate(item.deleted_at)}</div>
        </div>
        <div class="flat-item-actions">
          <button onclick="restoreTrash('${item.storage_path}')">Restaurar</button>
        </div>
      </div>`;
  }).join("");
}

async function restoreTrash(storage_path) {
  await api().restore_from_trash(storage_path);
  showToast("Item restaurado.", "ok");
  await loadTrashView();
  await loadSidebar();
}

// ── Configurações ─────────────────────────────────────────────────────────────
let settingsState = { groups: [], editingUserId: null, editingGroupId: null };

async function loadSettingsView() {
  showView("settingsView");
  setActiveNav("navConfig");

  const perms = await api().get_permissions();
  const restricted = document.getElementById("settingsRestricted");
  const content     = document.getElementById("settingsContent");

  if (!perms.is_admin) {
    restricted.style.display = "";
    content.style.display    = "none";
    return;
  }
  restricted.style.display = "none";
  content.style.display    = "";

  switchSettingsTab("usuarios");
}

function switchSettingsTab(tab) {
  document.querySelectorAll(".settings-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  document.getElementById("paneUsuarios").style.display = tab === "usuarios" ? "" : "none";
  document.getElementById("paneGrupos").style.display   = tab === "grupos"   ? "" : "none";
  document.getElementById("paneEmpresa").style.display  = tab === "empresa"  ? "" : "none";

  if (tab === "usuarios") loadUsersTable();
  else if (tab === "grupos") loadGroupsTable();
  else if (tab === "empresa") loadEmpresaTab();
}

function initSettingsTabs() {
  document.querySelectorAll(".settings-tab").forEach(btn => {
    btn.addEventListener("click", () => switchSettingsTab(btn.dataset.tab));
  });
}

// ── Usuários ───────────────────────────────────────────────────────────────
async function loadUsersTable() {
  const tbody = document.getElementById("usersTableBody");
  tbody.innerHTML = `<tr><td colspan="4">Carregando...</td></tr>`;
  const [users, groups] = await Promise.all([api().get_users(), api().get_groups()]);
  settingsState.groups = groups;

  if (!users.length) {
    tbody.innerHTML = `<tr><td colspan="4">Nenhum usuário cadastrado.</td></tr>`;
    return;
  }
  const selfId = state.user?.id;
  tbody.innerHTML = users.map(u => `
    <tr>
      <td>${u.name}</td>
      <td>${u.email}</td>
      <td>${u.group_name || "Sem grupo"}</td>
      <td>
        <div class="row-actions">
          <button title="Editar" onclick="openUserModal('${u.id}')">✏️</button>
          <button title="Excluir" class="danger" ${u.id === selfId ? "disabled" : ""} onclick="deleteUserRow('${u.id}')">✕</button>
        </div>
      </td>
    </tr>`).join("");
}

async function openUserModal(userId = null) {
  if (!settingsState.groups.length) settingsState.groups = await api().get_groups();
  const groups = settingsState.groups;
  settingsState.editingUserId = userId;

  let editing = null;
  if (userId) {
    const users = await api().get_users();
    editing = users.find(u => u.id === userId) || null;
  }

  document.getElementById("userModalTitle").textContent = editing ? "Editar Usuário" : "Novo Usuário";
  document.getElementById("userNameInput").value  = editing?.name  || "";
  document.getElementById("userEmailInput").value = editing?.email || "";
  document.getElementById("userPasswordInput").value  = "";
  document.getElementById("userPassword2Input").value = "";
  document.getElementById("userPasswordGroup").style.display = editing ? "none" : "";
  document.getElementById("btnChangeUserPw").style.display   = editing ? "" : "none";
  document.getElementById("userModalError").textContent = "";

  const select = document.getElementById("userGroupSelect");
  select.innerHTML = groups.map(g => `<option value="${g.id}">${g.name}</option>`).join("");
  if (editing?.group_id) select.value = editing.group_id;

  document.getElementById("userModalOverlay").style.display = "flex";
}

function closeUserModal() {
  document.getElementById("userModalOverlay").style.display = "none";
  settingsState.editingUserId = null;
}

async function saveUserModal() {
  const name  = document.getElementById("userNameInput").value.trim();
  const email = document.getElementById("userEmailInput").value.trim();
  const groupId = document.getElementById("userGroupSelect").value;
  const errEl = document.getElementById("userModalError");

  if (!name || !email) { errEl.textContent = "Nome e e-mail são obrigatórios."; return; }
  if (!groupId) { errEl.textContent = "Selecione um grupo."; return; }

  const editingId = settingsState.editingUserId;
  let res;
  if (editingId) {
    res = await api().update_user(editingId, name, email, null, groupId);
  } else {
    const pwd  = document.getElementById("userPasswordInput").value;
    const pwd2 = document.getElementById("userPassword2Input").value;
    if (!pwd) { errEl.textContent = "Informe uma senha."; return; }
    if (pwd !== pwd2) { errEl.textContent = "As senhas não coincidem."; return; }
    res = await api().create_user(name, email, pwd, groupId);
  }

  if (!res.ok) { errEl.textContent = res.error || "Erro ao salvar usuário."; return; }
  closeUserModal();
  showToast(editingId ? "Usuário atualizado." : "Usuário criado.", "ok");
  await loadUsersTable();
}

async function deleteUserRow(userId) {
  const ok = await showConfirm("Deseja remover este usuário? Esta ação não pode ser desfeita.", { title: "Excluir usuário", okLabel: "Excluir" });
  if (!ok) return;
  const res = await api().delete_user(userId);
  if (!res.ok) { showToast(res.error || "Erro ao excluir usuário.", "error"); return; }
  showToast("Usuário excluído.", "ok");
  await loadUsersTable();
}

function openUserPwModal() {
  document.getElementById("userPwNew1").value = "";
  document.getElementById("userPwNew2").value = "";
  document.getElementById("userPwModalError").textContent = "";
  document.getElementById("userPwModalOverlay").style.display = "flex";
}

function closeUserPwModal() {
  document.getElementById("userPwModalOverlay").style.display = "none";
}

async function saveUserPwModal() {
  const pwd  = document.getElementById("userPwNew1").value;
  const pwd2 = document.getElementById("userPwNew2").value;
  const errEl = document.getElementById("userPwModalError");
  if (!pwd) { errEl.textContent = "Informe a nova senha."; return; }
  if (pwd !== pwd2) { errEl.textContent = "As senhas não coincidem."; return; }

  const res = await api().update_user(settingsState.editingUserId, null, null, pwd, null);
  if (!res.ok) { errEl.textContent = res.error || "Erro ao alterar senha."; return; }
  closeUserPwModal();
  showToast("Senha alterada com sucesso.", "ok");
}

// ── Grupos ─────────────────────────────────────────────────────────────────
async function loadGroupsTable() {
  const tbody = document.getElementById("groupsTableBody");
  tbody.innerHTML = `<tr><td colspan="7">Carregando...</td></tr>`;
  const groups = await api().get_groups();
  settingsState.groups = groups;

  if (!groups.length) {
    tbody.innerHTML = `<tr><td colspan="7">Nenhum grupo cadastrado.</td></tr>`;
    return;
  }
  const flag = v => v ? `<span class="perm-yes">✓</span>` : `<span class="perm-no">—</span>`;
  tbody.innerHTML = groups.map(g => `
    <tr>
      <td><strong>${g.name}</strong></td>
      <td>${flag(g.can_view)}</td>
      <td>${flag(g.can_create)}</td>
      <td>${flag(g.can_edit)}</td>
      <td>${flag(g.can_delete)}</td>
      <td>${flag(g.is_admin)}</td>
      <td>
        <div class="row-actions">
          <button title="Editar" onclick="openGroupModal('${g.id}')">✏️</button>
          <button title="Excluir" class="danger" onclick="deleteGroupRow('${g.id}')">✕</button>
        </div>
      </td>
    </tr>`).join("");
}

async function openGroupModal(groupId = null) {
  settingsState.editingGroupId = groupId;
  let editing = null;
  if (groupId) {
    const groups = settingsState.groups.length ? settingsState.groups : await api().get_groups();
    editing = groups.find(g => g.id === groupId) || null;
  }

  document.getElementById("groupModalTitle").textContent = editing ? "Editar Grupo" : "Novo Grupo";
  document.getElementById("groupNameInput").value = editing?.name || "";
  document.getElementById("permCanView").checked   = !!editing?.can_view;
  document.getElementById("permCanCreate").checked = !!editing?.can_create;
  document.getElementById("permCanEdit").checked   = !!editing?.can_edit;
  document.getElementById("permCanDelete").checked = !!editing?.can_delete;
  document.getElementById("permIsAdmin").checked   = !!editing?.is_admin;
  document.getElementById("groupModalError").textContent = "";

  document.getElementById("groupModalOverlay").style.display = "flex";
}

function closeGroupModal() {
  document.getElementById("groupModalOverlay").style.display = "none";
  settingsState.editingGroupId = null;
}

async function saveGroupModal() {
  const name = document.getElementById("groupNameInput").value.trim();
  const errEl = document.getElementById("groupModalError");
  if (!name) { errEl.textContent = "Informe um nome para o grupo."; return; }

  const perms = {
    can_view:   document.getElementById("permCanView").checked,
    can_create: document.getElementById("permCanCreate").checked,
    can_edit:   document.getElementById("permCanEdit").checked,
    can_delete: document.getElementById("permCanDelete").checked,
    is_admin:   document.getElementById("permIsAdmin").checked,
  };

  const editingId = settingsState.editingGroupId;
  const res = editingId
    ? await api().update_group(editingId, name, perms.can_view, perms.can_create, perms.can_edit, perms.can_delete, perms.is_admin)
    : await api().create_group(name, perms.can_view, perms.can_create, perms.can_edit, perms.can_delete, perms.is_admin);

  if (!res.ok) { errEl.textContent = res.error || "Erro ao salvar grupo."; return; }
  closeGroupModal();
  showToast(editingId ? "Grupo atualizado." : "Grupo criado.", "ok");
  await loadGroupsTable();
}

async function deleteGroupRow(groupId) {
  const ok = await showConfirm("Deseja remover este grupo? Os usuários deste grupo ficarão sem grupo.", { title: "Excluir grupo", okLabel: "Excluir" });
  if (!ok) return;
  const res = await api().delete_group(groupId);
  if (!res.ok) { showToast(res.error || "Erro ao excluir grupo.", "error"); return; }
  showToast("Grupo excluído.", "ok");
  await loadGroupsTable();
}

// ── Empresa ──────────────────────────────────────────────────────────────────
async function loadEmpresaTab() {
  const info = await api().get_tenant_info();
  document.getElementById("companyNameInput").value = info.name || "";
  document.getElementById("companyError").textContent = "";
  await refreshLogoPreview();
}

async function refreshLogoPreview() {
  const img  = document.getElementById("logoPreviewImg");
  const icon = document.getElementById("logoPreviewIcon");
  const msg  = document.getElementById("logoPreviewMsg");
  try {
    const url = await api().get_tenant_logo_url();
    if (url) {
      img.src = url;
      img.style.display  = "";
      icon.style.display = "none";
      msg.textContent = "Logo cadastrada.";
    } else {
      img.style.display  = "none";
      icon.style.display = "";
      msg.textContent = "Nenhuma logo cadastrada.";
    }
  } catch (e) {
    img.style.display  = "none";
    icon.style.display = "";
    msg.textContent = "Nenhuma logo cadastrada.";
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function initEmpresaTab() {
  const fileInput = document.getElementById("logoFileInput");

  document.getElementById("btnChooseLogo")?.addEventListener("click", () => fileInput.click());

  fileInput?.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    const errEl = document.getElementById("companyError");
    errEl.textContent = "";
    try {
      const b64 = await fileToBase64(file);
      const res = await api().upload_tenant_logo(file.name, b64);
      if (!res.ok) { showToast(res.error || "Erro ao enviar logo.", "error"); return; }
      showToast("Logo atualizada.", "ok");
      await refreshLogoPreview();
      await applySidebarLogo();
    } catch (e) {
      showToast("Erro ao enviar logo.", "error");
    } finally {
      fileInput.value = "";
    }
  });

  document.getElementById("btnRemoveLogo")?.addEventListener("click", async () => {
    const ok = await showConfirm("Remover a logo da empresa?", { title: "Remover Logo", okLabel: "Remover" });
    if (!ok) return;
    const res = await api().remove_tenant_logo();
    if (!res.ok) { showToast(res.error || "Erro ao remover logo.", "error"); return; }
    showToast("Logo removida.", "ok");
    await refreshLogoPreview();
    await applySidebarLogo();
  });

  document.getElementById("btnSaveCompanyName")?.addEventListener("click", async () => {
    const name = document.getElementById("companyNameInput").value.trim();
    const errEl = document.getElementById("companyError");
    errEl.textContent = "";
    const res = await api().update_tenant_name(name);
    if (!res.ok) { errEl.textContent = res.error || "Erro ao salvar nome."; return; }
    showToast("Nome da empresa atualizado.", "ok");
  });
}

function initSettingsModals() {
  initSettingsTabs();
  initEmpresaTab();

  document.getElementById("btnNewUser")?.addEventListener("click", () => openUserModal());
  document.getElementById("userModalClose")?.addEventListener("click", closeUserModal);
  document.getElementById("userModalCancel")?.addEventListener("click", closeUserModal);
  document.getElementById("userModalSave")?.addEventListener("click", saveUserModal);
  document.getElementById("btnChangeUserPw")?.addEventListener("click", openUserPwModal);
  document.getElementById("userModalOverlay")?.addEventListener("click", e => {
    if (e.target.id === "userModalOverlay") closeUserModal();
  });

  document.getElementById("userPwModalClose")?.addEventListener("click", closeUserPwModal);
  document.getElementById("userPwModalCancel")?.addEventListener("click", closeUserPwModal);
  document.getElementById("userPwModalSave")?.addEventListener("click", saveUserPwModal);
  document.getElementById("userPwModalOverlay")?.addEventListener("click", e => {
    if (e.target.id === "userPwModalOverlay") closeUserPwModal();
  });

  document.getElementById("btnNewGroup")?.addEventListener("click", () => openGroupModal());
  document.getElementById("groupModalClose")?.addEventListener("click", closeGroupModal);
  document.getElementById("groupModalCancel")?.addEventListener("click", closeGroupModal);
  document.getElementById("groupModalSave")?.addEventListener("click", saveGroupModal);
  document.getElementById("groupModalOverlay")?.addEventListener("click", e => {
    if (e.target.id === "groupModalOverlay") closeGroupModal();
  });
}

// ── Botão Favoritar no painel de detalhes ─────────────────────────────────────
function initFavoriteBtn() {
  document.getElementById("detailFavBtn")?.addEventListener("click", async () => {
    if (!detailItem) return;
    const res = await api().toggle_favorite(detailItem.storage_path);
    const btn = document.getElementById("detailFavBtn");
    if (res.is_favorite) {
      btn.classList.add("active");
      btn.querySelector("svg").setAttribute("fill", "#f59e0b");
      showToast("Adicionado aos favoritos.", "ok");
    } else {
      btn.classList.remove("active");
      btn.querySelector("svg").setAttribute("fill", "none");
      showToast("Removido dos favoritos.", "ok");
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initActivation();
  initLogin();
  initChangePw();
  initSearch();
  initDetailTabs();
  initFavoriteBtn();
  initNewDropdown();
  initModal();
  initUpload();
  initShare();
  initNotifications();
  initUserMenu();
  initPlanModal();
  initSettingsModals();

  // nav clicks
  document.getElementById("navDocumentos")?.addEventListener("click", e => { e.preventDefault(); showHomeView(); });
  document.getElementById("navRecent")?.addEventListener("click", e => { e.preventDefault(); loadRecentView(); });
  document.getElementById("navFavorites")?.addEventListener("click", e => { e.preventDefault(); loadFavoritesView(); });
  document.getElementById("navShared")?.addEventListener("click", e => { e.preventDefault(); loadSharedView(); });
  document.getElementById("navTrash")?.addEventListener("click", e => { e.preventDefault(); loadTrashView(); });
  document.getElementById("navConfig")?.addEventListener("click", e => { e.preventDefault(); loadSettingsView(); });

  document.getElementById("emptyTrashBtn")?.addEventListener("click", async () => {
    const ok = await showConfirm("Todos os itens serão excluídos permanentemente do sistema.\nEsta ação não pode ser desfeita.", { title: "Esvaziar lixeira", okLabel: "Esvaziar" });
    if (!ok) return;
    await api().empty_trash();
    showToast("Lixeira esvaziada.", "ok");
    await loadTrashView();
  });

  // fechar painel clicando fora
  document.querySelector(".content").addEventListener("click", e => {
    if (!e.target.closest(".item-row") && !e.target.closest(".detail-panel")) {
      closeDetail();
      document.querySelectorAll(".item-row").forEach(r => r.classList.remove("selected"));
    }
  });

  // libera todas as travas desta sessão ao fechar a janela
  window.addEventListener("beforeunload", () => {
    try { api()?.unlock_all(); } catch {}
  });

  init();
});
