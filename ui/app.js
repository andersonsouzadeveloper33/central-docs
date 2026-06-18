// ── Estado global ────────────────────────────────────────────────────────────
const state = {
  currentPath: null,
  currentName: "",
  breadcrumb:  [],
  expanded:    new Set(),   // paths de pastas expandidas na sidebar
};

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
  await loadSession();
  await loadSidebar();
}

// ── Sessão ───────────────────────────────────────────────────────────────────
async function loadSession() {
  try {
    const s = await api().get_session();
    if (!s.user?.name) return;
    const initials = s.user.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
    document.querySelectorAll(".user-avatar").forEach(el => el.textContent = initials);
    document.querySelectorAll(".user-name").forEach(el => el.textContent = s.user.name);
  } catch(e) { console.warn("sem sessão:", e); }
}

// ── Sidebar ──────────────────────────────────────────────────────────────────
async function loadSidebar() {
  const tree = document.getElementById("folderTree");
  tree.innerHTML = '<div class="tree-loading">Carregando...</div>';
  try {
    const folders = await api().get_root_folders();
    tree.innerHTML = "";
    if (!folders.length) {
      tree.innerHTML = '<div class="tree-empty">Nenhuma pasta</div>';
      return;
    }
    folders.forEach(f => tree.appendChild(buildTreeNode(f, 0)));
  } catch(e) {
    tree.innerHTML = `<div class="tree-empty">Erro ao carregar</div>`;
    console.error(e);
  }
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
  // remove seleção anterior
  document.querySelectorAll(".tree-row.active").forEach(r => r.classList.remove("active"));
  wrap.querySelector(".tree-row").classList.add("active");

  const crumbs = buildCrumbs(folder.storage_path, folder.name);
  state.currentPath = folder.storage_path;
  state.currentName = folder.name;
  state.breadcrumb  = crumbs;

  updateBreadcrumb();
  updateFolderTitle(folder.name);
  await loadGrid(folder.storage_path);
  await loadStats(folder.storage_path);
}

// monta breadcrumb a partir do storage_path (ex: "projetos/zelar")
function buildCrumbs(storagePath, name) {
  const parts = storagePath.split("/").filter(Boolean);
  // usa o nome real só no último nível — os intermediários usam o próprio segmento
  return parts.map((seg, i) => ({
    name: i === parts.length - 1 ? name : seg,
    path: parts.slice(0, i + 1).join("/"),
  }));
}

// ── Breadcrumb ───────────────────────────────────────────────────────────────
function updateBreadcrumb() {
  const bc     = document.querySelector(".breadcrumb");
  const crumbs = [{ name: "Início", path: null }, ...state.breadcrumb];
  bc.innerHTML  = crumbs.map((c, i) => {
    const isLast = i === crumbs.length - 1;
    if (isLast) return `<strong>${c.name}</strong>`;
    return `<a href="#" data-path="${c.path ?? ""}" data-name="${c.name}">${c.name}</a><span class="sep">›</span>`;
  }).join("");

  bc.querySelectorAll("a[data-path]").forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      // navega de volta — seleciona o nó da sidebar se existir
      const node = document.querySelector(`.tree-node[data-path="${a.dataset.path}"]`);
      if (node) {
        const folder = { storage_path: a.dataset.path, name: a.dataset.name };
        selectNode(node, folder);
      }
    });
  });
}

function updateFolderTitle(name) {
  const h1 = document.querySelector(".folder-name");
  if (h1) h1.textContent = name;
}

// ── Grid ─────────────────────────────────────────────────────────────────────
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
      row.addEventListener("click", () => {
        tbody.querySelectorAll(".item-row").forEach(r => r.classList.remove("selected"));
        row.classList.add("selected");
        if (item) openDetail(item);
      });

      // duplo clique em pasta → navega
      if (row.dataset.type === "folder") {
        row.addEventListener("dblclick", async () => {
          const folder = { storage_path: row.dataset.path, name: row.dataset.name };
          let node = document.querySelector(`.tree-node[data-path="${row.dataset.path}"]`);
          if (!node) {
            node = document.createElement("div");
            node.dataset.path = row.dataset.path;
            node.appendChild(document.createElement("div")).className = "tree-row";
          }
          closeDetail();
          await selectNode(node, folder);
        });
      }
    });

    const footer = document.querySelector(".file-list-footer");
    if (footer) footer.textContent = `${items.length} ${items.length === 1 ? "item" : "itens"}`;
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">Erro: ${e}</td></tr>`;
  }
}

// ── Stats ─────────────────────────────────────────────────────────────────────
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
  document.getElementById("dLocation").textContent  = item.storage_path.split("/").slice(0, -1).join(" / ") || "Raiz";
  document.getElementById("dSize").textContent      = item.type === "folder" ? "—" : (item.size || "—");
  document.getElementById("dCreated").textContent   = item.updated_at ? fmtDate(item.updated_at) : "—";
  document.getElementById("dModified").textContent  = item.updated_at ? fmtDate(item.updated_at) : "—";
}

function closeDetail() {
  detailItem = null;
  document.getElementById("detailPanel").classList.remove("open");
}

function initDetailTabs() {
  document.querySelectorAll(".detail-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".detail-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
    });
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

document.addEventListener("DOMContentLoaded", () => {
  initSearch();
  initDetailTabs();

  // fechar painel clicando fora
  document.querySelector(".content").addEventListener("click", e => {
    if (!e.target.closest(".item-row") && !e.target.closest(".detail-panel")) {
      closeDetail();
      document.querySelectorAll(".item-row").forEach(r => r.classList.remove("selected"));
    }
  });

  init();
});
