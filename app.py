import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ══════════════════════════════════════════════════════════════════════════════
# STORAGE — camada de abstração para cloud (Supabase / Cloudflare R2)
#
# Quando for conectar de verdade, implemente as funções marcadas com TODO
# e aponte STORAGE_PROVIDER para o provedor escolhido.
# O restante do app consome apenas as funções db_* e storage_* abaixo.
# ══════════════════════════════════════════════════════════════════════════════

STORAGE_PROVIDER = "mock"   # trocar para "supabase" ou "cloudflare" quando pronto
STORAGE_BUCKET   = "centraldocs"


def storage_upload(storage_path: str, local_path: str) -> str:
    """
    Faz upload de um arquivo local para o storage.
    Retorna a URL pública ou o storage_path confirmado.

    TODO (Cloudflare R2):
        import boto3
        s3 = boto3.client("s3", endpoint_url=CF_ENDPOINT,
                          aws_access_key_id=CF_KEY, aws_secret_access_key=CF_SECRET)
        s3.upload_file(local_path, STORAGE_BUCKET, storage_path)
        return storage_path

    TODO (Supabase):
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        with open(local_path, "rb") as f:
            sb.storage.from_(STORAGE_BUCKET).upload(storage_path, f)
        return sb.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
    """
    return storage_path   # mock: devolve o próprio caminho


def storage_delete(storage_path: str):
    """
    Remove um arquivo/pasta do storage.

    TODO (Cloudflare R2):
        s3.delete_object(Bucket=STORAGE_BUCKET, Key=storage_path)

    TODO (Supabase):
        sb.storage.from_(STORAGE_BUCKET).remove([storage_path])
    """
    pass   # mock: não faz nada


def storage_list(storage_path: str) -> list[dict]:
    """
    Lista objetos dentro de um caminho no storage.
    Retorna lista de {"name": str, "storage_path": str, "is_folder": bool, "size": int}

    TODO (Cloudflare R2):
        resp = s3.list_objects_v2(Bucket=STORAGE_BUCKET, Prefix=storage_path, Delimiter="/")
        folders = [{"name": p["Prefix"].rstrip("/").split("/")[-1],
                    "storage_path": p["Prefix"], "is_folder": True, "size": 0}
                   for p in resp.get("CommonPrefixes", [])]
        files   = [{"name": o["Key"].split("/")[-1],
                    "storage_path": o["Key"], "is_folder": False, "size": o["Size"]}
                   for o in resp.get("Contents", []) if not o["Key"].endswith("/")]
        return folders + files

    TODO (Supabase):
        items = sb.storage.from_(STORAGE_BUCKET).list(storage_path)
        return [{"name": i["name"], "storage_path": f"{storage_path}/{i['name']}",
                 "is_folder": i["metadata"] is None, "size": i.get("metadata", {}).get("size", 0)}
                for i in items]
    """
    return []   # mock: pasta vazia no cloud


# ══════════════════════════════════════════════════════════════════════════════
# BANCO DE DADOS — registros de pastas/arquivos
#
# Estrutura do registro:
#   id           : int   — identificador único
#   name         : str   — nome legível
#   storage_path : str   — caminho dentro do bucket  ex: "documentos/orcamentos/"
#   provider     : str   — "cloudflare" | "supabase" | "mock"
#   type         : str   — "folder" | "file"
# ══════════════════════════════════════════════════════════════════════════════

MOCK_DB: list[dict] = []


def _next_id() -> int:
    return max((r["id"] for r in MOCK_DB), default=0) + 1


def _make_storage_path(parent_path: str, name: str, is_folder: bool) -> str:
    """Monta o storage_path no estilo bucket: 'pasta/subpasta/nome/'"""
    base = parent_path.rstrip("/")
    slug = name.lower().replace(" ", "-")
    return f"{base}/{slug}/" if is_folder else f"{base}/{slug}"


def db_create_folder(name: str, parent_path: str = "") -> dict:
    storage_path = _make_storage_path(parent_path, name, is_folder=True)
    record = {
        "id":           _next_id(),
        "name":         name,
        "storage_path": storage_path,
        "provider":     STORAGE_PROVIDER,
        "type":         "folder",
    }
    MOCK_DB.append(record)
    return record


def db_create_file(name: str, parent_path: str) -> dict:
    storage_path = _make_storage_path(parent_path, name, is_folder=False)
    record = {
        "id":           _next_id(),
        "name":         name,
        "storage_path": storage_path,
        "provider":     STORAGE_PROVIDER,
        "type":         "file",
    }
    MOCK_DB.append(record)
    return record


def db_list_folders() -> list[dict]:
    return [r for r in MOCK_DB if r["type"] == "folder"]


def db_list_children(parent_path: str) -> list[dict]:
    """Retorna registros cujo storage_path é filho direto de parent_path."""
    prefix = parent_path.rstrip("/") + "/"
    result = []
    for r in MOCK_DB:
        sp = r["storage_path"]
        if not sp.startswith(prefix):
            continue
        rest = sp[len(prefix):].rstrip("/")
        if rest and "/" not in rest:   # filho direto
            result.append(r)
    return result


def db_delete(record_id: int):
    global MOCK_DB
    rec = next((r for r in MOCK_DB if r["id"] == record_id), None)
    if rec:
        # remove o registro e todos os filhos (subpastas/arquivos)
        prefix = rec["storage_path"]
        MOCK_DB = [r for r in MOCK_DB
                   if r["id"] != record_id and not r["storage_path"].startswith(prefix)]
        storage_delete(rec["storage_path"])


# ── Modal: Nova Pasta ─────────────────────────────────────────────────────────
class NewFolderDialog(tk.Toplevel):
    def __init__(self, parent, parent_path: str = ""):
        super().__init__(parent)
        self.title("Nova Pasta")
        self.resizable(False, False)
        self.configure(bg="#F5F6FA")
        self.grab_set()
        self.result = None
        self._parent_path = parent_path

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"440x340+{pw - 220}+{ph - 170}")
        self._build()

    def _build(self):
        header = tk.Frame(self, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="  Nova Pasta", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=12)

        body = tk.Frame(self, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        tk.Label(body, text="Nome da pasta", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w")
        self._name_var = tk.StringVar()
        e = tk.Entry(body, textvariable=self._name_var, font=("Segoe UI", 11),
                     relief="flat", bg="#FFFFFF", fg="#1E2A3A", insertbackground="#1E2A3A",
                     highlightthickness=1, highlightbackground="#D0D7E2", highlightcolor="#4A90E2")
        e.pack(fill="x", ipady=7, pady=(4, 6))
        e.focus_set()
        e.bind("<KeyRelease>", self._update_preview)

        # Preview do caminho no storage
        tk.Label(body, text="Caminho no storage", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
        self._preview_var = tk.StringVar(value=self._storage_preview(""))
        tk.Label(body, textvariable=self._preview_var, bg="#1E2A3A", fg="#7ECB9F",
                 font=("Courier New", 9), anchor="w", padx=10, pady=6).pack(fill="x", pady=(4, 0))

        tk.Label(body, text=f"Provedor: {STORAGE_PROVIDER}   Bucket: {STORAGE_BUCKET}",
                 bg="#F5F6FA", fg="#9AAEC1", font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))

        btn_row = tk.Frame(self, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=24, pady=(0, 20))
        tk.Button(btn_row, text="Cancelar", bg="#E8EDF4", fg="#1E2A3A", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2", activebackground="#D0D7E2",
                  padx=16, pady=6, command=self.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btn_row, text="Criar Pasta", bg="#4A90E2", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#357ABD", activeforeground="#FFFFFF",
                  padx=16, pady=6, command=self._confirm).pack(side="right")

        self.bind("<Return>", lambda _: self._confirm())
        self.bind("<Escape>", lambda _: self.destroy())

    def _storage_preview(self, name: str) -> str:
        slug = name.lower().replace(" ", "-") if name else "<nome>"
        base = self._parent_path.rstrip("/")
        path = f"{base}/{slug}/" if base else f"{slug}/"
        return f"{STORAGE_BUCKET}  ›  {path}"

    def _update_preview(self, _=None):
        self._preview_var.set(self._storage_preview(self._name_var.get().strip()))

    def _confirm(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Atenção", "Informe um nome para a pasta.", parent=self)
            return
        self.result = {"name": name}
        self.destroy()


# ── Modal: Novo Arquivo ───────────────────────────────────────────────────────
FILE_TYPES = [
    ("📝", "Word",  ".docx", "#2B579A"),
    ("📊", "Excel", ".xlsx", "#217346"),
]
EXT_MAP = {label: ext for _, label, ext, _ in FILE_TYPES}


class NewFileDialog(tk.Toplevel):
    def __init__(self, parent, parent_storage_path: str):
        super().__init__(parent)
        self.title("Novo Arquivo")
        self.resizable(False, False)
        self.configure(bg="#F5F6FA")
        self.grab_set()
        self.result = None
        self._parent_storage_path = parent_storage_path
        self._selected_type = FILE_TYPES[0]   # (icon, label, ext, color)

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"500x340+{pw - 250}+{ph - 170}")
        self._build()

    def _build(self):
        header = tk.Frame(self, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="  Novo Arquivo", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=12)

        body = tk.Frame(self, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # Nome
        tk.Label(body, text="Nome do arquivo", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w")
        self._name_var = tk.StringVar()
        e = tk.Entry(body, textvariable=self._name_var, font=("Segoe UI", 11),
                     relief="flat", bg="#FFFFFF", fg="#1E2A3A", insertbackground="#1E2A3A",
                     highlightthickness=1, highlightbackground="#D0D7E2", highlightcolor="#4A90E2")
        e.pack(fill="x", ipady=7, pady=(4, 14))
        e.focus_set()
        e.bind("<KeyRelease>", self._update_preview)

        # Cards de tipo
        tk.Label(body, text="Tipo de arquivo", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))

        types_row = tk.Frame(body, bg="#F5F6FA")
        types_row.pack(fill="x", pady=(0, 14))

        self._type_cards = {}
        for ft in FILE_TYPES:
            icon, label, ext, color = ft
            card = tk.Frame(types_row, bg="#FFFFFF", cursor="hand2",
                            highlightthickness=2, highlightbackground="#E0E6EF",
                            width=72, height=72)
            card.pack(side="left", padx=(0, 8))
            card.pack_propagate(False)

            tk.Label(card, text=icon, bg="#FFFFFF", fg=color,
                     font=("Segoe UI", 20)).pack(pady=(8, 0))
            tk.Label(card, text=label, bg="#FFFFFF", fg="#1E2A3A",
                     font=("Segoe UI", 8)).pack()

            self._type_cards[label] = (card, color)
            for w in [card] + list(card.winfo_children()):
                w.bind("<Button-1>", lambda _, f=ft: self._select_type(f))

        # Marca o primeiro como selecionado
        self._select_type(FILE_TYPES[0], update_preview=False)


        btn_row = tk.Frame(self, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=24, pady=(0, 20))
        tk.Button(btn_row, text="Cancelar", bg="#E8EDF4", fg="#1E2A3A", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2", activebackground="#D0D7E2",
                  padx=16, pady=6, command=self.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btn_row, text="Criar Arquivo", bg="#27AE60", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#1E8449", activeforeground="#FFFFFF",
                  padx=16, pady=6, command=self._confirm).pack(side="right")

        self.bind("<Return>", lambda _: self._confirm())
        self.bind("<Escape>", lambda _: self.destroy())

    def _select_type(self, ft, update_preview=True):
        self._selected_type = ft
        _, sel_label, _, sel_color = ft
        for label, (card, color) in self._type_cards.items():
            if label == sel_label:
                card.config(highlightbackground=color, bg="#F8FAFF")
                for ch in card.winfo_children():
                    ch.config(bg="#F8FAFF")
            else:
                card.config(highlightbackground="#E0E6EF", bg="#FFFFFF")
                for ch in card.winfo_children():
                    ch.config(bg="#FFFFFF")
        if update_preview:
            self._update_preview()

    def _storage_preview(self, name: str) -> str:
        _, _, ext, _ = self._selected_type
        slug = name.lower().replace(" ", "-") if name else "<nome>"
        filename = f"{slug}{ext}"
        base = self._parent_storage_path.rstrip("/")
        return f"{STORAGE_BUCKET}  ›  {base}/{filename}"

    def _update_preview(self, _=None):
        self._preview_var.set(self._storage_preview(self._name_var.get().strip()))

    def _confirm(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Atenção", "Informe um nome para o arquivo.", parent=self)
            return
        _, _, ext, _ = self._selected_type
        filename = name if name.endswith(ext) else name + ext
        self.result = {"name": filename}
        self.destroy()


# ── Ícones por extensão ───────────────────────────────────────────────────────
EXT_ICONS = {
    ".txt":  ("📄", "#6B7A90"),
    ".docx": ("📝", "#2B579A"),
    ".doc":  ("📝", "#2B579A"),
    ".xlsx": ("📊", "#217346"),
    ".xls":  ("📊", "#217346"),
    ".pdf":  ("📕", "#E53935"),
    ".png":  ("🖼️", "#8E24AA"),
    ".jpg":  ("🖼️", "#8E24AA"),
    ".jpeg": ("🖼️", "#8E24AA"),
    ".zip":  ("🗜️", "#F57C00"),
    ".rar":  ("🗜️", "#F57C00"),
}


def file_icon(name: str):
    ext = os.path.splitext(name)[1].lower()
    return EXT_ICONS.get(ext, ("📄", "#6B7A90"))


# ── App principal ─────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CentralDocs")
        self.geometry("1240x720")
        self.state("zoomed")
        self.minsize(900, 540)
        self.configure(bg="#F5F6FA")
        self._root_path  = None
        self._current_path = None
        self._history: list[str] = []   # pilha de navegação
        self._search_after = None
        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    # UI principal
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── Sidebar ───────────────────────────────────────────────────────────
        self._sidebar = tk.Frame(self, bg="#1E2A3A", width=240)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        tk.Label(self._sidebar, text="CentralDocs", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 16, "bold"), pady=24).pack(fill="x", padx=20)
        tk.Frame(self._sidebar, bg="#2E3F52", height=1).pack(fill="x", padx=16, pady=4)

        nav_items = [
            ("  📄  Documentos",    "documentos"),
            ("  📊  Relatórios",    "relatorios"),
            ("  ⚙️  Configurações", "config"),
        ]
        self._nav_labels = {}
        for label, key in nav_items:
            lbl = tk.Label(self._sidebar, text=label,
                           bg="#1E2A3A", fg="#9AAEC1",
                           font=("Segoe UI", 11), anchor="w",
                           cursor="hand2", pady=10, padx=16)
            lbl.pack(fill="x", pady=2)
            lbl.bind("<Button-1>", lambda _, k=key: self._nav_go(k))
            self._nav_labels[key] = lbl

        tk.Frame(self._sidebar, bg="#2E3F52", height=1).pack(fill="x", padx=16, pady=(16, 4))

        folders_header = tk.Frame(self._sidebar, bg="#1E2A3A")
        folders_header.pack(fill="x", padx=16, pady=(4, 4))
        tk.Label(folders_header, text="MINHAS PASTAS", bg="#1E2A3A", fg="#6B8099",
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        add_lbl = tk.Label(folders_header, text="＋", bg="#1E2A3A", fg="#9AAEC1",
                           font=("Segoe UI", 13), cursor="hand2")
        add_lbl.pack(side="right")
        add_lbl.bind("<Button-1>", lambda _: self._open_new_folder_dialog())

        self._folders_list = tk.Frame(self._sidebar, bg="#1E2A3A")
        self._folders_list.pack(fill="x")

        # ── Main ──────────────────────────────────────────────────────────────
        main = tk.Frame(self, bg="#F5F6FA")
        main.pack(side="left", fill="both", expand=True)

        # Topbar
        topbar = tk.Frame(main, bg="#FFFFFF", height=56)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        self._topbar_title = tk.Label(topbar, text="Documentos", bg="#FFFFFF", fg="#1E2A3A",
                                      font=("Segoe UI", 14, "bold"))
        self._topbar_title.pack(side="left", padx=24, pady=14)
        tk.Label(topbar, text="Usuário  ▾", bg="#FFFFFF", fg="#1E2A3A",
                 font=("Segoe UI", 10), cursor="hand2").pack(side="right", padx=24)

        # Container de páginas
        self._pages_container = tk.Frame(main, bg="#F5F6FA")
        self._pages_container.pack(fill="both", expand=True)

        # ── Página: Documentos ────────────────────────────────────────────────
        self._page_documentos = tk.Frame(self._pages_container, bg="#F5F6FA")
        content = self._page_documentos
        content.pack(fill="both", expand=True, padx=28, pady=20)


        # Breadcrumb
        self._breadcrumb_frame = tk.Frame(content, bg="#F5F6FA")
        self._breadcrumb_frame.pack(fill="x", pady=(0, 8))

        # Search bar
        search_frame = tk.Frame(content, bg="#FFFFFF", highlightthickness=1,
                                highlightbackground="#D0D7E2")
        search_frame.pack(fill="x", pady=(0, 10))

        tk.Label(search_frame, text="🔍", bg="#FFFFFF", font=("Segoe UI", 11),
                 padx=8).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        tk.Entry(search_frame, textvariable=self._search_var, bg="#FFFFFF", fg="#1E2A3A",
                 relief="flat", font=("Segoe UI", 11),
                 insertbackground="#1E2A3A").pack(side="left", fill="x", expand=True, ipady=7)
        clr = tk.Label(search_frame, text="✕", bg="#FFFFFF", fg="#9AAEC1",
                       font=("Segoe UI", 11), cursor="hand2", padx=10)
        clr.pack(side="right")
        clr.bind("<Button-1>", lambda _: self._search_var.set(""))

        self._result_var = tk.StringVar(value="")
        tk.Label(content, textvariable=self._result_var, bg="#F5F6FA",
                 fg="#6B7A90", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))

        # Barra de ações — Nova Pasta / Novo Arquivo
        self._action_bar = tk.Frame(content, bg="#F5F6FA")
        self._action_bar.pack(fill="x", pady=(0, 10))

        # Área de cards com scroll
        wrapper = tk.Frame(content, bg="#F5F6FA")
        wrapper.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Thin.Vertical.TScrollbar", troughcolor="#F5F6FA",
                        background="#C8D0DC", borderwidth=0, arrowsize=0)

        canvas = tk.Canvas(wrapper, bg="#F5F6FA", highlightthickness=0)
        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview,
                            style="Thin.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._cards_frame = tk.Frame(canvas, bg="#F5F6FA")
        self._canvas_window = canvas.create_window((0, 0), window=self._cards_frame, anchor="nw")

        self._cards_frame.bind("<Configure>",
                               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", self._on_canvas_resize)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._canvas = canvas
        self._canvas_width = 0

        # Tela inicial
        self._nav_go("documentos")

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)
        # Re-renderiza o grid se a largura mudou o suficiente para alterar colunas
        new_cols = self._calc_cols(event.width)
        if new_cols != self._calc_cols(self._canvas_width):
            self._canvas_width = event.width
            if self._current_path:
                self._render_cards(self._current_path)
            else:
                self._show_home()
        else:
            self._canvas_width = event.width

    def _calc_cols(self, width: int = 0) -> int:
        w = width or self._canvas_width or self._canvas.winfo_width()
        card_w = 176  # 160 card + 16 padx
        return max(1, w // card_w)

    # ══════════════════════════════════════════════════════════════════════════
    # Navegação entre módulos
    # ══════════════════════════════════════════════════════════════════════════
    def _nav_go(self, key: str, show_home: bool = True):
        titles = {
            "documentos": "Documentos",
            "relatorios": "Relatórios",
            "config":     "Configurações",
        }
        # Atualiza destaque na sidebar
        for k, lbl in self._nav_labels.items():
            lbl.config(bg="#2E3F52" if k == key else "#1E2A3A",
                       fg="#FFFFFF" if k == key else "#9AAEC1")

        self._topbar_title.config(text=titles.get(key, key.capitalize()))

        # Esconde todas as páginas
        for frame in self._pages_container.winfo_children():
            frame.pack_forget()

        if key == "documentos":
            self._page_documentos.pack(fill="both", expand=True, padx=28, pady=20)
            if show_home:
                self._show_home()

    # ══════════════════════════════════════════════════════════════════════════
    # Navegação interna — Documentos
    # ══════════════════════════════════════════════════════════════════════════
    def _show_home(self):
        """Tela inicial — lista pastas do banco de dados."""
        self._current_path = None
        self._root_path = None
        self._history.clear()
        self._search_var.set("")
        self._result_var.set("")
        self._clear_cards()
        self._clear_breadcrumb()
        self._render_action_bar("home")

        folders = db_list_folders()

        if not folders:
            tk.Label(self._cards_frame, text="Nenhuma pasta cadastrada ainda.",
                     bg="#F5F6FA", fg="#C0C8D4", font=("Segoe UI", 12)).pack(pady=60)
            return

        tk.Label(self._cards_frame, text=f"{len(folders)} pasta(s) cadastrada(s)",
                 bg="#F5F6FA", fg="#6B7A90", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))

        COLS = self._calc_cols()
        row_frame = None
        for i, folder in enumerate(folders):
            if i % COLS == 0:
                row_frame = tk.Frame(self._cards_frame, bg="#F5F6FA")
                row_frame.pack(fill="x", pady=4)
            self._make_home_folder_card(row_frame, folder)

    def _render_action_bar(self, mode: str):
        """mode: 'home' mostra só Nova Pasta; 'folder' mostra ambos."""
        for w in self._action_bar.winfo_children():
            w.destroy()

        self._make_add_card(self._action_bar, "📁", "Nova Pasta", "#4A90E2",
                            self._open_new_folder_dialog)
        if mode == "folder":
            self._make_add_card(self._action_bar, "📄", "Novo Arquivo", "#27AE60",
                                self._open_new_file_dialog)

    def _clear_breadcrumb(self):
        for w in self._breadcrumb_frame.winfo_children():
            w.destroy()
        # Mostra só o link "Início"
        tk.Label(self._breadcrumb_frame, text="Início", bg="#F5F6FA",
                 fg="#1E2A3A", font=("Segoe UI", 10, "bold")).pack(side="left")

    def _make_add_card(self, parent, icon: str, label: str, color: str, cmd):
        card = tk.Frame(parent, bg="#FFFFFF", cursor="hand2",
                        highlightthickness=2, highlightbackground="#E0E6EF",
                        width=160, height=130)
        card.pack(side="left", padx=6, pady=2)
        card.pack_propagate(False)

        tk.Label(card, text=icon, bg="#FFFFFF", fg=color,
                 font=("Segoe UI", 28)).pack(pady=(14, 2))
        tk.Label(card, text=f"+ {label}", bg="#FFFFFF", fg=color,
                 font=("Segoe UI", 9, "bold")).pack()

        def on_enter(_):
            card.config(highlightbackground=color, bg="#F8FAFF")
            for w in card.winfo_children():
                try: w.config(bg="#F8FAFF")
                except Exception: pass

        def on_leave(_):
            card.config(highlightbackground="#E0E6EF", bg="#FFFFFF")
            for w in card.winfo_children():
                try: w.config(bg="#FFFFFF")
                except Exception: pass

        for w in [card] + list(card.winfo_children()):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda _: cmd())

    def _make_home_folder_card(self, parent, folder: dict):
        card = tk.Frame(parent, bg="#FFFFFF", cursor="hand2",
                        highlightthickness=1, highlightbackground="#E0E6EF",
                        width=160, height=130)
        card.pack(side="left", padx=6, pady=2)
        card.pack_propagate(False)

        tk.Label(card, text="📁", bg="#FFFFFF", font=("Segoe UI", 30)).pack(pady=(14, 2))
        tk.Label(card, text=folder["name"], bg="#FFFFFF", fg="#1E2A3A",
                 font=("Segoe UI", 9, "bold"), wraplength=140, justify="center").pack()
        tk.Label(card, text=f"id: {folder['id']}", bg="#FFFFFF", fg="#B0BEC5",
                 font=("Segoe UI", 8)).pack()

        # botão remover no canto superior direito
        del_btn = tk.Label(card, text="✕", bg="#FFFFFF", fg="#D0D7E2",
                           font=("Segoe UI", 9), cursor="hand2")
        del_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-4, y=4)
        del_btn.bind("<Button-1>", lambda _, fid=folder["id"]: self._remove_folder(fid))
        del_btn.bind("<Enter>", lambda _, w=del_btn: w.config(fg="#E53935"))
        del_btn.bind("<Leave>", lambda _, w=del_btn: w.config(fg="#D0D7E2"))

        sp = folder["storage_path"]

        def on_enter(_):
            card.config(highlightbackground="#4A90E2", bg="#F0F5FF")
            for w in card.winfo_children():
                try: w.config(bg="#F0F5FF")
                except Exception: pass

        def on_leave(_):
            card.config(highlightbackground="#E0E6EF", bg="#FFFFFF")
            for w in card.winfo_children():
                try: w.config(bg="#FFFFFF")
                except Exception: pass

        for w in [card] + list(card.winfo_children()):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda _, p=sp: self._enter_folder(p))

    def _enter_folder(self, storage_path: str):
        self._root_path = storage_path
        self._history.clear()
        self._navigate_to(storage_path)

    def _remove_folder(self, folder_id: int):
        if messagebox.askyesno("Remover", "Remover esta pasta do cadastro?\n(os arquivos no storage não serão apagados)"):
            db_delete(folder_id)
            self._refresh_sidebar()
            self._show_home()

    def _refresh_sidebar(self):
        for w in self._folders_list.winfo_children():
            w.destroy()
        # Mostra apenas pastas raiz — storage_path com um único nível (ex: "orcamentos/")
        root_folders = [
            f for f in db_list_folders()
            if f["storage_path"].strip("/").count("/") == 0
        ]
        for folder in root_folders:
            self._add_folder_to_sidebar(folder)

    def _navigate_to(self, path: str, push_history=True):
        if push_history and self._current_path and self._current_path != path:
            self._history.append(self._current_path)
        self._current_path = path
        self._search_var.set("")
        self._render_action_bar("folder")
        self._render_cards(path)
        self._render_breadcrumb(path)

    def _go_back(self):
        if self._history:
            path = self._history.pop()
            self._navigate_to(path, push_history=False)

    # ── Breadcrumb ────────────────────────────────────────────────────────────
    def _render_breadcrumb(self, path: str):
        for w in self._breadcrumb_frame.winfo_children():
            w.destroy()

        # Início — sempre volta para a home (listagem do banco)
        home_lbl = tk.Label(self._breadcrumb_frame, text="Início", bg="#F5F6FA",
                            fg="#4A90E2", font=("Segoe UI", 10), cursor="hand2")
        home_lbl.pack(side="left")
        home_lbl.bind("<Button-1>", lambda _: self._show_home())
        tk.Label(self._breadcrumb_frame, text="  /  ", bg="#F5F6FA",
                 fg="#B0BEC5", font=("Segoe UI", 10)).pack(side="left")

        # Botão voltar
        if self._history:
            back = tk.Label(self._breadcrumb_frame, text="← Voltar", bg="#F5F6FA",
                            fg="#4A90E2", font=("Segoe UI", 10), cursor="hand2")
            back.pack(side="left", padx=(0, 12))
            back.bind("<Button-1>", lambda _: self._go_back())

        # Partes do caminho
        # Monta breadcrumb a partir do storage_path
        # ex: "documentos/orcamentos/2024/" → ["documentos", "orcamentos", "2024"]
        parts = [p for p in path.strip("/").split("/") if p]
        accumulated = ""

        for i, part in enumerate(parts):
            accumulated = accumulated + part + "/"
            is_last = (i == len(parts) - 1)

            acc_copy = accumulated
            lbl = tk.Label(self._breadcrumb_frame, text=part, bg="#F5F6FA",
                           fg="#1E2A3A" if is_last else "#4A90E2",
                           font=("Segoe UI", 10, "bold" if is_last else "normal"),
                           cursor="arrow" if is_last else "hand2")
            lbl.pack(side="left")

            if not is_last:
                lbl.bind("<Button-1>", lambda _, p=acc_copy: self._navigate_to(p))
                tk.Label(self._breadcrumb_frame, text="  /  ", bg="#F5F6FA",
                         fg="#B0BEC5", font=("Segoe UI", 10)).pack(side="left")

    # ── Renderiza cards ───────────────────────────────────────────────────────
    def _clear_cards(self):
        for w in self._cards_frame.winfo_children():
            w.destroy()

    def _render_cards(self, storage_path: str):
        self._clear_cards()

        entries = db_list_children(storage_path)

        if not entries:
            tk.Label(self._cards_frame, text="Pasta vazia", bg="#F5F6FA",
                     fg="#C0C8D4", font=("Segoe UI", 12)).pack(pady=60)
            return

        entries_sorted = sorted(entries, key=lambda e: (e["type"] != "folder", e["name"].lower()))

        COLS = self._calc_cols()
        row_frame = None
        for i, rec in enumerate(entries_sorted):
            if i % COLS == 0:
                row_frame = tk.Frame(self._cards_frame, bg="#F5F6FA")
                row_frame.pack(fill="x", pady=4)
            if rec["type"] == "folder":
                self._make_folder_card(row_frame, rec)
            else:
                self._make_file_card(row_frame, rec)

    def _make_folder_card(self, parent, rec: dict):
        ACCENT = "#4A90E2"
        card = tk.Frame(parent, bg="#FFFFFF", cursor="hand2",
                        highlightthickness=1, highlightbackground="#E0E6EF",
                        width=160, height=130)
        card.pack(side="left", padx=8, pady=6)
        card.pack_propagate(False)

        # Barra colorida no topo
        tk.Frame(card, bg=ACCENT, height=3).pack(fill="x")

        body = tk.Frame(card, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        tk.Label(body, text="📁", bg="#FFFFFF", font=("Segoe UI", 30),
                 anchor="w").pack(anchor="w")
        tk.Label(body, text=rec["name"], bg="#FFFFFF", fg="#1E2A3A",
                 font=("Segoe UI", 10, "bold"), wraplength=136,
                 justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

        sp = rec["storage_path"]

        def _all_widgets():
            return [card, body] + list(body.winfo_children())

        def on_enter(_):
            card.config(highlightbackground=ACCENT, bg="#F0F5FF")
            body.config(bg="#F0F5FF")
            for w in body.winfo_children():
                try: w.config(bg="#F0F5FF")
                except Exception: pass

        def on_leave(_):
            card.config(highlightbackground="#E0E6EF", bg="#FFFFFF")
            body.config(bg="#FFFFFF")
            for w in body.winfo_children():
                try: w.config(bg="#FFFFFF")
                except Exception: pass

        for w in _all_widgets():
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda _, p=sp: self._navigate_to(p))

    def _make_file_card(self, parent, rec: dict):
        icon, color = file_icon(rec["name"])
        ext = os.path.splitext(rec["name"])[1].upper().lstrip(".") or "FILE"

        card = tk.Frame(parent, bg="#FFFFFF", cursor="hand2",
                        highlightthickness=1, highlightbackground="#E0E6EF",
                        width=160, height=130)
        card.pack(side="left", padx=8, pady=6)
        card.pack_propagate(False)

        # Barra colorida no topo
        tk.Frame(card, bg=color, height=3).pack(fill="x")

        body = tk.Frame(card, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        # Linha: ícone + badge de extensão
        top_row = tk.Frame(body, bg="#FFFFFF")
        top_row.pack(fill="x", anchor="w")
        tk.Label(top_row, text=icon, bg="#FFFFFF", fg=color,
                 font=("Segoe UI", 26)).pack(side="left")
        badge = tk.Label(top_row, text=ext, bg=color, fg="#FFFFFF",
                         font=("Segoe UI", 7, "bold"),
                         padx=4, pady=1)
        badge.pack(side="left", anchor="s", pady=(0, 4), padx=(4, 0))

        # Nome do arquivo
        name_no_ext = os.path.splitext(rec["name"])[0]
        tk.Label(body, text=name_no_ext, bg="#FFFFFF", fg="#1E2A3A",
                 font=("Segoe UI", 10, "bold"), wraplength=136,
                 justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

        sp = rec["storage_path"]

        def on_enter(_):
            card.config(highlightbackground=color, bg="#FAFAFA")
            body.config(bg="#FAFAFA")
            top_row.config(bg="#FAFAFA")
            for w in list(top_row.winfo_children()) + list(body.winfo_children()):
                if w is badge:
                    continue
                try: w.config(bg="#FAFAFA")
                except Exception: pass

        def on_leave(_):
            card.config(highlightbackground="#E0E6EF", bg="#FFFFFF")
            body.config(bg="#FFFFFF")
            top_row.config(bg="#FFFFFF")
            for w in list(top_row.winfo_children()) + list(body.winfo_children()):
                if w is badge:
                    continue
                try: w.config(bg="#FFFFFF")
                except Exception: pass

        def on_double(_sp=sp):
            messagebox.showinfo("Arquivo no Storage",
                                f"Caminho:\n{STORAGE_BUCKET}  ›  {_sp}\n\n"
                                f"(Download via {STORAGE_PROVIDER} será implementado aqui)")

        for w in [card, body, top_row] + list(top_row.winfo_children()) + list(body.winfo_children()):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Double-1>", lambda _e, p=sp: on_double(p))

    # ══════════════════════════════════════════════════════════════════════════
    # Ações
    # ══════════════════════════════════════════════════════════════════════════
    def _open_new_folder_dialog(self):
        parent_sp = self._current_path or ""
        dialog = NewFolderDialog(self, parent_path=parent_sp)
        self.wait_window(dialog)
        if dialog.result:
            foldername = dialog.result["name"]
            # Verifica duplicata no nível atual
            existentes = [r["name"].lower() for r in db_list_children(parent_sp)] if parent_sp \
                         else [f["name"].lower() for f in db_list_folders()]
            if foldername.lower() in existentes:
                messagebox.showwarning(
                    "Nome duplicado",
                    f'Já existe uma pasta chamada "{foldername}" neste local.\n'
                    "Escolha um nome diferente.",
                )
                return
            db_create_folder(foldername, parent_path=parent_sp)
            self._refresh_sidebar()
            if parent_sp:
                self._render_cards(parent_sp)
            else:
                self._show_home()

    def _add_folder_to_sidebar(self, folder: dict):
        row = tk.Frame(self._folders_list, bg="#1E2A3A", cursor="hand2")
        row.pack(fill="x")
        lbl = tk.Label(row, text=f"  📁  {folder['name']}", bg="#1E2A3A", fg="#C5D5E8",
                       font=("Segoe UI", 10), anchor="w", cursor="hand2", pady=7, padx=8)
        lbl.pack(fill="x")
        for w in (row, lbl):
            w.bind("<Button-1>", lambda _, p=folder["storage_path"]: self._select_root(p))
            w.bind("<Enter>",    lambda _, ww=lbl: ww.config(bg="#2E3F52"))
            w.bind("<Leave>",    lambda _, ww=lbl: ww.config(bg="#1E2A3A"))

    def _select_root(self, storage_path: str):
        self._root_path = storage_path
        self._history.clear()
        self._nav_go("documentos", show_home=False)
        self._navigate_to(storage_path)

    def _open_new_file_dialog(self):
        if not self._current_path:
            messagebox.showwarning("Atenção", "Abra uma pasta primeiro para criar um arquivo.")
            return
        dialog = NewFileDialog(self, parent_storage_path=self._current_path)
        self.wait_window(dialog)
        if dialog.result:
            filename = dialog.result["name"]
            # Verifica duplicata na pasta atual
            existentes = [r["name"].lower() for r in db_list_children(self._current_path)]
            if filename.lower() in existentes:
                messagebox.showwarning(
                    "Nome duplicado",
                    f'Já existe um arquivo chamado "{filename}" nesta pasta.\n'
                    "Escolha um nome diferente.",
                )
                return
            db_create_file(filename, parent_path=self._current_path)
            self._render_cards(self._current_path)

    def _choose_folder(self):
        pass  # não aplicável no modelo cloud

    # ── Busca ─────────────────────────────────────────────────────────────────
    def _on_search_change(self, *_):
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(300, self._run_search)

    def _run_search(self):
        query = self._search_var.get().strip().lower()
        if not self._root_path:
            return
        if not query:
            if self._current_path:
                self._render_cards(self._current_path)
                self._render_breadcrumb(self._current_path)
            self._result_var.set("")
            return

        self._clear_cards()
        matches = []
        # Busca em todos os registros do banco
        scope = self._root_path or ""
        matches = [
            r for r in MOCK_DB
            if query in r["name"].lower()
            and (not scope or r["storage_path"].startswith(scope))
        ]

        COLS = self._calc_cols()
        row_frame = None
        for i, rec in enumerate(matches):
            if i % COLS == 0:
                row_frame = tk.Frame(self._cards_frame, bg="#F5F6FA")
                row_frame.pack(fill="x", pady=4)
            if rec["type"] == "folder":
                self._make_folder_card(row_frame, rec)
            else:
                self._make_file_card(row_frame, rec)

        count = len(matches)
        self._result_var.set(
            f'Nenhum resultado para "{query}"' if count == 0 else
            "1 resultado encontrado" if count == 1 else
            f"{count} resultados encontrados"
        )

    @staticmethod
    def _fmt_size(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    # ══════════════════════════════════════════════════════════════════════════
    # Módulo Clientes
    # ══════════════════════════════════════════════════════════════════════════
    def _show_clientes(self):
        for w in self._page_clientes.winfo_children():
            w.destroy()

        # Toolbar clientes
        toolbar = tk.Frame(self._page_clientes, bg="#F5F6FA")
        toolbar.pack(fill="x", pady=(0, 12))

        tk.Label(toolbar, text=f"{len(cliente_list())} cliente(s) cadastrado(s)",
                 bg="#F5F6FA", fg="#6B7A90", font=("Segoe UI", 10)).pack(side="left")

        tk.Button(toolbar, text="  + Novo Cliente  ", bg="#4A90E2", fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#357ABD", activeforeground="#FFFFFF",
                  padx=8, pady=6, command=self._novo_cliente).pack(side="right")

        # Busca
        search_frame = tk.Frame(self._page_clientes, bg="#FFFFFF",
                                highlightthickness=1, highlightbackground="#D0D7E2")
        search_frame.pack(fill="x", pady=(0, 12))
        tk.Label(search_frame, text="🔍", bg="#FFFFFF", font=("Segoe UI", 11),
                 padx=8).pack(side="left")
        self._cli_search_var = tk.StringVar()
        self._cli_search_var.trace_add("write", lambda *_: self._filter_clientes())
        tk.Entry(search_frame, textvariable=self._cli_search_var, bg="#FFFFFF",
                 fg="#1E2A3A", relief="flat", font=("Segoe UI", 11),
                 insertbackground="#1E2A3A").pack(side="left", fill="x", expand=True, ipady=7)
        clr = tk.Label(search_frame, text="✕", bg="#FFFFFF", fg="#9AAEC1",
                       font=("Segoe UI", 11), cursor="hand2", padx=10)
        clr.pack(side="right")
        clr.bind("<Button-1>", lambda _: self._cli_search_var.set(""))

        # Tabela
        table_wrap = tk.Frame(self._page_clientes, bg="#FFFFFF",
                              highlightthickness=1, highlightbackground="#E0E6EF")
        table_wrap.pack(fill="both", expand=True)

        # Cabeçalho fixo
        head = tk.Frame(table_wrap, bg="#F5F6FA")
        head.pack(fill="x")
        for col, w, anchor in [("ID", 50, "e"), ("Nome", 220, "w"), ("E-mail", 220, "w"),
                                ("Telefone", 120, "w"), ("Empresa", 160, "w"), ("", 80, "center")]:
            tk.Label(head, text=col, bg="#F5F6FA", fg="#6B7A90",
                     font=("Segoe UI", 9, "bold"), width=0, anchor=anchor,
                     padx=12, pady=8).pack(side="left",
                                           fill="x" if w == 0 else None,
                                           expand=(w == 0),
                                           ipadx=0)
        tk.Frame(table_wrap, bg="#E0E6EF", height=1).pack(fill="x")

        # Scroll para as linhas
        vsb_frame = tk.Frame(table_wrap, bg="#FFFFFF")
        vsb_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(vsb_frame, bg="#FFFFFF", highlightthickness=0)
        vsb = ttk.Scrollbar(vsb_frame, orient="vertical", command=canvas.yview,
                            style="Thin.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._cli_rows_frame = tk.Frame(canvas, bg="#FFFFFF")
        win = canvas.create_window((0, 0), window=self._cli_rows_frame, anchor="nw")
        self._cli_rows_frame.bind("<Configure>",
                                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._render_clientes(cliente_list())

    def _render_clientes(self, clientes: list):
        for w in self._cli_rows_frame.winfo_children():
            w.destroy()

        if not clientes:
            tk.Label(self._cli_rows_frame, text="Nenhum cliente encontrado.",
                     bg="#FFFFFF", fg="#C0C8D4", font=("Segoe UI", 11)).pack(pady=40)
            return

        for i, c in enumerate(clientes):
            bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"
            row = tk.Frame(self._cli_rows_frame, bg=bg)
            row.pack(fill="x")

            for val, flex in [
                (str(c["id"]),       False),
                (c.get("nome",""),   False),
                (c.get("email",""),  False),
                (c.get("telefone",""), False),
                (c.get("empresa",""), False),
            ]:
                tk.Label(row, text=val, bg=bg, fg="#1E2A3A",
                         font=("Segoe UI", 10), anchor="w",
                         padx=12, pady=10).pack(side="left",
                                                fill="x" if flex else None,
                                                expand=flex)

            # Ações
            acts = tk.Frame(row, bg=bg)
            acts.pack(side="right", padx=8)
            tk.Button(acts, text="✏️", bg=bg, fg="#4A90E2", relief="flat",
                      font=("Segoe UI", 10), cursor="hand2",
                      activebackground="#E8F0FE", padx=4, pady=2,
                      command=lambda cid=c["id"]: self._editar_cliente(cid)).pack(side="left")
            tk.Button(acts, text="✕", bg=bg, fg="#E53935", relief="flat",
                      font=("Segoe UI", 10, "bold"), cursor="hand2",
                      activebackground="#FDECEA", padx=4, pady=2,
                      command=lambda cid=c["id"]: self._deletar_cliente(cid)).pack(side="left", padx=(4, 0))

            def _enter(_, w=row, b=bg):
                w.config(bg="#EEF4FF")
                for ch in w.winfo_children():
                    try: ch.config(bg="#EEF4FF")
                    except Exception: pass
            def _leave(_, w=row, b=bg):
                w.config(bg=b)
                for ch in w.winfo_children():
                    try: ch.config(bg=b)
                    except Exception: pass

            row.bind("<Enter>", _enter)
            row.bind("<Leave>", _leave)
            tk.Frame(self._cli_rows_frame, bg="#F0F2F5", height=1).pack(fill="x")

    def _filter_clientes(self):
        q = self._cli_search_var.get().strip().lower()
        todos = cliente_list()
        filtrados = [c for c in todos if not q or q in c.get("nome","").lower()
                     or q in c.get("email","").lower()
                     or q in c.get("empresa","").lower()] if q else todos
        self._render_clientes(filtrados)

    def _novo_cliente(self):
        dialog = ClienteDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            cliente_create(dialog.result)
            self._show_clientes()

    def _editar_cliente(self, cid: int):
        c = next((x for x in cliente_list() if x["id"] == cid), None)
        if not c:
            return
        dialog = ClienteDialog(self, cliente=c)
        self.wait_window(dialog)
        if dialog.result:
            cliente_update(cid, dialog.result)
            self._show_clientes()

    def _deletar_cliente(self, cid: int):
        if messagebox.askyesno("Remover", "Deseja remover este cliente?"):
            cliente_delete(cid)
            self._show_clientes()


if __name__ == "__main__":
    app = App()
    app.mainloop()
