// ── Estado global ────────────────────────────────────────────────────────────
const state = {
  currentPath: null,   // storage_path da pasta aberta
  currentName: "",
  breadcrumb:  [],     // [{name, path}]
};

// ── Aguarda pywebview ────────────────────────────────────────────────────────
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
  await loadSession();
  await loadSidebar();
}

// ── Sessão ───────────────────────────────────────────────────────────────────
async function loadSession() {
  try {
    const s = await api().get_session();
    if (s.user?.name) {
      document.querySelectorAll(".user-name").forEach(el => el.textContent = s.user.name);
      document.querySelectorAll(".user-top").forEach(el => {
        const span = el.querySelector("span") || el;
        // mantém apenas o nome no topbar
      });
      // Iniciais do avatar
      const initials = s.user.name.split(" ").map(w => w[0]).slice(0,2).join("").toUpperCase();
      document.querySelectorAll(".user-avatar").forEach(el => el.textContent = initials);
      // Nome no topbar
      const topName = document.querySelector(".user-top");
      if (topName) {
        topName.childNodes.forEach(n => { if (n.nodeType === 3) n.textContent = " " + s.user.name + " "; });
      }
    }
  } catch(e) { console.warn("sem sessão:", e); }
}

// ── Sidebar — pastas raiz ────────────────────────────────────────────────────
async function loadSidebar() {
  const tree = document.getElementById("folderTree");
  tree.innerHTML = '<div class="folder-item loading">Carregando...</div>';
  try {
    const folders = await api().get_root_folders();
    tree.innerHTML = "";
    if (!folders.length) {
      tree.innerHTML = '<div class="folder-item muted">Nenhuma pasta</div>';
      return;
    }
    folders.forEach(f => {
      const el = document.createElement("div");
      el.className = "folder-item";
      el.dataset.path = f.storage_path;
      el.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <span>${f.name}</span>`;
      el.addEventListener("click", () => openFolder(f.storage_path, f.name, []));
      tree.appendChild(el);
    });
  } catch(e) {
    tree.innerHTML = '<div class="folder-item muted">Erro ao carregar</div>';
    console.error(e);
  }
}

// ── Abre pasta ───────────────────────────────────────────────────────────────
async function openFolder(path, name, parentCrumbs) {
  state.currentPath = path;
  state.currentName = name;
  state.breadcrumb  = [...parentCrumbs, { name, path }];

  // Marca ativo na sidebar
  document.querySelectorAll(".folder-item").forEach(el => {
    el.classList.toggle("active", el.dataset.path === path);
  });

  updateBreadcrumb();
  updateFolderTitle(name);
  await loadGrid(path);
  await loadStats(path);
}

// ── Breadcrumb ───────────────────────────────────────────────────────────────
function updateBreadcrumb() {
  const bc = document.querySelector(".breadcrumb");
  const crumbs = [{ name: "Início", path: null }, ...state.breadcrumb];
  bc.innerHTML = crumbs.map((c, i) => {
    const isLast = i === crumbs.length - 1;
    if (isLast) return `<strong>${c.name}</strong>`;
    return `<a href="#" data-path="${c.path}" data-name="${c.name}">${c.name}</a><span class="sep">›</span>`;
  }).join("");

  bc.querySelectorAll("a[data-path]").forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      const idx = state.breadcrumb.findIndex(c => c.path === a.dataset.path);
      const parent = idx > 0 ? state.breadcrumb.slice(0, idx) : [];
      openFolder(a.dataset.path, a.dataset.name, parent);
    });
  });
}

function updateFolderTitle(name) {
  const h1 = document.querySelector(".folder-name");
  if (h1) h1.textContent = name;
}

// ── Grid de arquivos/pastas ───────────────────────────────────────────────────
async function loadGrid(path) {
  const tbody = document.getElementById("fileList");
  tbody.innerHTML = '<tr><td colspan="5" class="loading-cell">Carregando...</td></tr>';
  try {
    const items = await api().get_children(path);
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">Pasta vazia</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(item => {
      const icon = item.type === "folder"
        ? `<div class="folder-icon-sm"></div>`
        : `<div class="file-icon-sm ${fileExt(item.name)}"></div>`;
      const size = item.type === "folder" ? "—" : (item.size || "—");
      const date = item.updated_at ? fmtDate(item.updated_at) : "—";
      return `
        <tr class="item-row" data-type="${item.type}" data-path="${item.storage_path}" data-name="${item.name}">
          <td class="name-cell">${icon} ${item.name}</td>
          <td>${item.type === "folder" ? "Pasta" : extLabel(item.name)}</td>
          <td>${size}</td>
          <td>${date}</td>
          <td><button class="btn-more">⋮</button></td>
        </tr>`;
    }).join("");

    // Clique em pasta → navega
    tbody.querySelectorAll(".item-row[data-type='folder']").forEach(row => {
      row.addEventListener("dblclick", () => {
        openFolder(row.dataset.path, row.dataset.name, state.breadcrumb);
      });
      row.addEventListener("click", () => {
        tbody.querySelectorAll(".item-row").forEach(r => r.classList.remove("selected"));
        row.classList.add("selected");
      });
    });

    // Atualiza rodapé
    const footer = document.querySelector(".file-list-footer");
    if (footer) footer.textContent = `${items.length} ${items.length === 1 ? "item" : "itens"}`;

  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">Erro: ${e}</td></tr>`;
  }
}

// ── Stats cards ───────────────────────────────────────────────────────────────
async function loadStats(path) {
  try {
    const s = await api().get_folder_stats(path);
    setStatVal(0, s.file_count   ?? "—");
    setStatVal(1, s.folder_count ?? "—");
    setStatVal(2, s.total_size   ?? "—");
  } catch(e) { /* silencioso */ }
}
function setStatVal(idx, val) {
  const cards = document.querySelectorAll(".stat-value");
  if (cards[idx]) cards[idx].textContent = val;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fileExt(name) {
  const ext = name.split(".").pop().toLowerCase();
  const map = { pdf: "pdf", txt: "txt", doc: "doc", docx: "doc",
                png: "img", jpg: "img", jpeg: "img", xlsx: "xls", xls: "xls" };
  return map[ext] || "generic";
}
function extLabel(name) {
  const ext = name.split(".").pop().toUpperCase();
  return ext || "Arquivo";
}
function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit"
    });
  } catch { return iso; }
}

// ── Search ────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.querySelector(".search-box input");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.toLowerCase();
      document.querySelectorAll(".item-row").forEach(row => {
        row.style.display = row.dataset.name.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }
  init();
});
