import os
import uuid
import hashlib
import threading
import time
import ctypes
import ctypes.wintypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from supabase import create_client, Client
import boto3
from botocore.config import Config

# ID único desta instância do app (muda a cada execução)
SESSION_ID = str(uuid.uuid4())

# Usuário logado (preenchido após login bem-sucedido)
CURRENT_USER: dict = {}   # {"id": ..., "name": ..., "email": ...}

# ══════════════════════════════════════════════════════════════════════════════
# TENANT — configuração do cliente
# ══════════════════════════════════════════════════════════════════════════════
import json as _json

import sys as _sys

def _resource(filename: str) -> str:
    """Retorna o caminho correto tanto rodando via .py quanto via .exe (PyInstaller)."""
    if getattr(_sys, "frozen", False):
        # Executando como .exe — arquivos embutidos ficam em _MEIPASS
        base = _sys._MEIPASS
        path = os.path.join(base, filename)
        if os.path.exists(path):
            return path
    # Rodando via python ou arquivo ao lado do .exe
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = _resource("config.json")
_ICON_FILE   = _resource("icon.ico")

def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}

_config = _load_config()
TENANT_ID: str = _config.get("tenant_id", "")

if not TENANT_ID:
    import tkinter as _tk
    _tk.Tk().withdraw()
    import tkinter.messagebox as _mb
    _mb.showerror("Configuração ausente",
                  "Arquivo config.json não encontrado ou inválido.\n"
                  "Contate o suporte.")
    raise SystemExit(1)


# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE — banco de dados
# ══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = "https://ipstefusensfzjltdbwn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imlwc3RlZnVzZW5zZnpqbHRkYnduIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEwMjU4MDEsImV4cCI6MjA5NjYwMTgwMX0.QSghFta1Qa6_rkPlHY0XvohAm0q6S0FRK6Aao1PZFeY"

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ══════════════════════════════════════════════════════════════════════════════
# CLOUDFLARE R2 — storage de arquivos
# ══════════════════════════════════════════════════════════════════════════════

CF_ACCOUNT_ID  = "0527279a58ca34c6f7759899a64d07e3"
CF_ACCESS_KEY  = "7a3ac7882e63a79d2192d547e7b03f1d"
CF_SECRET_KEY  = "17f05bbe4c37afe9dfbb368fce4cf74af7e219ea65c5183607b6f241015e6656"
CF_BUCKET      = "centraldocs"
CF_ENDPOINT    = f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Pasta local onde os arquivos ficam espelhados (isolada por tenant)
LOCAL_STORAGE  = os.path.join(os.path.expanduser("~"), "Zynor Docs", TENANT_ID)
os.makedirs(LOCAL_STORAGE, exist_ok=True)
LAST_USER_FILE = os.path.join(LOCAL_STORAGE, ".last_user")

r2 = boto3.client(
    "s3",
    endpoint_url=CF_ENDPOINT,
    aws_access_key_id=CF_ACCESS_KEY,
    aws_secret_access_key=CF_SECRET_KEY,
    config=Config(signature_version="s3v4"),
)

STORAGE_PROVIDER = "cloudflare"
STORAGE_BUCKET   = CF_BUCKET


def _local_path(storage_path: str) -> str:
    """Retorna o caminho local equivalente ao storage_path."""
    return os.path.join(LOCAL_STORAGE, storage_path.lstrip("/").replace("/", os.sep))


def storage_upload(storage_path: str, local_path: str) -> str:
    """
    Copia o arquivo para a pasta local Zynor Docs e faz upload para o R2.
    Retorna o storage_path.
    """
    # 1. Copia para pasta local espelhada
    dest = _local_path(storage_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    import shutil
    shutil.copy2(local_path, dest)

    # 2. Upload para Cloudflare R2
    try:
        r2.upload_file(local_path, CF_BUCKET, storage_path)
    except Exception as e:
        print(f"[R2] Erro no upload: {e}")

    return storage_path


def storage_download(storage_path: str, force: bool = False) -> str:
    """
    Baixa do R2 apenas se o arquivo não existe localmente ou se o R2 tem
    versão mais recente. Retorna o caminho local.
    force=True sempre baixa do R2, sobrescrevendo o arquivo local.
    """
    dest = _local_path(storage_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        meta = r2.head_object(Bucket=CF_BUCKET, Key=storage_path)
        r2_mtime = meta["LastModified"].timestamp()
        # Só baixa se local não existe, R2 é mais recente, ou force=True
        if force or not os.path.exists(dest) or r2_mtime > os.path.getmtime(dest) + 5:
            try:
                r2.download_file(CF_BUCKET, storage_path, dest)
            except PermissionError:
                # Arquivo aberto por outro processo — usa a cópia local existente
                pass
    except Exception as e:
        print(f"[R2] Erro no download: {e}")
        if not os.path.exists(dest):
            return ""
    return dest


def storage_delete(storage_path: str):
    """Remove o arquivo local e do R2."""
    # Remove local
    local = _local_path(storage_path)
    if os.path.exists(local):
        try:
            os.remove(local)
        except Exception:
            pass
    # Remove do R2
    try:
        r2.delete_object(Bucket=CF_BUCKET, Key=storage_path)
    except Exception as e:
        print(f"[R2] Erro ao deletar: {e}")


def storage_list(storage_path: str) -> list[dict]:
    """Lista objetos dentro de um caminho no R2."""
    try:
        resp = r2.list_objects_v2(Bucket=CF_BUCKET, Prefix=storage_path, Delimiter="/")
        folders = [{"name": p["Prefix"].rstrip("/").split("/")[-1],
                    "storage_path": p["Prefix"], "is_folder": True, "size": 0}
                   for p in resp.get("CommonPrefixes", [])]
        files   = [{"name": o["Key"].split("/")[-1],
                    "storage_path": o["Key"], "is_folder": False, "size": o["Size"]}
                   for o in resp.get("Contents", []) if not o["Key"].endswith("/")]
        return folders + files
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# BANCO DE DADOS — Supabase (tabelas: folders, files)
# ══════════════════════════════════════════════════════════════════════════════

def _make_storage_path(parent_path: str, name: str, is_folder: bool) -> str:
    """Monta o storage_path prefixado com tenant_id para isolamento no R2."""
    slug = name.lower().replace(" ", "-")
    base = parent_path.strip("/")
    if base:
        return f"{base}/{slug}/" if is_folder else f"{base}/{slug}"
    else:
        # raiz do tenant
        return f"{TENANT_ID}/{slug}/" if is_folder else f"{TENANT_ID}/{slug}"


def db_create_folder(name: str, parent_path: str = "") -> dict:
    storage_path = _make_storage_path(parent_path, name, is_folder=True)
    res = sb.table("folders").insert({
        "name": name,
        "storage_path": storage_path,
        "parent_path": parent_path,
        "tenant_id": TENANT_ID,
    }).execute()
    row = res.data[0]
    return {"id": row["id"], "name": row["name"],
            "storage_path": row["storage_path"], "type": "folder"}


def db_create_file(name: str, parent_path: str) -> dict:
    storage_path = _make_storage_path(parent_path, name, is_folder=False)
    res = sb.table("files").insert({
        "name": name,
        "storage_path": storage_path,
        "parent_path": parent_path,
        "tenant_id": TENANT_ID,
    }).execute()
    row = res.data[0]
    return {"id": row["id"], "name": row["name"],
            "storage_path": row["storage_path"], "type": "file"}


def db_list_folders() -> list[dict]:
    res = sb.table("folders").select("*").eq("tenant_id", TENANT_ID).execute()
    return [{"id": r["id"], "name": r["name"],
             "storage_path": r["storage_path"],
             "parent_path": r.get("parent_path", ""),
             "type": "folder"}
            for r in res.data]


def db_list_children(parent_path: str) -> list[dict]:
    """Retorna pastas e arquivos filhos diretos de parent_path."""
    result = []
    folders = sb.table("folders").select("*").eq("tenant_id", TENANT_ID).eq("parent_path", parent_path).execute()
    for r in folders.data:
        result.append({"id": r["id"], "name": r["name"],
                       "storage_path": r["storage_path"], "type": "folder"})
    files = sb.table("files").select("*").eq("tenant_id", TENANT_ID).eq("parent_path", parent_path).execute()
    for r in files.data:
        result.append({"id": r["id"], "name": r["name"],
                       "storage_path": r["storage_path"], "type": "file"})
    return result


def db_list_all() -> list[dict]:
    """Retorna todos os registros do tenant (para busca global)."""
    result = []
    folders = sb.table("folders").select("*").eq("tenant_id", TENANT_ID).execute()
    for r in folders.data:
        result.append({"id": r["id"], "name": r["name"],
                       "storage_path": r["storage_path"], "type": "folder"})
    files = sb.table("files").select("*").eq("tenant_id", TENANT_ID).execute()
    for r in files.data:
        result.append({"id": r["id"], "name": r["name"],
                       "storage_path": r["storage_path"], "type": "file"})
    return result


def db_delete(record_id, record_type: str):
    """Remove uma pasta (e sub-itens) ou arquivo do banco."""
    if record_type == "folder":
        res = sb.table("folders").select("storage_path").eq("id", record_id).execute()
        if res.data:
            prefix = res.data[0]["storage_path"]
            all_files = sb.table("files").select("id, storage_path").eq("tenant_id", TENANT_ID).execute()
            for f in all_files.data:
                if f["storage_path"].startswith(prefix):
                    sb.table("files").delete().eq("id", f["id"]).execute()
                    storage_delete(f["storage_path"])
            all_folders = sb.table("folders").select("id, storage_path").eq("tenant_id", TENANT_ID).execute()
            for f in all_folders.data:
                if f["storage_path"].startswith(prefix) and f["id"] != record_id:
                    sb.table("folders").delete().eq("id", f["id"]).execute()
        sb.table("folders").delete().eq("id", record_id).execute()
    else:
        res = sb.table("files").select("storage_path").eq("id", record_id).execute()
        if res.data:
            storage_delete(res.data[0]["storage_path"])
        sb.table("files").delete().eq("id", record_id).execute()


# ══════════════════════════════════════════════════════════════════════════════
# GRUPOS E USUÁRIOS
# ══════════════════════════════════════════════════════════════════════════════

def group_list() -> list[dict]:
    res = sb.table("groups").select("*").eq("tenant_id", TENANT_ID).order("name").execute()
    return res.data

def group_create(name: str, can_view: bool, can_create: bool,
                 can_edit: bool, can_delete: bool, is_admin: bool) -> dict:
    res = sb.table("groups").insert({
        "name": name, "can_view": can_view, "can_create": can_create,
        "can_edit": can_edit, "can_delete": can_delete, "is_admin": is_admin,
        "tenant_id": TENANT_ID,
    }).execute()
    return res.data[0]

def group_update(group_id: str, name: str, can_view: bool, can_create: bool,
                 can_edit: bool, can_delete: bool, is_admin: bool):
    sb.table("groups").update({
        "name": name, "can_view": can_view, "can_create": can_create,
        "can_edit": can_edit, "can_delete": can_delete, "is_admin": is_admin,
    }).eq("id", group_id).eq("tenant_id", TENANT_ID).execute()

def group_delete(group_id: str):
    sb.table("groups").delete().eq("id", group_id).eq("tenant_id", TENANT_ID).execute()

def user_list() -> list[dict]:
    """Retorna usuários do tenant com nome do grupo."""
    users = sb.table("users").select("id, name, email, created_at").eq("tenant_id", TENANT_ID).order("name").execute()
    result = []
    for u in users.data:
        ug = sb.table("user_groups").select("group_id, groups(name)").eq("user_id", u["id"]).execute()
        group_name = ug.data[0]["groups"]["name"] if ug.data else "Sem grupo"
        group_id   = ug.data[0]["group_id"] if ug.data else None
        result.append({**u, "group_name": group_name, "group_id": group_id})
    return result

def user_create(name: str, email: str, password: str, group_id: str) -> dict:
    res = sb.table("users").insert({
        "name": name, "email": email,
        "password": _hash_password(password),
        "tenant_id": TENANT_ID,
    }).execute()
    user = res.data[0]
    sb.table("user_groups").insert({"user_id": user["id"], "group_id": group_id}).execute()
    return user

def user_update(user_id: str, name: str | None, email: str | None,
                password: str | None, group_id: str | None):
    data: dict = {}
    if name:    data["name"]  = name
    if email:   data["email"] = email
    if password: data["password"] = _hash_password(password)
    if data:
        sb.table("users").update(data).eq("id", user_id).execute()
    if group_id:
        sb.table("user_groups").delete().eq("user_id", user_id).execute()
        sb.table("user_groups").insert({"user_id": user_id, "group_id": group_id}).execute()

def user_delete(user_id: str):
    sb.table("users").delete().eq("id", user_id).execute()

def get_current_user_permissions() -> dict:
    """Retorna as permissões do usuário logado."""
    if not CURRENT_USER.get("id"):
        return {"can_view": True, "can_create": False,
                "can_edit": False, "can_delete": False, "is_admin": False}
    ug = sb.table("user_groups").select("group_id, groups(*)").eq("user_id", CURRENT_USER["id"]).execute()
    if ug.data:
        return ug.data[0]["groups"]
    return {"can_view": True, "can_create": False,
            "can_edit": False, "can_delete": False, "is_admin": False}


# ── Modal: Confirmação ───────────────────────────────────────────────────────
class InfoDialog(tk.Toplevel):
    """Diálogo informativo moderno com overlay escuro."""
    def __init__(self, parent, title: str, message: str, submessage: str = "",
                 icon: str = "⚠", icon_color: str = "#E67E22"):
        self._overlay = tk.Toplevel(parent)
        self._overlay.overrideredirect(True)
        self._overlay.configure(bg="#000000")
        self._overlay.attributes("-alpha", 0.45)
        self._overlay.geometry(
            f"{parent.winfo_width()}x{parent.winfo_height()}"
            f"+{parent.winfo_rootx()}+{parent.winfo_rooty()}"
        )
        self._overlay.lift()

        super().__init__(parent)
        self.resizable(False, False)
        self.configure(bg="#F5F6FA")
        self.overrideredirect(True)
        self.grab_set()
        self.lift()

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"400x230+{pw - 200}+{ph - 115}")

        self.configure(highlightthickness=1, highlightbackground="#D0D7E2")

        # Header
        header = tk.Frame(self, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=f"  {title}", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=14)
        close = tk.Label(header, text="✕", bg="#1E2A3A", fg="#6B8099",
                         font=("Segoe UI", 11), cursor="hand2", padx=14)
        close.pack(side="right")
        close.bind("<Button-1>", lambda _: self.destroy())
        close.bind("<Enter>", lambda _: close.config(fg="#FFFFFF"))
        close.bind("<Leave>", lambda _: close.config(fg="#6B8099"))

        # Corpo
        body = tk.Frame(self, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=28, pady=16)

        # Ícone + mensagem principal
        top = tk.Frame(body, bg="#F5F6FA")
        top.pack(anchor="w", fill="x")
        tk.Label(top, text=icon, bg="#F5F6FA", fg=icon_color,
                 font=("Segoe UI", 20)).pack(side="left", padx=(0, 12))
        tk.Label(top, text=message, bg="#F5F6FA", fg="#1E2A3A",
                 font=("Segoe UI", 11, "bold"), anchor="w",
                 justify="left", wraplength=300).pack(side="left", anchor="w")

        if submessage:
            tk.Label(body, text=submessage, bg="#F5F6FA", fg="#6B7A90",
                     font=("Segoe UI", 9), anchor="w", justify="left",
                     wraplength=344).pack(anchor="w", pady=(10, 0))

        # Botão OK
        btn_row = tk.Frame(self, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=28, pady=(0, 18))
        tk.Button(btn_row, text="OK", bg="#4A90E2", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#357ABD", activeforeground="#FFFFFF",
                  padx=24, pady=6, command=self.destroy).pack(side="right")

        self.bind("<Return>", lambda _: self.destroy())
        self.bind("<Escape>", lambda _: self.destroy())

    def destroy(self):
        try: self._overlay.destroy()
        except: pass
        super().destroy()


class ConfirmDialog(tk.Toplevel):
    """Diálogo de confirmação moderno, substitui messagebox.askyesno."""
    def __init__(self, parent, title: str, message: str, submessage: str = "",
                 confirm_text: str = "Confirmar", confirm_color: str = "#E53935"):
        # Overlay escuro sobre a janela principal
        self._overlay = tk.Toplevel(parent)
        self._overlay.overrideredirect(True)
        self._overlay.configure(bg="#000000")
        self._overlay.attributes("-alpha", 0.45)
        self._overlay.geometry(
            f"{parent.winfo_width()}x{parent.winfo_height()}"
            f"+{parent.winfo_rootx()}+{parent.winfo_rooty()}"
        )
        self._overlay.lift()

        super().__init__(parent)
        self.title("")
        self.resizable(False, False)
        self.configure(bg="#F5F6FA")
        self.overrideredirect(True)
        self.grab_set()
        self.result = False
        self.lift()

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"400x210+{pw - 200}+{ph - 105}")

        self._build(title, message, submessage, confirm_text, confirm_color)
        self.bind("<Return>", lambda _: self._confirm())
        self.bind("<Escape>", lambda _: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build(self, title, message, submessage, confirm_text, confirm_color):
        # Sombra/borda
        self.configure(highlightthickness=1, highlightbackground="#D0D7E2")

        # Header
        header = tk.Frame(self, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=f"  {title}", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=14)
        close = tk.Label(header, text="✕", bg="#1E2A3A", fg="#6B8099",
                         font=("Segoe UI", 11), cursor="hand2", padx=14)
        close.pack(side="right")
        close.bind("<Button-1>", lambda _: self.destroy())
        close.bind("<Enter>", lambda _: close.config(fg="#FFFFFF"))
        close.bind("<Leave>", lambda _: close.config(fg="#6B8099"))

        # Corpo
        body = tk.Frame(self, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=28, pady=20)

        tk.Label(body, text=message, bg="#F5F6FA", fg="#1E2A3A",
                 font=("Segoe UI", 11, "bold"), anchor="w", justify="left").pack(anchor="w")

        if submessage:
            tk.Label(body, text=submessage, bg="#F5F6FA", fg="#6B7A90",
                     font=("Segoe UI", 9), anchor="w", justify="left").pack(anchor="w", pady=(4, 0))

        # Botões
        btn_row = tk.Frame(self, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=28, pady=(0, 20))

        tk.Button(btn_row, text="Cancelar", bg="#E8EDF4", fg="#1E2A3A",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  activebackground="#D0D7E2", padx=18, pady=7,
                  command=self.destroy).pack(side="right", padx=(8, 0))

        tk.Button(btn_row, text=confirm_text, bg=confirm_color, fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#B71C1C", activeforeground="#FFFFFF",
                  padx=18, pady=7, command=self._confirm).pack(side="right")

    def _confirm(self):
        self.result = True
        self.destroy()

    def destroy(self):
        try:
            self._overlay.destroy()
        except Exception:
            pass
        super().destroy()


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


# ══════════════════════════════════════════════════════════════════════════════
# AUTENTICAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def auth_login(email: str, password: str) -> dict | None:
    """Valida credenciais do tenant. Retorna o usuário ou None se inválido."""
    hashed = _hash_password(password)
    res = sb.table("users").select("*").eq("tenant_id", TENANT_ID).eq("email", email).eq("password", hashed).execute()
    return res.data[0] if res.data else None


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

def audit(action: str, target_type: str = None, target_name: str = None):
    """Registra uma ação do usuário logado no audit_log."""
    try:
        sb.table("audit_log").insert({
            "tenant_id":   TENANT_ID,
            "user_id":     CURRENT_USER.get("id"),
            "user_name":   CURRENT_USER.get("name", ""),
            "action":      action,
            "target_type": target_type,
            "target_name": target_name,
        }).execute()
    except Exception as e:
        print(f"[Audit] Erro: {e}")

def audit_list(limit: int = 200) -> list[dict]:
    """Retorna os últimos registros de audit do tenant."""
    res = (sb.table("audit_log")
             .select("*")
             .eq("tenant_id", TENANT_ID)
             .order("created_at", desc=True)
             .limit(limit)
             .execute())
    return res.data


# ══════════════════════════════════════════════════════════════════════════════
# TRAVA DE ARQUIVO
# ══════════════════════════════════════════════════════════════════════════════

def file_lock(file_id: str) -> bool:
    """
    Tenta travar o arquivo para esta sessão.
    Retorna True se conseguiu, False se já está travado por outra sessão.
    """
    res = sb.table("files").select("locked_by").eq("id", file_id).execute()
    if not res.data:
        return False
    row = res.data[0]
    if row["locked_by"] and row["locked_by"] != SESSION_ID:
        return False   # travado por outra sessão/instância
    # Trava com o SESSION_ID desta instância
    sb.table("files").update({
        "locked_by":   SESSION_ID,
        "locked_name": CURRENT_USER.get("name", "Usuário"),
        "locked_at":   "now()",
    }).eq("id", file_id).execute()
    return True


def file_unlock(file_id: str):
    """Libera a trava do arquivo desta sessão."""
    sb.table("files").update({
        "locked_by":   None,
        "locked_name": None,
        "locked_at":   None,
    }).eq("id", file_id).eq("locked_by", SESSION_ID).execute()


def file_unlock_all():
    """Libera todas as travas desta sessão ao fechar o app."""
    sb.table("files").update({
        "locked_by":   None,
        "locked_name": None,
        "locked_at":   None,
    }).eq("locked_by", SESSION_ID).execute()


def file_get_lock_info(file_id: str) -> dict | None:
    """Retorna info de trava do arquivo, ou None se livre ou se é desta sessão."""
    res = sb.table("files").select("locked_by, locked_name, locked_at").eq("id", file_id).execute()
    if res.data and res.data[0]["locked_by"]:
        row = res.data[0]
        # Não bloqueia se a trava é desta própria sessão
        if row["locked_by"] == SESSION_ID:
            return None
        return row
    return None


# ── Modal: Adicionar Arquivo ──────────────────────────────────────────────────
class AddFileDialog(tk.Toplevel):
    """Dialog com 3 opções: Novo Word, Novo Excel, Subir arquivo existente."""

    def __init__(self, parent, parent_storage_path: str):
        super().__init__(parent)
        self.resizable(False, False)
        self.configure(bg="#F5F6FA")
        self.overrideredirect(True)
        self.grab_set()
        # result: {"mode": "new"|"upload", "name": str, "local_path": str|None}
        self.result = None
        self._parent_storage_path = parent_storage_path
        self._mode = "new"          # "new" ou "upload"
        self._ext  = ".docx"
        self._color = "#2B579A"

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"480x370+{pw - 240}+{ph - 185}")
        self._build()

    def _build(self):
        # Header
        header = tk.Frame(self, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="  Adicionar Arquivo", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=12)
        close = tk.Label(header, text="✕", bg="#1E2A3A", fg="#6B8099",
                         font=("Segoe UI", 11), cursor="hand2", padx=14)
        close.pack(side="right")
        close.bind("<Button-1>", lambda _: self.destroy())
        close.bind("<Enter>",    lambda _: close.config(fg="#FFFFFF"))
        close.bind("<Leave>",    lambda _: close.config(fg="#6B8099"))

        body = tk.Frame(self, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Opções ──
        tk.Label(body, text="O que deseja fazer?", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        opts_row = tk.Frame(body, bg="#F5F6FA")
        opts_row.pack(fill="x", pady=(0, 16))

        OPTIONS = [
            ("📝", "Novo Word",   "new",    ".docx", "#2B579A"),
            ("📊", "Novo Excel",  "new",    ".xlsx", "#217346"),
            ("📁", "Subir arquivo", "upload", None,   "#E67E22"),
        ]
        self._opt_cards = {}
        for icon, label, mode, ext, color in OPTIONS:
            card = tk.Frame(opts_row, bg="#FFFFFF", cursor="hand2",
                            highlightthickness=2, highlightbackground="#E0E6EF",
                            width=130, height=80)
            card.pack(side="left", padx=(0, 8))
            card.pack_propagate(False)
            tk.Label(card, text=icon, bg="#FFFFFF", fg=color,
                     font=("Segoe UI", 22)).pack(pady=(8, 0))
            tk.Label(card, text=label, bg="#FFFFFF", fg="#1E2A3A",
                     font=("Segoe UI", 8)).pack()
            self._opt_cards[label] = (card, color, mode, ext)
            for w in [card] + list(card.winfo_children()):
                w.bind("<Button-1>", lambda _, lb=label: self._select_opt(lb))

        # ── Nome ──
        self._name_lbl = tk.Label(body, text="Nome do arquivo", bg="#F5F6FA", fg="#6B7A90",
                                  font=("Segoe UI", 9))
        self._name_lbl.pack(anchor="w")
        self._name_var = tk.StringVar()
        self._entry = tk.Entry(body, textvariable=self._name_var, font=("Segoe UI", 11),
                               relief="flat", bg="#FFFFFF", fg="#1E2A3A",
                               insertbackground="#1E2A3A", highlightthickness=1,
                               highlightbackground="#D0D7E2", highlightcolor="#4A90E2")
        self._entry.pack(fill="x", ipady=7, pady=(4, 0))
        self._entry.focus_set()

        # Botões
        btn_row = tk.Frame(self, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=24, pady=(12, 20))
        tk.Button(btn_row, text="Cancelar", bg="#E8EDF4", fg="#1E2A3A", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2", activebackground="#D0D7E2",
                  padx=16, pady=6, command=self.destroy).pack(side="right", padx=(8, 0))
        self._btn_ok = tk.Button(btn_row, text="Criar", bg="#27AE60", fg="#FFFFFF",
                                 relief="flat", font=("Segoe UI", 10, "bold"), cursor="hand2",
                                 activebackground="#1E8449", activeforeground="#FFFFFF",
                                 padx=16, pady=6, command=self._confirm)
        self._btn_ok.pack(side="right")

        self.bind("<Return>", lambda _: self._confirm())
        self.bind("<Escape>", lambda _: self.destroy())

        # Seleciona Word por padrão
        self._select_opt("Novo Word")

    def _select_opt(self, label):
        for lb, (card, color, mode, ext) in self._opt_cards.items():
            if lb == label:
                card.config(highlightbackground=color, bg="#F8FAFF")
                for ch in card.winfo_children(): ch.config(bg="#F8FAFF")
                self._mode  = mode
                self._ext   = ext
                self._color = color
            else:
                card.config(highlightbackground="#E0E6EF", bg="#FFFFFF")
                for ch in card.winfo_children(): ch.config(bg="#FFFFFF")

        if self._mode == "upload":
            self._name_lbl.config(text="Arquivo selecionado")
            self._entry.config(state="disabled", bg="#F0F0F0")
            self._btn_ok.config(text="Selecionar arquivo")
        else:
            self._name_lbl.config(text="Nome do arquivo")
            self._entry.config(state="normal", bg="#FFFFFF")
            self._btn_ok.config(text="Criar")

    def _confirm(self):
        if self._mode == "upload":
            local_path = filedialog.askopenfilename(
                title="Selecionar arquivo",
                filetypes=[
                    ("Documentos", "*.docx *.xlsx *.pdf *.doc *.xls *.pptx *.txt"),
                    ("Todos os arquivos", "*.*"),
                ]
            )
            if not local_path:
                return
            self.result = {
                "mode": "upload",
                "name": os.path.basename(local_path),
                "local_path": local_path,
            }
            self.destroy()
        else:
            name = self._name_var.get().strip()
            if not name:
                messagebox.showwarning("Atenção", "Informe um nome para o arquivo.", parent=self)
                return
            filename = name if name.endswith(self._ext) else name + self._ext
            self.result = {
                "mode": "new",
                "name": filename,
                "local_path": None,
                "ext": self._ext,
            }
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
        self.title("Zynor Docs")
        if os.path.exists(_ICON_FILE):
            self.iconbitmap(_ICON_FILE)
        self.geometry("1240x720")
        self.minsize(900, 540)
        self.configure(bg="#1E2A3A")
        self.overrideredirect(True)   # remove barra nativa do Windows
        self._is_maximized = False
        self._restore_geometry = "1240x720+120+60"
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._root_path  = None
        self._current_path = None
        self._history: list[str] = []
        self._search_after = None
        self._open_files: set = set()
        self._build_ui()
        # Inicia maximizado e força ícone na barra de tarefas
        self.after(10, self._maximize)
        self.after(50, self._fix_taskbar)
        # Libera travas ao fechar
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        file_unlock_all()
        self.destroy()

    def _logout(self):
        audit("logout")
        file_unlock_all()
        self.destroy()
        # Reabre a tela de login
        login = LoginWindow()
        login.mainloop()
        if login._logged_in:
            app = App()
            app.mainloop()

    def _fix_taskbar(self):
        """Força o ícone do app a aparecer na barra de tarefas do Windows."""
        GWL_EXSTYLE      = -20
        WS_EX_APPWINDOW  = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        self._apply_icon(hwnd)
        self.withdraw()
        self.after(10, self.deiconify)

    def _apply_icon(self, hwnd=None):
        """Força o ícone personalizado na barra de tarefas via WM_SETICON."""
        if not os.path.exists(_ICON_FILE):
            return
        try:
            LR_LOADFROMFILE = 0x00000010
            IMAGE_ICON      = 1
            WM_SETICON      = 0x0080
            ICON_SMALL      = 0
            ICON_BIG        = 1
            hicon = ctypes.windll.user32.LoadImageW(
                None, _ICON_FILE, IMAGE_ICON, 0, 0, LR_LOADFROMFILE
            )
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG,   hicon)
        except Exception as e:
            print(f"[Icon] Erro ao aplicar ícone: {e}")

    def _get_work_area(self):
        """Retorna (width, height, x, y) da área de trabalho, descontando a taskbar."""
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
        return rect.right - rect.left, rect.bottom - rect.top, rect.left, rect.top

    def _maximize(self):
        self._restore_geometry = self.geometry()
        w, h, x, y = self._get_work_area()
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._is_maximized = True
        self._btn_max.config(text="❐")

    def _toggle_maximize(self):
        if self._is_maximized:
            self.geometry(self._restore_geometry)
            self._is_maximized = False
            self._btn_max.config(text="□")
        else:
            self._restore_geometry = self.geometry()
            w, h, x, y = self._get_work_area()
            self.geometry(f"{w}x{h}+{x}+{y}")
            self._is_maximized = True
            self._btn_max.config(text="❐")

    def _minimize(self):
        SW_MINIMIZE = 6
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)

    def _start_drag(self, event):
        if self._is_maximized:
            return
        self._drag_start_x = event.x_root - self.winfo_x()
        self._drag_start_y = event.y_root - self.winfo_y()

    def _do_drag(self, event):
        if self._is_maximized:
            return
        x = event.x_root - self._drag_start_x
        y = event.y_root - self._drag_start_y
        self.geometry(f"+{x}+{y}")

    # ══════════════════════════════════════════════════════════════════════════
    # UI principal
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── Barra de título customizada ───────────────────────────────────────
        titlebar = tk.Frame(self, bg="#141F2D", height=36)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)

        # Ícone + nome do app
        tk.Label(titlebar, text="  ◈  Zynor Docs", bg="#141F2D", fg="#FFFFFF",
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)

        # Botões de controle (direita)
        btn_cfg = dict(bg="#141F2D", font=("Segoe UI", 11), relief="flat",
                       cursor="hand2", bd=0, padx=14, pady=4)

        btn_close = tk.Button(titlebar, text="✕", fg="#9AAEC1",
                              activebackground="#E53935", activeforeground="#FFFFFF",
                              command=self._on_close, **btn_cfg)
        btn_close.pack(side="right")
        btn_close.bind("<Enter>", lambda _: btn_close.config(bg="#E53935", fg="#FFFFFF"))
        btn_close.bind("<Leave>", lambda _: btn_close.config(bg="#141F2D", fg="#9AAEC1"))

        self._btn_max = tk.Button(titlebar, text="□", fg="#9AAEC1",
                                  activebackground="#2E3F52", activeforeground="#FFFFFF",
                                  command=self._toggle_maximize, **btn_cfg)
        self._btn_max.pack(side="right")
        self._btn_max.bind("<Enter>", lambda _: self._btn_max.config(bg="#2E3F52", fg="#FFFFFF"))
        self._btn_max.bind("<Leave>", lambda _: self._btn_max.config(bg="#141F2D", fg="#9AAEC1"))

        btn_min = tk.Button(titlebar, text="─", fg="#9AAEC1",
                            activebackground="#2E3F52", activeforeground="#FFFFFF",
                            command=self._minimize, **btn_cfg)
        btn_min.pack(side="right")
        btn_min.bind("<Enter>", lambda _: btn_min.config(bg="#2E3F52", fg="#FFFFFF"))
        btn_min.bind("<Leave>", lambda _: btn_min.config(bg="#141F2D", fg="#9AAEC1"))

        # Arrastar janela pelo titlebar
        titlebar.bind("<Button-1>",   self._start_drag)
        titlebar.bind("<B1-Motion>",  self._do_drag)
        titlebar.bind("<Double-1>",   lambda _: self._toggle_maximize())

        # ── Corpo (sidebar + main) ─────────────────────────────────────────────
        body = tk.Frame(self, bg="#F5F6FA")
        body.pack(fill="both", expand=True)

        # ── Sidebar ───────────────────────────────────────────────────────────
        self._sidebar = tk.Frame(body, bg="#1E2A3A", width=240)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        tk.Label(self._sidebar, text="Zynor Docs", bg="#1E2A3A", fg="#FFFFFF",
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
        main = tk.Frame(body, bg="#F5F6FA")
        main.pack(side="left", fill="both", expand=True)

        # Topbar
        topbar = tk.Frame(main, bg="#FFFFFF", height=56)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        self._topbar_title = tk.Label(topbar, text="Documentos", bg="#FFFFFF", fg="#1E2A3A",
                                      font=("Segoe UI", 14, "bold"))
        self._topbar_title.pack(side="left", padx=24, pady=14)
        user_name = CURRENT_USER.get("name", "Usuário")
        user_frame = tk.Frame(topbar, bg="#FFFFFF", cursor="hand2")
        user_frame.pack(side="right", padx=24)
        tk.Label(user_frame, text="👤", bg="#FFFFFF", fg="#4A90E2",
                 font=("Segoe UI", 11)).pack(side="left")
        user_lbl = tk.Label(user_frame, text=f"  {user_name}  ▾", bg="#FFFFFF", fg="#1E2A3A",
                            font=("Segoe UI", 10))
        user_lbl.pack(side="left")

        def _show_user_menu(e):
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label=f"👤  {user_name}", state="disabled")
            menu.add_separator()
            menu.add_command(label="🚪  Sair", command=self._logout)
            menu.tk_popup(e.x_root, e.y_root)

        for w in [user_frame, user_lbl]:
            w.bind("<Button-1>", _show_user_menu)

        # Container de páginas
        self._pages_container = tk.Frame(main, bg="#F5F6FA")
        self._pages_container.pack(fill="both", expand=True)

        # ── Página: Configurações ─────────────────────────────────────────────
        self._page_config = tk.Frame(self._pages_container, bg="#F5F6FA")

        # ── Página: Relatórios ────────────────────────────────────────────────
        self._page_relatorios = tk.Frame(self._pages_container, bg="#F5F6FA")

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


        # Área de cards com scroll
        wrapper = tk.Frame(content, bg="#F5F6FA")
        wrapper.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Thin.Vertical.TScrollbar", troughcolor="#F5F6FA",
                        background="#C8D0DC", borderwidth=0, arrowsize=0)

        canvas = tk.Canvas(wrapper, bg="#F5F6FA", highlightthickness=0)
        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview,
                            style="Thin.Vertical.TScrollbar")

        def _update_scrollbar(*_):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Mostra a scrollbar só quando o conteúdo ultrapassa a área visível
            if canvas.bbox("all") and canvas.bbox("all")[3] > canvas.winfo_height():
                vsb.pack(side="right", fill="y")
            else:
                vsb.pack_forget()

        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)

        self._cards_frame = tk.Frame(canvas, bg="#F5F6FA")
        self._canvas_window = canvas.create_window((0, 0), window=self._cards_frame, anchor="nw")

        self._cards_frame.bind("<Configure>", _update_scrollbar)
        self._update_scrollbar = _update_scrollbar
        canvas.bind("<Configure>", self._on_canvas_resize)

        def _on_mousewheel(e):
            bbox = canvas.bbox("all")
            if bbox and bbox[3] > canvas.winfo_height():
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self._canvas = canvas
        self._canvas_width = 0
        self._resize_after = None

        # Tela inicial
        self._nav_go("documentos")

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)
        new_width = event.width
        if self._resize_after:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(120, lambda: self._apply_resize(new_width))

    def _apply_resize(self, new_width: int):
        self._resize_after = None
        if self._calc_cols(new_width) != self._calc_cols(self._canvas_width):
            self._canvas_width = new_width
            if self._current_path:
                self._render_cards(self._current_path)
            else:
                self._show_home()
        else:
            self._canvas_width = new_width
        self._update_scrollbar()

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
        elif key == "relatorios":
            self._page_relatorios.pack(fill="both", expand=True)
            self._show_relatorios()
        elif key == "config":
            self._page_config.pack(fill="both", expand=True)
            self._show_config()

    # ══════════════════════════════════════════════════════════════════════════
    # Navegação interna — Documentos
    # ══════════════════════════════════════════════════════════════════════════
    def _show_home(self):
        """Tela inicial — lista pastas do banco de dados."""
        self._current_path = None
        self._root_path = None
        self._history.clear()
        if self._search_after:
            self.after_cancel(self._search_after)
            self._search_after = None
        self._search_var.set("")
        self._result_var.set("")
        self._clear_breadcrumb()
        self._refresh_sidebar()
        self._render_home_cards()

    def _render_home_cards(self):
        """Renderiza o grid da home: botão Nova Pasta + pastas cadastradas."""
        self._clear_cards()
        folders = db_list_folders()
        COLS = self._calc_cols()
        perms = get_current_user_permissions()

        entries = []
        if perms.get("can_create") or perms.get("is_admin"):
            entries.append(("add", None))
        entries += [("folder", f) for f in folders]

        row_frame = None
        for i, (kind, data) in enumerate(entries):
            if i % COLS == 0:
                row_frame = tk.Frame(self._cards_frame, bg="#F5F6FA")
                row_frame.pack(fill="x", pady=4)
            if kind == "add":
                self._make_add_card(row_frame, "📁", "Nova Pasta", "#4A90E2",
                                    self._open_new_folder_dialog)
            else:
                self._make_home_folder_card(row_frame, data)


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

        sp = folder["storage_path"]
        fid = folder["id"]

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

        def on_right_click(event, _fid=fid):
            perms = get_current_user_permissions()
            if not (perms.get("can_delete") or perms.get("is_admin")):
                return
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="🗑  Excluir pasta",
                             command=lambda: self._remove_folder(_fid))
            menu.tk_popup(event.x_root, event.y_root)

        for w in [card] + list(card.winfo_children()):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda _, p=sp: self._enter_folder(p))
            w.bind("<Button-3>", on_right_click)

    def _enter_folder(self, storage_path: str):
        self._root_path = storage_path
        self._history.clear()
        self._navigate_to(storage_path)

    def _remove_folder(self, folder_id: int):
        perms = get_current_user_permissions()
        if not perms.get("can_delete") and not perms.get("is_admin"):
            messagebox.showwarning("Sem permissão",
                                   "Você não tem permissão para excluir pastas.")
            return
        dialog = ConfirmDialog(
            self,
            title="Excluir pasta",
            message="Deseja excluir esta pasta?",
            submessage="Esta ação removerá a pasta e todo o seu conteúdo.",
            confirm_text="Excluir",
            confirm_color="#E53935",
        )
        self.wait_window(dialog)
        if dialog.result:
            name = sb.table("folders").select("name").eq("id", folder_id).execute()
            folder_name = name.data[0]["name"] if name.data else str(folder_id)
            db_delete(folder_id, "folder")
            audit("excluiu", "pasta", folder_name)
            self._refresh_sidebar()
            self._show_home()

    def _remove_file(self, file_id: int):
        perms = get_current_user_permissions()
        if not perms.get("can_delete") and not perms.get("is_admin"):
            messagebox.showwarning("Sem permissão",
                                   "Você não tem permissão para excluir arquivos.")
            return
        dialog = ConfirmDialog(
            self,
            title="Excluir arquivo",
            message="Deseja excluir este arquivo?",
            submessage="Esta ação não pode ser desfeita.",
            confirm_text="Excluir",
            confirm_color="#E53935",
        )
        self.wait_window(dialog)
        if dialog.result:
            name = sb.table("files").select("name").eq("id", file_id).execute()
            file_name = name.data[0]["name"] if name.data else str(file_id)
            db_delete(file_id, "file")
            audit("excluiu", "arquivo", file_name)
            if self._current_path:
                self._render_cards(self._current_path)

    def _refresh_sidebar(self):
        for w in self._folders_list.winfo_children():
            w.destroy()
        # Pastas raiz são as que têm parent_path vazio
        root_folders = [f for f in db_list_folders() if f.get("parent_path", "") == ""]
        for folder in root_folders:
            self._add_folder_to_sidebar(folder)

    # ══════════════════════════════════════════════════════════════════════════
    # RELATÓRIOS
    # ══════════════════════════════════════════════════════════════════════════
    def _show_relatorios(self):
        for w in self._page_relatorios.winfo_children():
            w.destroy()

        page = self._page_relatorios
        perms = get_current_user_permissions()
        if not perms.get("is_admin"):
            tk.Label(page, text="⚠  Acesso restrito a administradores.",
                     bg="#F5F6FA", fg="#E53935", font=("Segoe UI", 12)).pack(pady=60)
            return

        # Cabeçalho
        bar = tk.Frame(page, bg="#F5F6FA")
        bar.pack(fill="x", padx=28, pady=(20, 0))
        tk.Label(bar, text="Relatórios", bg="#F5F6FA", fg="#1E2A3A",
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Button(bar, text="⬇  Exportar Excel", bg="#27AE60", fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  activebackground="#1E8449", padx=14, pady=6,
                  command=self._export_audit_excel).pack(side="right")
        tk.Button(bar, text="🔄  Atualizar", bg="#4A90E2", fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  activebackground="#357ABD", padx=14, pady=6,
                  command=self._show_relatorios).pack(side="right", padx=(0, 8))

        # Tabela
        wrap = tk.Frame(page, bg="#FFFFFF", highlightthickness=1,
                        highlightbackground="#E0E6EF")
        wrap.pack(fill="both", expand=True, padx=28, pady=16)

        COLS = [("Data / Hora", 18), ("Usuário", 18), ("Ação", 10), ("Tipo", 10), ("Item", 28)]

        head = tk.Frame(wrap, bg="#F5F6FA")
        head.pack(fill="x")
        for col, cw in COLS:
            tk.Label(head, text=col, bg="#F5F6FA", fg="#6B7A90",
                     font=("Segoe UI", 10, "bold"), anchor="w",
                     padx=12, pady=10, width=cw).pack(side="left")
        tk.Frame(wrap, bg="#E0E6EF", height=1).pack(fill="x")

        # Scroll
        container = tk.Frame(wrap, bg="#FFFFFF")
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg="#FFFFFF", highlightthickness=0)
        sb_scroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg="#FFFFFF")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb_scroll.set)
        sb_scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        ACTION_COLORS = {
            "login":      "#2E7D32",
            "logout":     "#6B7A90",
            "abriu":      "#1565C0",
            "visualizou": "#6A1B9A",
            "criou":      "#E65100",
            "excluiu":    "#C62828",
        }

        logs = audit_list(500)
        if not logs:
            tk.Label(inner, text="Nenhum registro encontrado.",
                     bg="#FFFFFF", fg="#C0C8D4", font=("Segoe UI", 11)).pack(pady=40)
        else:
            for i, row in enumerate(logs):
                bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"
                r = tk.Frame(inner, bg=bg)
                r.pack(fill="x")
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                    dt_str = dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    dt_str = row.get("created_at", "")
                action = row.get("action", "")
                color  = ACTION_COLORS.get(action, "#1E2A3A")
                vals = [
                    (dt_str,                    18, "#1E2A3A"),
                    (row.get("user_name", ""),  18, "#1E2A3A"),
                    (action.capitalize(),        10, color),
                    (row.get("target_type", "") or "", 10, "#6B7A90"),
                    (row.get("target_name", "") or "", 28, "#1E2A3A"),
                ]
                for text, cw, fg in vals:
                    tk.Label(r, text=text, bg=bg, fg=fg,
                             font=("Segoe UI", 10), anchor="w",
                             padx=12, pady=8, width=cw).pack(side="left")

        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    def _export_audit_excel(self):
        try:
            import openpyxl
            from datetime import datetime, timezone
        except ImportError:
            messagebox.showerror("Erro", "openpyxl não instalado.")
            return

        logs = audit_list(5000)
        if not logs:
            messagebox.showinfo("Atenção", "Nenhum registro para exportar.")
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Audit Log"
        ws.append(["Data / Hora", "Usuário", "Ação", "Tipo", "Item"])
        for row in logs:
            try:
                dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                dt_str = dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                dt_str = row.get("created_at", "")
            ws.append([
                dt_str,
                row.get("user_name", ""),
                row.get("action", "").capitalize(),
                row.get("target_type", "") or "",
                row.get("target_name", "") or "",
            ])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 25

        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="relatorio_audit.xlsx",
        )
        if path:
            wb.save(path)
            messagebox.showinfo("Exportado", f"Arquivo salvo em:\n{path}")

    # ══════════════════════════════════════════════════════════════════════════
    # CONFIGURAÇÕES
    # ══════════════════════════════════════════════════════════════════════════
    def _show_config(self):
        for w in self._page_config.winfo_children():
            w.destroy()

        perms = get_current_user_permissions()
        if not perms.get("is_admin"):
            tk.Label(self._page_config, text="⛔  Acesso restrito a administradores.",
                     bg="#F5F6FA", fg="#E53935", font=("Segoe UI", 13)).pack(pady=80)
            return

        # ── Abas ──────────────────────────────────────────────────────────────
        tab_bar = tk.Frame(self._page_config, bg="#F5F6FA")
        tab_bar.pack(fill="x", padx=28, pady=(20, 0))

        content_area = tk.Frame(self._page_config, bg="#F5F6FA")
        content_area.pack(fill="both", expand=True, padx=28, pady=12)

        self._config_tab = tk.StringVar(value="usuarios")

        def switch_tab(tab):
            self._config_tab.set(tab)
            for t, btn in tab_btns.items():
                if t == tab:
                    btn.config(bg="#FFFFFF", fg="#1E2A3A",
                               highlightbackground="#4A90E2", highlightthickness=2)
                else:
                    btn.config(bg="#F5F6FA", fg="#6B7A90",
                               highlightbackground="#E0E6EF", highlightthickness=1)
            for w in content_area.winfo_children():
                w.destroy()
            if tab == "usuarios":
                self._render_config_usuarios(content_area)
            elif tab == "grupos":
                self._render_config_grupos(content_area)

        tab_btns = {}
        for key, label in [("usuarios", "👤  Usuários"), ("grupos", "🔑  Grupos")]:
            btn = tk.Button(tab_bar, text=label, relief="flat", font=("Segoe UI", 10),
                            cursor="hand2", padx=16, pady=7,
                            command=lambda k=key: switch_tab(k))
            btn.pack(side="left", padx=(0, 6))
            tab_btns[key] = btn

        switch_tab("usuarios")

    # ── Aba: Usuários ─────────────────────────────────────────────────────────
    def _render_config_usuarios(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        # Toolbar
        bar = tk.Frame(parent, bg="#F5F6FA")
        bar.pack(fill="x", pady=(0, 12))
        tk.Label(bar, text="Usuários do sistema", bg="#F5F6FA", fg="#1E2A3A",
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Button(bar, text="+ Novo Usuário", bg="#4A90E2", fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  activebackground="#357ABD", padx=14, pady=6,
                  command=lambda: self._open_user_dialog(parent)).pack(side="right")

        # Tabela
        wrap = tk.Frame(parent, bg="#FFFFFF", highlightthickness=1,
                        highlightbackground="#E0E6EF")
        wrap.pack(fill="both", expand=True)

        COL_WIDTHS = [("Nome", 22), ("E-mail", 30), ("Grupo", 18)]

        # Cabeçalho
        head = tk.Frame(wrap, bg="#F5F6FA")
        head.pack(fill="x")
        for col, cw in COL_WIDTHS:
            tk.Label(head, text=col, bg="#F5F6FA", fg="#6B7A90",
                     font=("Segoe UI", 9, "bold"), anchor="w",
                     padx=16, pady=10, width=cw).pack(side="left")
        tk.Frame(wrap, bg="#E0E6EF", height=1).pack(fill="x")

        # Linhas
        self._user_rows_frame = tk.Frame(wrap, bg="#FFFFFF")
        self._user_rows_frame.pack(fill="both", expand=True)
        self._render_user_rows(parent)

    def _render_user_rows(self, parent):
        COL_WIDTHS = [("name", 22), ("email", 30), ("group_name", 18)]
        for w in self._user_rows_frame.winfo_children():
            w.destroy()
        users = user_list()
        if not users:
            tk.Label(self._user_rows_frame, text="Nenhum usuário cadastrado.",
                     bg="#FFFFFF", fg="#C0C8D4", font=("Segoe UI", 11)).pack(pady=40)
            return
        for i, u in enumerate(users):
            bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"
            row = tk.Frame(self._user_rows_frame, bg=bg)
            row.pack(fill="x")
            for key, cw in COL_WIDTHS:
                tk.Label(row, text=u.get(key, ""), bg=bg, fg="#1E2A3A",
                         font=("Segoe UI", 10), anchor="w",
                         padx=16, pady=10, width=cw).pack(side="left")
            acts = tk.Frame(row, bg=bg)
            acts.pack(side="right", padx=12)
            tk.Button(acts, text="✏️", bg=bg, relief="flat", cursor="hand2",
                      font=("Segoe UI", 10), activebackground="#E8F0FE",
                      command=lambda uid=u["id"]: self._open_user_dialog(parent, uid)
                      ).pack(side="left")
            is_self = u["id"] == CURRENT_USER.get("id")
            tk.Button(acts, text="✕", bg=bg, fg="#E53935" if not is_self else "#C0C8D4",
                      relief="flat", cursor="hand2" if not is_self else "arrow",
                      font=("Segoe UI", 10, "bold"), activebackground="#FDECEA",
                      state="normal" if not is_self else "disabled",
                      command=lambda uid=u["id"]: self._delete_user(uid, parent)
                      ).pack(side="left")

    def _delete_user(self, user_id: str, parent):
        dialog = ConfirmDialog(self, "Excluir usuário",
                               "Deseja remover este usuário?",
                               "Esta ação não pode ser desfeita.",
                               confirm_text="Excluir")
        self.wait_window(dialog)
        if dialog.result:
            user_delete(user_id)
            self._render_user_rows(parent)

    def _open_user_dialog(self, parent, user_id: str = None):
        groups  = group_list()
        editing = None
        if user_id:
            users   = user_list()
            editing = next((u for u in users if u["id"] == user_id), None)

        self.update_idletasks()
        wx, wy = self.winfo_x(), self.winfo_y()
        ww, wh = self.winfo_width(), self.winfo_height()

        ov = tk.Toplevel(self)
        ov.overrideredirect(True)
        ov.configure(bg="#000000")
        ov.attributes("-alpha", 0.4)
        ov.geometry(f"{ww}x{wh}+{wx}+{wy}")
        ov.lift()

        dialog = tk.Toplevel(self)
        dialog.configure(bg="#F5F6FA")
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.overrideredirect(True)
        w, h = 440, 500
        x = wx + (ww - w) // 2
        y = wy + (wh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.configure(highlightthickness=1, highlightbackground="#D0D7E2")
        dialog.lift()

        # Header
        header = tk.Frame(dialog, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = "Editar Usuário" if editing else "Novo Usuário"
        tk.Label(header, text=f"  {title}", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=14)
        close = tk.Label(header, text="✕", bg="#1E2A3A", fg="#6B8099",
                         font=("Segoe UI", 11), cursor="hand2", padx=14)
        close.pack(side="right")

        def _close():
            try: ov.destroy()
            except: pass
            dialog.destroy()

        close.bind("<Button-1>", lambda _: _close())
        close.bind("<Enter>", lambda _: close.config(fg="#FFFFFF"))
        close.bind("<Leave>", lambda _: close.config(fg="#6B8099"))

        body = tk.Frame(dialog, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        vars_ = {}

        def _make_entry(label, key, secret=False, value=""):
            tk.Label(body, text=label, bg="#F5F6FA", fg="#6B7A90",
                     font=("Segoe UI", 9)).pack(anchor="w")
            v = tk.StringVar(value=value)
            e = tk.Entry(body, textvariable=v, show="•" if secret else "", font=("Segoe UI", 10),
                         relief="flat", bg="#FFFFFF", fg="#1E2A3A",
                         insertbackground="#1E2A3A", highlightthickness=1,
                         highlightbackground="#D0D7E2", highlightcolor="#4A90E2")
            e.pack(fill="x", ipady=6, pady=(3, 10))
            vars_[key] = v

        _make_entry("Nome", "name", value=editing.get("name", "") if editing else "")
        _make_entry("E-mail", "email", value=editing.get("email", "") if editing else "")

        # Senha apenas na inclusão
        if not editing:
            _make_entry("Senha", "password", secret=True)
            _make_entry("Confirmar senha", "password2", secret=True)

        # Grupo
        tk.Label(body, text="Grupo", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w")
        group_var = tk.StringVar()
        group_map = {g["name"]: g["id"] for g in groups}
        cb = ttk.Combobox(body, textvariable=group_var, state="readonly",
                          values=list(group_map.keys()), font=("Segoe UI", 10))
        cb.pack(fill="x", pady=(3, 0))
        if editing and editing.get("group_name"):
            group_var.set(editing["group_name"])
        elif groups:
            group_var.set(groups[0]["name"])

        # Botão "Alterar Senha" disponível apenas na edição
        if editing:
            tk.Button(body, text="🔑  Alterar Senha", bg="#E8EDF4", fg="#1E2A3A",
                      relief="flat", font=("Segoe UI", 9), cursor="hand2",
                      anchor="w", pady=6,
                      command=lambda: self._open_change_password_dialog(editing["id"])
                      ).pack(fill="x", pady=(14, 0))

        def _save():
            name  = vars_["name"].get().strip()
            email = vars_["email"].get().strip()
            grp   = group_var.get()

            if not name or not email:
                messagebox.showwarning("Atenção", "Nome e e-mail são obrigatórios.", parent=dialog)
                return
            if not grp:
                messagebox.showwarning("Atenção", "Selecione um grupo.", parent=dialog)
                return
            group_id = group_map[grp]

            if editing:
                user_update(editing["id"], name, email, None, group_id)
            else:
                pwd  = vars_["password"].get().strip()
                pwd2 = vars_["password2"].get().strip()
                if not pwd:
                    messagebox.showwarning("Atenção", "Informe uma senha.", parent=dialog)
                    return
                if pwd != pwd2:
                    messagebox.showwarning("Atenção", "As senhas não coincidem.", parent=dialog)
                    return
                user_create(name, email, pwd, group_id)
            _close()
            self._render_user_rows(parent)

        btn_row = tk.Frame(dialog, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))
        tk.Button(btn_row, text="Cancelar", bg="#E8EDF4", fg="#1E2A3A", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2", padx=14, pady=6,
                  command=_close).pack(side="right", padx=(8, 0))
        tk.Button(btn_row, text="Salvar", bg="#27AE60", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#1E8449", padx=14, pady=6,
                  command=_save).pack(side="right")
        dialog.bind("<Escape>", lambda _: _close())

    def _open_change_password_dialog(self, user_id: str):
        self.update_idletasks()
        wx, wy = self.winfo_x(), self.winfo_y()
        ww, wh = self.winfo_width(), self.winfo_height()

        ov = tk.Toplevel(self)
        ov.overrideredirect(True)
        ov.configure(bg="#000000")
        ov.attributes("-alpha", 0.4)
        ov.geometry(f"{ww}x{wh}+{wx}+{wy}")
        ov.lift()

        dialog = tk.Toplevel(self)
        dialog.configure(bg="#F5F6FA")
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.overrideredirect(True)
        w, h = 400, 280
        x = wx + (ww - w) // 2
        y = wy + (wh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.configure(highlightthickness=1, highlightbackground="#D0D7E2")
        dialog.lift()

        header = tk.Frame(dialog, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="  Alterar Senha", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=14)
        close_lbl = tk.Label(header, text="✕", bg="#1E2A3A", fg="#6B8099",
                             font=("Segoe UI", 11), cursor="hand2", padx=14)
        close_lbl.pack(side="right")

        def _close():
            try: ov.destroy()
            except: pass
            dialog.destroy()

        close_lbl.bind("<Button-1>", lambda _: _close())
        close_lbl.bind("<Enter>", lambda _: close_lbl.config(fg="#FFFFFF"))
        close_lbl.bind("<Leave>", lambda _: close_lbl.config(fg="#6B8099"))

        body = tk.Frame(dialog, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        pwd_var  = tk.StringVar()
        pwd2_var = tk.StringVar()

        for label, var in [("Nova Senha", pwd_var), ("Confirmar Nova Senha", pwd2_var)]:
            tk.Label(body, text=label, bg="#F5F6FA", fg="#6B7A90",
                     font=("Segoe UI", 9)).pack(anchor="w")
            tk.Entry(body, textvariable=var, show="•", font=("Segoe UI", 10),
                     relief="flat", bg="#FFFFFF", fg="#1E2A3A",
                     insertbackground="#1E2A3A", highlightthickness=1,
                     highlightbackground="#D0D7E2", highlightcolor="#4A90E2"
                     ).pack(fill="x", ipady=6, pady=(3, 10))

        def _save_pwd():
            pwd  = pwd_var.get().strip()
            pwd2 = pwd2_var.get().strip()
            if not pwd:
                messagebox.showwarning("Atenção", "Informe a nova senha.", parent=dialog)
                return
            if pwd != pwd2:
                messagebox.showwarning("Atenção", "As senhas não coincidem.", parent=dialog)
                return
            user_update(user_id, None, None, pwd, None)
            _close()
            messagebox.showinfo("Sucesso", "Senha alterada com sucesso.")

        btn_row = tk.Frame(dialog, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))
        tk.Button(btn_row, text="Cancelar", bg="#E8EDF4", fg="#1E2A3A", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2", padx=14, pady=6,
                  command=_close).pack(side="right", padx=(8, 0))
        tk.Button(btn_row, text="Salvar", bg="#27AE60", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#1E8449", padx=14, pady=6,
                  command=_save_pwd).pack(side="right")
        dialog.bind("<Escape>", lambda _: _close())

    # ── Aba: Grupos ───────────────────────────────────────────────────────────
    def _render_config_grupos(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        bar = tk.Frame(parent, bg="#F5F6FA")
        bar.pack(fill="x", pady=(0, 12))
        tk.Label(bar, text="Grupos e permissões", bg="#F5F6FA", fg="#1E2A3A",
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Button(bar, text="+ Novo Grupo", bg="#4A90E2", fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  activebackground="#357ABD", padx=14, pady=6,
                  command=lambda: self._open_group_dialog(parent)).pack(side="right")

        wrap = tk.Frame(parent, bg="#FFFFFF", highlightthickness=1,
                        highlightbackground="#E0E6EF")
        wrap.pack(fill="both", expand=True)

        # mesma fonte no cabeçalho e nas linhas → width em caracteres é consistente
        FONT = ("Segoe UI", 10)
        GROUP_COLS = [("Grupo", 20, "w"), ("Visualizar", 12, "center"), ("Criar", 9, "center"),
                      ("Editar", 9, "center"), ("Excluir", 9, "center"), ("Admin", 9, "center")]

        head = tk.Frame(wrap, bg="#F5F6FA")
        head.pack(fill="x")
        for col, cw, anch in GROUP_COLS:
            tk.Label(head, text=col, bg="#F5F6FA", fg="#6B7A90",
                     font=FONT, anchor=anch, justify="center" if anch == "center" else "left",
                     padx=0, pady=10, width=cw).pack(side="left")
        tk.Frame(wrap, bg="#E0E6EF", height=1).pack(fill="x")

        self._group_rows_frame = tk.Frame(wrap, bg="#FFFFFF")
        self._group_rows_frame.pack(fill="both", expand=True)
        self._render_group_rows(parent)

    def _render_group_rows(self, parent):
        FONT = ("Segoe UI", 10)
        GROUP_COLS = [("Grupo", 20, "w"), ("Visualizar", 12, "center"), ("Criar", 9, "center"),
                      ("Editar", 9, "center"), ("Excluir", 9, "center"), ("Admin", 9, "center")]
        FLAG_KEYS = ["can_view", "can_create", "can_edit", "can_delete", "is_admin"]

        for w in self._group_rows_frame.winfo_children():
            w.destroy()
        groups = group_list()
        if not groups:
            tk.Label(self._group_rows_frame, text="Nenhum grupo cadastrado.",
                     bg="#FFFFFF", fg="#C0C8D4", font=FONT).pack(pady=40)
            return
        for i, g in enumerate(groups):
            bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"
            row = tk.Frame(self._group_rows_frame, bg=bg)
            row.pack(fill="x")
            tk.Label(row, text=g["name"], bg=bg, fg="#1E2A3A",
                     font=(FONT[0], FONT[1], "bold"), anchor="w",
                     padx=12, pady=10, width=20).pack(side="left")
            for flag, (_, cw, _) in zip(FLAG_KEYS, GROUP_COLS[1:]):
                val = "☑" if g.get(flag) else "—"
                tk.Label(row, text=val, bg=bg,
                         fg="#2E7D32" if g.get(flag) else "#AABBCC",
                         font=FONT, anchor="center", justify="center",
                         padx=0, pady=10, width=cw).pack(side="left", fill="x", expand=False)
            acts = tk.Frame(row, bg=bg)
            acts.pack(side="right", padx=12)
            tk.Button(acts, text="✏️", bg=bg, relief="flat", cursor="hand2",
                      font=("Segoe UI", 10), activebackground="#E8F0FE",
                      command=lambda gid=g["id"]: self._open_group_dialog(parent, gid)
                      ).pack(side="left")
            tk.Button(acts, text="✕", bg=bg, fg="#E53935", relief="flat",
                      cursor="hand2", font=("Segoe UI", 10, "bold"),
                      activebackground="#FDECEA",
                      command=lambda gid=g["id"]: self._delete_group(gid, parent)
                      ).pack(side="left")

    def _delete_group(self, group_id: str, parent):
        dialog = ConfirmDialog(self, "Excluir grupo", "Deseja remover este grupo?",
                               "Os usuários deste grupo ficarão sem grupo.",
                               confirm_text="Excluir")
        self.wait_window(dialog)
        if dialog.result:
            group_delete(group_id)
            self._render_group_rows(parent)

    def _open_group_dialog(self, parent, group_id: str = None):
        groups  = group_list()
        editing = next((g for g in groups if g["id"] == group_id), None) if group_id else None

        self.update_idletasks()
        wx, wy = self.winfo_x(), self.winfo_y()
        ww, wh = self.winfo_width(), self.winfo_height()

        ov = tk.Toplevel(self)
        ov.overrideredirect(True)
        ov.configure(bg="#000000")
        ov.attributes("-alpha", 0.4)
        ov.geometry(f"{ww}x{wh}+{wx}+{wy}")
        ov.lift()

        dialog = tk.Toplevel(self)
        dialog.overrideredirect(True)
        dialog.configure(bg="#F5F6FA")
        dialog.grab_set()
        dialog.resizable(False, False)
        w, h = 380, 440
        x = wx + (ww - w) // 2
        y = wy + (wh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.configure(highlightthickness=1, highlightbackground="#D0D7E2")
        dialog.lift()

        header = tk.Frame(dialog, bg="#1E2A3A", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = "Editar Grupo" if editing else "Novo Grupo"
        tk.Label(header, text=f"  {title}", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=14)
        close = tk.Label(header, text="✕", bg="#1E2A3A", fg="#6B8099",
                         font=("Segoe UI", 11), cursor="hand2", padx=14)
        close.pack(side="right")

        def _close():
            try: ov.destroy()
            except: pass
            dialog.destroy()

        close.bind("<Button-1>", lambda _: _close())
        close.bind("<Enter>", lambda _: close.config(fg="#FFFFFF"))
        close.bind("<Leave>", lambda _: close.config(fg="#6B8099"))

        body = tk.Frame(dialog, bg="#F5F6FA")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(body, text="Nome do grupo", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w")
        name_var = tk.StringVar(value=editing["name"] if editing else "")
        tk.Entry(body, textvariable=name_var, font=("Segoe UI", 11),
                 relief="flat", bg="#FFFFFF", fg="#1E2A3A",
                 insertbackground="#1E2A3A", highlightthickness=1,
                 highlightbackground="#D0D7E2", highlightcolor="#4A90E2"
                 ).pack(fill="x", ipady=6, pady=(3, 16))

        tk.Label(body, text="Permissões", bg="#F5F6FA", fg="#6B7A90",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        perm_vars = {}
        perms_def = [
            ("can_view",   "👁  Visualizar arquivos e pastas"),
            ("can_create", "➕  Criar pastas e arquivos"),
            ("can_edit",   "✏️  Editar arquivos"),
            ("can_delete", "🗑  Excluir arquivos e pastas"),
            ("is_admin",   "⚙️  Administrador do sistema"),
        ]
        for key, label in perms_def:
            v = tk.BooleanVar(value=editing.get(key, False) if editing else False)
            cb_frame = tk.Frame(body, bg="#F5F6FA")
            cb_frame.pack(anchor="w", pady=2)
            tk.Checkbutton(cb_frame, variable=v, bg="#F5F6FA",
                           activebackground="#F5F6FA").pack(side="left")
            tk.Label(cb_frame, text=label, bg="#F5F6FA", fg="#1E2A3A",
                     font=("Segoe UI", 10)).pack(side="left")
            perm_vars[key] = v

        def _save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Atenção", "Informe um nome para o grupo.", parent=dialog)
                return
            kwargs = {k: v.get() for k, v in perm_vars.items()}
            if editing:
                group_update(editing["id"], name, **kwargs)
            else:
                group_create(name, **kwargs)
            _close()
            self._render_group_rows(parent)

        btn_row = tk.Frame(dialog, bg="#F5F6FA")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))
        tk.Button(btn_row, text="Cancelar", bg="#E8EDF4", fg="#1E2A3A", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2", padx=14, pady=6,
                  command=_close).pack(side="right", padx=(8, 0))
        tk.Button(btn_row, text="Salvar", bg="#27AE60", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#1E8449", padx=14, pady=6,
                  command=_save).pack(side="right")
        dialog.bind("<Escape>", lambda _: _close())

    def _navigate_to(self, path: str, push_history=True):
        if push_history and self._current_path and self._current_path != path:
            self._history.append(self._current_path)
        self._current_path = path
        self._search_var.set("")
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

        # Partes do caminho — oculta o tenant_id (primeiro segmento)
        parts = [p for p in path.strip("/").split("/") if p]
        # remove o segmento do tenant_id do breadcrumb visual
        if parts and parts[0] == TENANT_ID:
            parts = parts[1:]
        accumulated = f"{TENANT_ID}/"

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
        perms = get_current_user_permissions()

        entries = db_list_children(storage_path)
        entries_sorted = sorted(entries, key=lambda e: (e["type"] != "folder", e["name"].lower()))

        all_items = []
        if perms.get("can_create") or perms.get("is_admin"):
            all_items.append(("add_file", None))
        all_items += [("rec", r) for r in entries_sorted]

        COLS = self._calc_cols()
        row_frame = None
        for i, (kind, data) in enumerate(all_items):
            if i % COLS == 0:
                row_frame = tk.Frame(self._cards_frame, bg="#F5F6FA")
                row_frame.pack(fill="x", pady=4)
            if kind == "add_file":
                self._make_add_card(row_frame, "📄", "Novo Arquivo", "#27AE60",
                                    self._open_new_file_dialog)
            elif data["type"] == "folder":
                self._make_folder_card(row_frame, data)
            else:
                self._make_file_card(row_frame, data)

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

        sp  = rec["storage_path"]
        fid = rec["id"]

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

        def on_right_click(event, _fid=fid):
            perms = get_current_user_permissions()
            menu = tk.Menu(self, tearoff=0)
            can_open = perms.get("is_admin") or (perms.get("can_view") and perms.get("can_edit"))
            if can_open:
                menu.add_command(label="📂  Abrir arquivo",
                                 command=lambda: self._open_file(rec))
            if perms.get("can_delete") or perms.get("is_admin"):
                if can_open:
                    menu.add_separator()
                menu.add_command(label="🗑  Excluir arquivo",
                                 command=lambda: self._remove_file(_fid))
            if menu.index("end") is not None:
                menu.tk_popup(event.x_root, event.y_root)

        for w in [card, body, top_row] + list(top_row.winfo_children()) + list(body.winfo_children()):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e, _rec=rec: self._open_file(_rec))
            w.bind("<Button-3>", on_right_click)

    # ══════════════════════════════════════════════════════════════════════════
    # Ações
    # ══════════════════════════════════════════════════════════════════════════
    def _open_new_folder_dialog(self):
        perms = get_current_user_permissions()
        if not perms.get("can_create") and not perms.get("is_admin"):
            messagebox.showwarning("Sem permissão", "Você não tem permissão para criar pastas.")
            return
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
            audit("criou", "pasta", foldername)
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
        perms = get_current_user_permissions()
        if not perms.get("can_create") and not perms.get("is_admin"):
            messagebox.showwarning("Sem permissão", "Você não tem permissão para criar arquivos.")
            return
        if not self._current_path:
            messagebox.showwarning("Atenção", "Abra uma pasta primeiro para adicionar um arquivo.")
            return
        dialog = AddFileDialog(self, parent_storage_path=self._current_path)
        self.wait_window(dialog)
        if not dialog.result:
            return

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

        rec = db_create_file(filename, parent_path=self._current_path)
        audit("criou", "arquivo", filename)

        if dialog.result["mode"] == "upload":
            storage_upload(rec["storage_path"], dialog.result["local_path"])
        else:
            # Cria arquivo em branco e faz upload
            import tempfile
            ext = dialog.result["ext"]
            tmp = os.path.join(tempfile.gettempdir(), filename)
            if ext == ".docx":
                from docx import Document
                Document().save(tmp)
            elif ext == ".xlsx":
                import openpyxl
                openpyxl.Workbook().save(tmp)
            storage_upload(rec["storage_path"], tmp)
            # Abre automaticamente após criar
            local = storage_download(rec["storage_path"])
            if local:
                os.startfile(local)

        self._render_cards(self._current_path)

    def _open_file(self, rec: dict):
        """Abre o arquivo verificando trava. Baixa do R2 se necessário."""
        perms = get_current_user_permissions()
        is_admin   = perms.get("is_admin", False)
        can_view   = perms.get("can_view", False)
        can_edit   = perms.get("can_edit", False)
        read_only  = False  # abre sem travar e sem sincronizar

        if not is_admin:
            if not can_view:
                messagebox.showwarning("Sem permissão", "Você não tem permissão para visualizar arquivos.")
                return
            if not can_edit:
                # Modo somente leitura: abre localmente, sem trava e sem sync de volta
                read_only = True

        if read_only:
            dialog = InfoDialog(
                self,
                title="Modo somente leitura",
                message="Você não tem permissão para editar este arquivo.",
                submessage="Quaisquer alterações feitas ficarão apenas no seu computador\ne poderão ser sobrescritas na próxima sincronização.",
                icon="⚠️",
                icon_color="#E67E22",
            )
            self.wait_window(dialog)
            local = storage_download(rec["storage_path"], force=True)
            if local and os.path.exists(local):
                audit("visualizou", "arquivo", rec["name"])
                os.startfile(local)
            else:
                messagebox.showerror("Erro", "Não foi possível abrir o arquivo.")
            return

        # Verifica se está travado por outro usuário
        lock = file_get_lock_info(rec["id"])
        if lock and lock["locked_by"] != CURRENT_USER.get("id"):
            locked_at = lock.get("locked_at", "")
            if locked_at:
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(locked_at.replace("Z", "+00:00"))
                    locked_at = dt.astimezone().strftime("%d/%m/%Y às %H:%M")
                except Exception:
                    pass
            dialog = InfoDialog(
                self,
                title="Arquivo em uso",
                message=f"Editado por: {lock['locked_name']}",
                submessage=f"Em uso desde {locked_at}.\nAguarde a pessoa fechar o arquivo para editá-lo.",
                icon="🔒",
                icon_color="#E67E22",
            )
            self.wait_window(dialog)
            return

        # Trava o arquivo para o usuário atual
        if not file_lock(rec["id"]):
            messagebox.showwarning("Arquivo em uso", "Não foi possível abrir o arquivo agora.")
            return

        # Baixa do R2 — sem force para preservar edições locais ainda não sincronizadas
        local = storage_download(rec["storage_path"], force=False)
        if local and os.path.exists(local):
            audit("abriu", "arquivo", rec["name"])
            os.startfile(local)
            self._open_files.add(rec["id"])
            # Thread que monitora quando o arquivo for fechado, sincroniza com R2 e libera trava
            threading.Thread(
                target=self._watch_file_unlock,
                args=(rec["id"], local, rec["storage_path"]),
                daemon=True
            ).start()
        else:
            file_unlock(rec["id"])
            messagebox.showerror("Erro", "Não foi possível abrir o arquivo.")

    def _watch_file_unlock(self, file_id: str, local_path: str, storage_path: str):
        """
        Roda em background. Monitora quando o arquivo é fechado pelo editor
        (Word/LibreOffice), faz upload da versão atualizada para o R2 e libera a trava.
        """
        directory  = os.path.dirname(local_path)
        filename   = os.path.basename(local_path)

        # Arquivos de lock criados pelos editores enquanto o arquivo está aberto
        lo_lock   = os.path.join(directory, f".~lock.{filename}#")   # LibreOffice
        word_lock = os.path.join(directory, f"~${filename[2:]}")     # Microsoft Word

        def _is_open():
            # LibreOffice mantém .~lock.arquivo# enquanto aberto
            if os.path.exists(lo_lock):
                return True
            # Word mantém ~$arquivo enquanto aberto
            if os.path.exists(word_lock):
                return True
            # Fallback: tenta abrir exclusivamente
            try:
                with open(local_path, "r+b"):
                    pass
                return False
            except (IOError, PermissionError):
                return True

        time.sleep(5)  # aguarda o editor abrir e criar o lock file

        while True:
            time.sleep(3)
            if not _is_open():
                # Aguarda 5s e confirma novamente — evita falso positivo durante Ctrl+S
                time.sleep(5)
                if not _is_open():
                    # Arquivo realmente fechado — sobe para o R2
                    try:
                        r2.upload_file(local_path, CF_BUCKET, storage_path)
                        print(f"[R2] Sincronizado: {storage_path}")
                    except Exception as e:
                        print(f"[R2] Erro ao sincronizar: {e}")
                    file_unlock(file_id)
                    self._open_files.discard(file_id)
                    break

    def _choose_folder(self):
        pass  # não aplicável no modelo cloud

    # ── Busca ─────────────────────────────────────────────────────────────────
    def _on_search_change(self, *_):
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(300, self._run_search)

    def _run_search(self):
        query = self._search_var.get().strip().lower()
        if not query:
            if self._current_path:
                self._render_cards(self._current_path)
                self._render_breadcrumb(self._current_path)
            else:
                self._render_home_cards()
            self._result_var.set("")
            return

        self._clear_cards()
        # Busca em TODOS os registros do banco, independente de onde o usuário está
        matches = [r for r in db_list_all() if query in r["name"].lower()]

        COLS = self._calc_cols()
        row_frame = None
        for i, rec in enumerate(matches):
            if i % COLS == 0:
                row_frame = tk.Frame(self._cards_frame, bg="#F5F6FA")
                row_frame.pack(fill="x", pady=4)
            if rec["type"] == "folder":
                # Na home usa o card de home; dentro de pasta usa o card interno
                if self._current_path:
                    self._make_folder_card(row_frame, rec)
                else:
                    self._make_home_folder_card(row_frame, rec)
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


def _load_user_history() -> list[str]:
    try:
        with open(LAST_USER_FILE, "r", encoding="utf-8") as f:
            return [e.strip() for e in f.read().splitlines() if e.strip()]
    except Exception:
        return []


# ── Tela de Login ─────────────────────────────────────────────────────────────
class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zynor Docs")
        if os.path.exists(_ICON_FILE):
            self.iconbitmap(_ICON_FILE)
        self.configure(bg="#1E2A3A")
        self.overrideredirect(True)
        self.resizable(False, False)
        self._logged_in = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        W, H = 420, 520
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw - W)//2}+{(sh - H)//2}")
        self._build()
        self.after(50, self._fix_taskbar)

    def _fix_taskbar(self):
        GWL_EXSTYLE      = -20
        WS_EX_APPWINDOW  = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        if os.path.exists(_ICON_FILE):
            try:
                LR_LOADFROMFILE = 0x00000010
                IMAGE_ICON = 1
                WM_SETICON = 0x0080
                hicon = ctypes.windll.user32.LoadImageW(
                    None, _ICON_FILE, IMAGE_ICON, 0, 0, LR_LOADFROMFILE
                )
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon)
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon)
            except Exception as e:
                print(f"[Icon] {e}")
        self.withdraw()
        self.after(10, self.deiconify)

    def _build(self):
        # Barra de título mínima
        titlebar = tk.Frame(self, bg="#141F2D", height=32)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        btn_close = tk.Button(titlebar, text="✕", bg="#141F2D", fg="#6B8099",
                              relief="flat", font=("Segoe UI", 10), cursor="hand2",
                              bd=0, padx=12, pady=2, command=self.destroy,
                              activebackground="#E53935", activeforeground="#FFFFFF")
        btn_close.pack(side="right")
        btn_close.bind("<Enter>", lambda _: btn_close.config(bg="#E53935", fg="#FFFFFF"))
        btn_close.bind("<Leave>", lambda _: btn_close.config(bg="#141F2D", fg="#6B8099"))
        titlebar.bind("<Button-1>",  self._start_drag)
        titlebar.bind("<B1-Motion>", self._do_drag)

        # Corpo
        body = tk.Frame(self, bg="#1E2A3A")
        body.pack(fill="both", expand=True, padx=48, pady=10)

        # Logo / nome
        tk.Label(body, text="◈", bg="#1E2A3A", fg="#4A90E2",
                 font=("Segoe UI", 36)).pack(pady=(20, 0))
        tk.Label(body, text="Zynor Docs", bg="#1E2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 22, "bold")).pack()
        tk.Label(body, text="Gestão de Documentos", bg="#1E2A3A", fg="#6B8099",
                 font=("Segoe UI", 10)).pack(pady=(2, 32))

        # Campo Usuário
        tk.Label(body, text="Usuário", bg="#1E2A3A", fg="#9AAEC1",
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")
        user_frame = tk.Frame(body, bg="#2E3F52", highlightthickness=1,
                              highlightbackground="#3A4F65")
        user_frame.pack(fill="x", pady=(4, 14))
        tk.Label(user_frame, text="  👤", bg="#2E3F52", fg="#6B8099",
                 font=("Segoe UI", 11)).pack(side="left")
        self._user_var = tk.StringVar()
        user_entry = tk.Entry(user_frame, textvariable=self._user_var,
                              bg="#2E3F52", fg="#FFFFFF", relief="flat",
                              font=("Segoe UI", 11), insertbackground="#FFFFFF",
                              highlightthickness=0)
        user_entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(4, 8))

        self._history_popup = None

        def _show_history(event=None):
            history = _load_user_history()
            if not history:
                return
            _hide_history()
            self.update_idletasks()
            x = user_frame.winfo_rootx()
            y = user_frame.winfo_rooty() + user_frame.winfo_height()
            w = user_frame.winfo_width()

            popup = tk.Toplevel(self)
            popup.overrideredirect(True)
            popup.geometry(f"{w}x{min(len(history), 6) * 38}+{x}+{y}")
            popup.configure(bg="#1E2A3A")
            popup.attributes("-topmost", True)
            self._history_popup = popup

            for email in history:
                row = tk.Frame(popup, bg="#2E3F52", cursor="hand2")
                row.pack(fill="x")
                tk.Label(row, text=f"  👤  {email}", bg="#2E3F52", fg="#FFFFFF",
                         font=("Segoe UI", 10), anchor="w", pady=9
                         ).pack(fill="x")
                tk.Frame(popup, bg="#1E2A3A", height=1).pack(fill="x")

                def _select(e=email):
                    self._user_var.set(e)
                    _hide_history()
                    pass_entry.focus_set()

                row.bind("<Button-1>", lambda _, fn=_select: fn())
                for w_ in row.winfo_children():
                    w_.bind("<Button-1>", lambda _, fn=_select: fn())
                row.bind("<Enter>", lambda _, r=row: r.config(bg="#3A5068") or
                         [c.config(bg="#3A5068") for c in r.winfo_children()])
                row.bind("<Leave>", lambda _, r=row: r.config(bg="#2E3F52") or
                         [c.config(bg="#2E3F52") for c in r.winfo_children()])

        def _hide_history(event=None):
            if self._history_popup:
                try: self._history_popup.destroy()
                except: pass
                self._history_popup = None

        user_entry.bind("<FocusIn>",  lambda e: (user_frame.config(highlightbackground="#4A90E2"), _show_history(e)))
        user_entry.bind("<FocusOut>", lambda e: (user_frame.config(highlightbackground="#3A4F65"), self.after(150, _hide_history)))
        user_entry.bind("<Escape>",   lambda _: _hide_history())

        # Campo Senha
        tk.Label(body, text="Senha", bg="#1E2A3A", fg="#9AAEC1",
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")
        pass_frame = tk.Frame(body, bg="#2E3F52", highlightthickness=1,
                              highlightbackground="#3A4F65")
        pass_frame.pack(fill="x", pady=(4, 28))
        tk.Label(pass_frame, text="  🔒", bg="#2E3F52", fg="#6B8099",
                 font=("Segoe UI", 11)).pack(side="left")
        self._pass_var = tk.StringVar()
        pass_entry = tk.Entry(pass_frame, textvariable=self._pass_var, show="•",
                              bg="#2E3F52", fg="#FFFFFF", relief="flat",
                              font=("Segoe UI", 11), insertbackground="#FFFFFF",
                              highlightthickness=0)
        pass_entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(4, 8))
        pass_entry.bind("<FocusIn>",  lambda _: pass_frame.config(highlightbackground="#4A90E2"))
        pass_entry.bind("<FocusOut>", lambda _: pass_frame.config(highlightbackground="#3A4F65"))
        pass_entry.bind("<Return>", lambda _: self._login())

        # Botão Entrar
        btn = tk.Button(body, text="Entrar", bg="#4A90E2", fg="#FFFFFF",
                        relief="flat", font=("Segoe UI", 12, "bold"),
                        cursor="hand2", activebackground="#357ABD",
                        activeforeground="#FFFFFF", pady=12,
                        command=self._login)
        btn.pack(fill="x")
        btn.bind("<Enter>", lambda _: btn.config(bg="#357ABD"))
        btn.bind("<Leave>", lambda _: btn.config(bg="#4A90E2"))

        # Rodapé
        tk.Label(body, text="© 2025 Zynor Docs", bg="#1E2A3A", fg="#3A4F65",
                 font=("Segoe UI", 8)).pack(side="bottom", pady=(0, 8))

        # Preenche o último e-mail usado e foca na senha
        history = _load_user_history()
        if history:
            self._user_var.set(history[0])
            pass_entry.focus_set()
        else:
            user_entry.focus_set()

    def _login(self):
        email    = self._user_var.get().strip()
        password = self._pass_var.get().strip()
        if not email or not password:
            self._show_error("Preencha e-mail e senha.")
            return
        user = auth_login(email, password)
        if not user:
            self._show_error("E-mail ou senha incorretos.")
            return
        # Armazena o usuário globalmente
        global CURRENT_USER
        CURRENT_USER = {"id": user["id"], "name": user["name"], "email": user["email"]}
        try:
            history = _load_user_history()
            if email in history:
                history.remove(email)
            history.insert(0, email)
            with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(history[:10]))
        except Exception:
            pass
        audit("login")
        self._logged_in = True
        self.destroy()

    def _show_error(self, msg: str):
        if hasattr(self, "_error_lbl"):
            self._error_lbl.config(text=msg)
        else:
            self._error_lbl = tk.Label(
                self, text=msg, bg="#1E2A3A", fg="#E53935",
                font=("Segoe UI", 9)
            )
            self._error_lbl.place(relx=0.5, rely=0.93, anchor="center")
        self.after(3000, lambda: self._error_lbl.config(text=""))

    def _start_drag(self, event):
        self._drag_start_x = event.x_root - self.winfo_x()
        self._drag_start_y = event.y_root - self.winfo_y()

    def _do_drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_start_x}+{event.y_root - self._drag_start_y}")


if __name__ == "__main__":
    login = LoginWindow()
    login.mainloop()
    if login._logged_in:
        app = App()
        app.mainloop()
