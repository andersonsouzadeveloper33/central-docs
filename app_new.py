"""
Nova interface Zynor Docs — pywebview
Processo separado; recebe tenant/user via env vars do app.py (CTk).
Todas as regras de negócio espelham o app.py.
"""
import os, sys, json, uuid, hashlib, shutil, tempfile
import webview
from supabase import create_client, Client

# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL = "https://ipstefusensfzjltdbwn.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imlwc3Rl"
    "ZnVzZW5zZnpqbHRkYnduIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEwMjU4MDEsImV4cCI6MjA5Nj"
    "YwMTgwMX0.QSghFta1Qa6_rkPlHY0XvohAm0q6S0FRK6Aao1PZFeY"
)
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Sessão ────────────────────────────────────────────────────────────────────
SESSION_ID   = str(uuid.uuid4())
TENANT_ID    = os.environ.get("ZYNOR_TENANT_ID", "")
CURRENT_USER: dict = json.loads(os.environ.get("ZYNOR_USER", "{}"))

# Standalone: carrega tenant do config.json
if not TENANT_ID:
    _appdata  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZynorDocs")
    _cfg_path = os.path.join(_appdata, "config.json")
    if os.path.exists(_cfg_path):
        with open(_cfg_path, encoding="utf-8") as _f:
            TENANT_ID = json.load(_f).get("tenant_id", "")

# ── Cloudflare R2 ─────────────────────────────────────────────────────────────
CF_ACCOUNT_ID = "0527279a58ca34c6f7759899a64d07e3"
CF_ACCESS_KEY = "7a3ac7882e63a79d2192d547e7b03f1d"
CF_SECRET_KEY = "17f05bbe4c37afe9dfbb368fce4cf74af7e219ea65c5183607b6f241015e6656"
CF_BUCKET     = "centraldocs"
CF_ENDPOINT   = f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com"

import boto3
from botocore.config import Config as _BotoConfig

def _r2():
    return boto3.client(
        "s3",
        endpoint_url=CF_ENDPOINT,
        aws_access_key_id=CF_ACCESS_KEY,
        aws_secret_access_key=CF_SECRET_KEY,
        config=_BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )

# ── Storage local (espelho) ────────────────────────────────────────────────────
def _local_storage() -> str:
    path = os.path.join(os.path.expanduser("~"), "Zynor Docs", TENANT_ID)
    os.makedirs(path, exist_ok=True)
    return path

def _local_path(storage_path: str) -> str:
    return os.path.join(_local_storage(), storage_path.lstrip("/").replace("/", os.sep))

def _storage_upload(storage_path: str, local_src: str):
    """Copia para pasta local primeiro; tenta R2 (falha silenciosa se offline)."""
    dest = _local_path(storage_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(local_src, dest)
    try:
        _r2().upload_file(local_src, CF_BUCKET, storage_path)
    except Exception as e:
        print(f"[R2] upload falhou (offline?): {e}")

def _storage_download(storage_path: str) -> str:
    """Baixa do R2 se necessário; fallback na cópia local."""
    dest = _local_path(storage_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        meta    = _r2().head_object(Bucket=CF_BUCKET, Key=storage_path)
        r2_mtime = meta["LastModified"].timestamp()
        if not os.path.exists(dest) or r2_mtime > os.path.getmtime(dest) + 5:
            try:
                _r2().download_file(CF_BUCKET, storage_path, dest)
            except PermissionError:
                pass
    except Exception as e:
        print(f"[R2] download falhou (offline?): {e}")
        if not os.path.exists(dest):
            return ""
    return dest

def _storage_delete(storage_path: str):
    """Remove arquivo local e do R2."""
    local = _local_path(storage_path)
    if os.path.exists(local):
        try: os.remove(local)
        except: pass
    try:
        _r2().delete_object(Bucket=CF_BUCKET, Key=storage_path)
    except Exception as e:
        print(f"[R2] delete falhou: {e}")

# ── Utilitários ───────────────────────────────────────────────────────────────
def _ui_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "ui")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

def _fmt_size(b) -> str:
    if b is None: return "—"
    b = int(b)
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024: return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def _make_storage_path(parent_path: str, name: str, is_folder: bool = False) -> str:
    """Mesma lógica do app.py: prefixo tenant_id na raiz, slug lowercase."""
    slug = name.lower().replace(" ", "-")
    base = parent_path.strip("/")
    if base:
        return f"{base}/{slug}/" if is_folder else f"{base}/{slug}"
    return f"{TENANT_ID}/{slug}/" if is_folder else f"{TENANT_ID}/{slug}"

# ── Audit log ─────────────────────────────────────────────────────────────────
def _audit(action: str, target_type: str = None, target_name: str = None):
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
        print(f"[Audit] {e}")

# ── API exposta ao JavaScript ──────────────────────────────────────────────────
class Api:

    # ── Licença ──────────────────────────────────────────────────────────────
    def _license_validate(self) -> dict:
        try:
            res = (sb.table("licenses")
                     .select("active, expires_at")
                     .eq("tenant_id", TENANT_ID)
                     .eq("active", True)
                     .execute())
            if not res.data:
                return {"ok": False, "error": "Sua licença foi revogada ou não encontrada.\nContate o suporte."}
            lic = res.data[0]
            if lic.get("expires_at"):
                from datetime import datetime, timezone
                exp = datetime.fromisoformat(lic["expires_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp:
                    return {"ok": False, "error": "Sua licença expirou.\nContate o suporte para renovar."}
            return {"ok": True}
        except Exception:
            return {"ok": True}  # fail-open em erro de rede

    def license_activate(self, code: str) -> dict:
        """Valida código de ativação e salva tenant_id."""
        try:
            res = sb.table("licenses").select("tenant_id, active").eq("code", code).execute()
            if not res.data:
                return {"ok": False, "error": "Código de ativação inválido."}
            lic = res.data[0]
            if not lic.get("active"):
                return {"ok": False, "error": "Este código já foi utilizado ou foi revogado."}
            global TENANT_ID
            TENANT_ID = lic["tenant_id"]
            # salva config.json
            _appdata = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZynorDocs")
            os.makedirs(_appdata, exist_ok=True)
            with open(os.path.join(_appdata, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"tenant_id": TENANT_ID}, f, indent=2)
            return {"ok": True, "tenant_id": TENANT_ID}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Login / Sessão ────────────────────────────────────────────────────────
    def login(self, email: str, password: str) -> dict:
        global CURRENT_USER
        try:
            lic = self._license_validate()
            if not lic["ok"]:
                return {"ok": False, "error": lic["error"]}

            pw_hash = _hash_password(password)
            res = (sb.table("users")
                     .select("*")
                     .eq("tenant_id", TENANT_ID)
                     .eq("email", email)
                     .eq("password", pw_hash)
                     .execute())
            if not res.data:
                return {"ok": False, "error": "E-mail ou senha incorretos."}
            user = res.data[0]

            CURRENT_USER = {
                "id":                   user["id"],
                "name":                 user["name"],
                "email":                user["email"],
                "role":                 user.get("role", "user"),
                "must_change_password": user.get("must_change_password", False),
            }
            self._save_email_history(email)
            # limpa locks de sessões anteriores deste usuário (app fechado sem unlock)
            try:
                sb.table("files").update({
                    "locked_by": None, "locked_name": None, "locked_at": None,
                }).eq("tenant_id", TENANT_ID).eq("locked_name", user["name"]).execute()
            except Exception:
                pass
            _audit("login")
            return {"ok": True, "must_change_password": user.get("must_change_password", False)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_session(self) -> dict:
        # ao iniciar sessão herdada do pai, limpa locks de sessões mortas deste usuário
        if CURRENT_USER.get("name"):
            try:
                sb.table("files").update({
                    "locked_by": None, "locked_name": None, "locked_at": None,
                }).eq("tenant_id", TENANT_ID).eq("locked_name", CURRENT_USER["name"]).execute()
            except Exception:
                pass
        return {"tenant_id": TENANT_ID, "user": CURRENT_USER}

    def change_password(self, new_password: str) -> dict:
        try:
            pw_hash = _hash_password(new_password)
            sb.table("users").update({
                "password":             pw_hash,
                "must_change_password": False,
            }).eq("id", CURRENT_USER["id"]).execute()
            CURRENT_USER["must_change_password"] = False
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Histórico de e-mails ──────────────────────────────────────────────────
    def _history_file(self) -> str:
        path = os.path.join(os.path.expanduser("~"), "Zynor Docs", TENANT_ID)
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, ".last_user")

    def get_email_history(self) -> list:
        try:
            with open(self._history_file(), "r", encoding="utf-8") as f:
                return [e.strip() for e in f.read().splitlines() if e.strip()]
        except Exception:
            return []

    def _save_email_history(self, email: str):
        try:
            history = self.get_email_history()
            if email in history:
                history.remove(email)
            history.insert(0, email)
            with open(self._history_file(), "w", encoding="utf-8") as f:
                f.write("\n".join(history[:10]))
        except Exception:
            pass

    # ── Permissões ────────────────────────────────────────────────────────────
    def get_permissions(self) -> dict:
        """Retorna permissões do usuário logado (mesmo grupo/permissão do app.py)."""
        default = {"can_view": True, "can_create": False,
                   "can_edit": False, "can_delete": False, "is_admin": False}
        if not CURRENT_USER.get("id"):
            return default
        try:
            ug = (sb.table("user_groups")
                    .select("group_id, groups(*)")
                    .eq("user_id", CURRENT_USER["id"])
                    .execute())
            if ug.data:
                return ug.data[0]["groups"]
        except Exception:
            pass
        return default

    # ── Tenant info ───────────────────────────────────────────────────────────
    def get_tenant_info(self) -> dict:
        try:
            res = (sb.table("tenants")
                     .select("name, logo_path, slug")
                     .eq("id", TENANT_ID)
                     .execute())
            return res.data[0] if res.data else {}
        except Exception:
            return {}

    # ── Pastas ────────────────────────────────────────────────────────────────
    def get_root_folders(self) -> list:
        if not TENANT_ID: return []
        res = (sb.table("folders")
                 .select("id, name, storage_path, parent_path")
                 .eq("tenant_id", TENANT_ID)
                 .eq("parent_path", "")
                 .order("name")
                 .execute())
        return res.data or []

    def get_subfolders(self, parent_path: str) -> list:
        if not TENANT_ID: return []
        res = (sb.table("folders")
                 .select("id, name, storage_path, parent_path")
                 .eq("tenant_id", TENANT_ID)
                 .eq("parent_path", parent_path)
                 .order("name")
                 .execute())
        return res.data or []

    def get_children(self, storage_path: str) -> list:
        if not TENANT_ID: return []
        folders = (sb.table("folders")
                     .select("id, name, storage_path, parent_path")
                     .eq("tenant_id", TENANT_ID)
                     .eq("parent_path", storage_path)
                     .order("name")
                     .execute()).data or []
        files = (sb.table("files")
                   .select("id, name, storage_path, size, created_at, locked_by, locked_name")
                   .eq("tenant_id", TENANT_ID)
                   .eq("parent_path", storage_path)
                   .order("name")
                   .execute()).data or []

        result = [{"type": "folder", **f} for f in folders]
        result += [{
            "type":         "file",
            "id":           f["id"],
            "name":         f["name"],
            "storage_path": f["storage_path"],
            "size":         _fmt_size(self._real_size(f["id"], f["storage_path"], f.get("size"))),
            "updated_at":   f.get("created_at") or "",
            "locked_by":    f.get("locked_by"),
            "locked_name":  f.get("locked_name"),
        } for f in files]
        return result

    def _real_size(self, file_id: str, storage_path: str, current_size) -> int:
        """Busca tamanho real no R2 quando o banco tem 0/null; atualiza o banco."""
        if current_size and int(current_size) > 0:
            return int(current_size)
        try:
            meta = _r2().head_object(Bucket=CF_BUCKET, Key=storage_path)
            size = meta.get("ContentLength", 0)
            if size > 0:
                sb.table("files").update({"size": size}).eq("id", file_id).execute()
            return size
        except Exception:
            # fallback: tenta cópia local
            local = _local_path(storage_path)
            if os.path.exists(local):
                return os.path.getsize(local)
            return 0

    def get_folder_stats(self, storage_path: str) -> dict:
        if not TENANT_ID: return {}
        files   = (sb.table("files").select("id, storage_path, size")
                     .eq("tenant_id", TENANT_ID).eq("parent_path", storage_path)
                     .execute()).data or []
        folders = (sb.table("folders").select("id")
                     .eq("tenant_id", TENANT_ID).eq("parent_path", storage_path)
                     .execute()).data or []
        total = sum(self._real_size(f["id"], f["storage_path"], f.get("size")) for f in files)
        return {"file_count": len(files), "folder_count": len(folders), "total_size": _fmt_size(total)}

    def create_folder(self, name: str, parent_path: str) -> dict:
        try:
            perms = self.get_permissions()
            if not perms.get("can_create") and not perms.get("is_admin"):
                return {"ok": False, "error": "Sem permissão para criar pastas."}
            existing = (sb.table("folders").select("id")
                          .eq("tenant_id", TENANT_ID).eq("parent_path", parent_path).eq("name", name)
                          .execute()).data
            if existing:
                return {"ok": False, "error": f'Já existe uma pasta chamada "{name}" aqui.'}
            storage_path = _make_storage_path(parent_path, name, is_folder=True)
            sb.table("folders").insert({
                "tenant_id": TENANT_ID, "name": name,
                "storage_path": storage_path, "parent_path": parent_path,
            }).execute()
            _audit("criou", "pasta", name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def rename_folder(self, folder_id: str, new_name: str) -> dict:
        try:
            perms = self.get_permissions()
            if not perms.get("can_edit") and not perms.get("is_admin"):
                return {"ok": False, "error": "Sem permissão para renomear."}
            res = (sb.table("folders").select("storage_path, parent_path, name")
                     .eq("id", folder_id).execute())
            if not res.data:
                return {"ok": False, "error": "Pasta não encontrada."}
            old = res.data[0]
            new_storage = _make_storage_path(old["parent_path"], new_name, is_folder=True)
            sb.table("folders").update({"name": new_name, "storage_path": new_storage}).eq("id", folder_id).execute()
            _audit("renomeou", "pasta", f"{old['name']} → {new_name}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Arquivos ──────────────────────────────────────────────────────────────
    def create_file(self, name: str, parent_path: str) -> dict:
        try:
            perms = self.get_permissions()
            if not perms.get("can_create") and not perms.get("is_admin"):
                return {"ok": False, "error": "Sem permissão para criar arquivos."}
            existing = (sb.table("files").select("id")
                          .eq("tenant_id", TENANT_ID).eq("parent_path", parent_path).eq("name", name)
                          .execute()).data
            if existing:
                return {"ok": False, "error": f'Já existe um arquivo chamado "{name}" aqui.'}

            storage_path = _make_storage_path(parent_path, name)
            ext = os.path.splitext(name)[1].lower()
            tmp_path = os.path.join(tempfile.gettempdir(), f"zynor_new_{name}")
            try:
                if ext == ".docx":
                    from docx import Document
                    Document().save(tmp_path)
                elif ext == ".xlsx":
                    import openpyxl
                    openpyxl.Workbook().save(tmp_path)
                else:
                    with open(tmp_path, "w") as f:
                        f.write("")
                file_size = os.path.getsize(tmp_path)
                _storage_upload(storage_path, tmp_path)
            finally:
                try: os.remove(tmp_path)
                except: pass

            sb.table("files").insert({
                "tenant_id": TENANT_ID, "name": name,
                "storage_path": storage_path, "parent_path": parent_path,
                "size": file_size,
            }).execute()
            _audit("criou", "arquivo", name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def upload_file(self, filename: str, b64_data: str, parent_path: str) -> dict:
        try:
            perms = self.get_permissions()
            if not perms.get("can_create") and not perms.get("is_admin"):
                return {"ok": False, "error": "Sem permissão para fazer upload."}
            import base64
            data = base64.b64decode(b64_data)
            storage_path = _make_storage_path(parent_path, filename)
            existing = (sb.table("files").select("id")
                          .eq("tenant_id", TENANT_ID).eq("parent_path", parent_path).eq("name", filename)
                          .execute()).data
            if existing:
                return {"ok": False, "error": f'"{filename}" já existe nesta pasta.'}

            tmp_path = os.path.join(tempfile.gettempdir(), f"zynor_up_{filename}")
            try:
                with open(tmp_path, "wb") as f:
                    f.write(data)
                _storage_upload(storage_path, tmp_path)
            finally:
                try: os.remove(tmp_path)
                except: pass

            sb.table("files").insert({
                "tenant_id": TENANT_ID, "name": filename,
                "storage_path": storage_path, "parent_path": parent_path,
                "size": len(data),
            }).execute()
            _audit("fez upload", "arquivo", filename)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_file(self, storage_path: str, filename: str) -> dict:
        """Verifica trava, baixa do R2 (ou usa local), abre com programa padrão."""
        try:
            # verifica se está travado por outra sessão (ignora locks com mais de 2h — sessão morta)
            lock = self.get_file_lock_info_by_path(storage_path)
            if lock:
                from datetime import datetime, timezone, timedelta
                locked_at = lock.get("locked_at")
                stale = False
                if locked_at:
                    try:
                        dt = datetime.fromisoformat(locked_at.replace("Z", "+00:00"))
                        stale = datetime.now(timezone.utc) - dt > timedelta(hours=2)
                    except Exception:
                        stale = True
                if not stale:
                    return {"ok": False, "error": f'Arquivo em uso por {lock["locked_name"]}.'}

            local = _storage_download(storage_path)
            if not local:
                return {"ok": False, "error": "Arquivo não encontrado localmente nem no storage."}

            # trava o arquivo para esta sessão
            res = (sb.table("files").select("id").eq("tenant_id", TENANT_ID)
                     .eq("storage_path", storage_path).execute())
            if res.data:
                file_id = res.data[0]["id"]
                self.lock_file(file_id)

            os.startfile(local)
            _audit("abriu", "arquivo", filename)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def rename_file(self, file_id: str, new_name: str) -> dict:
        try:
            perms = self.get_permissions()
            if not perms.get("can_edit") and not perms.get("is_admin"):
                return {"ok": False, "error": "Sem permissão para renomear."}
            res = (sb.table("files").select("storage_path, parent_path, name")
                     .eq("id", file_id).execute())
            if not res.data:
                return {"ok": False, "error": "Arquivo não encontrado."}
            old = res.data[0]
            new_storage = _make_storage_path(old["parent_path"], new_name)
            sb.table("files").update({"name": new_name, "storage_path": new_storage}).eq("id", file_id).execute()
            _audit("renomeou", "arquivo", f"{old['name']} → {new_name}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_item(self, item_type: str, item_id: str, storage_path: str) -> dict:
        try:
            perms = self.get_permissions()
            if not perms.get("can_delete") and not perms.get("is_admin"):
                return {"ok": False, "error": "Sem permissão para excluir."}

            if item_type == "folder":
                all_folders = (sb.table("folders").select("id, storage_path")
                                 .eq("tenant_id", TENANT_ID).execute()).data or []
                all_files   = (sb.table("files").select("id, storage_path, name")
                                 .eq("tenant_id", TENANT_ID).execute()).data or []
                prefix = storage_path.rstrip("/") + "/"
                for f in all_files:
                    if f["storage_path"].startswith(prefix) or f["storage_path"] == storage_path:
                        _storage_delete(f["storage_path"])
                        sb.table("files").delete().eq("id", f["id"]).execute()
                for f in all_folders:
                    if f["storage_path"].startswith(prefix):
                        sb.table("folders").delete().eq("id", f["id"]).execute()
                sb.table("folders").delete().eq("id", item_id).execute()
                _audit("excluiu", "pasta", storage_path)
            else:
                res = sb.table("files").select("name").eq("id", item_id).execute()
                fname = res.data[0]["name"] if res.data else storage_path
                _storage_delete(storage_path)
                sb.table("files").delete().eq("id", item_id).execute()
                _audit("excluiu", "arquivo", fname)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Trava de arquivo ──────────────────────────────────────────────────────
    def lock_file(self, file_id: str) -> dict:
        try:
            res = sb.table("files").select("locked_by").eq("id", file_id).execute()
            if not res.data:
                return {"ok": False}
            row = res.data[0]
            if row["locked_by"] and row["locked_by"] != SESSION_ID:
                return {"ok": False, "error": "Arquivo travado por outra sessão."}
            sb.table("files").update({
                "locked_by":   SESSION_ID,
                "locked_name": CURRENT_USER.get("name", "Usuário"),
                "locked_at":   "now()",
            }).eq("id", file_id).execute()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def unlock_file(self, file_id: str) -> dict:
        try:
            sb.table("files").update({
                "locked_by": None, "locked_name": None, "locked_at": None,
            }).eq("id", file_id).eq("locked_by", SESSION_ID).execute()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def unlock_all(self) -> dict:
        """Libera todas as travas desta sessão (chamar ao fechar o app)."""
        try:
            sb.table("files").update({
                "locked_by": None, "locked_name": None, "locked_at": None,
            }).eq("locked_by", SESSION_ID).execute()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_file_lock_info_by_path(self, storage_path: str) -> dict | None:
        try:
            res = (sb.table("files")
                     .select("locked_by, locked_name, locked_at")
                     .eq("tenant_id", TENANT_ID)
                     .eq("storage_path", storage_path)
                     .execute())
            if res.data and res.data[0]["locked_by"]:
                row = res.data[0]
                if row["locked_by"] == SESSION_ID:
                    return None  # é desta sessão, não bloqueia
                return row
        except Exception:
            pass
        return None

    # ── Audit log ─────────────────────────────────────────────────────────────
    def get_audit_log(self, limit: int = 200) -> list:
        try:
            res = (sb.table("audit_log")
                     .select("*")
                     .eq("tenant_id", TENANT_ID)
                     .order("created_at", desc=True)
                     .limit(limit)
                     .execute())
            return res.data or []
        except Exception:
            return []

    def get_item_activity(self, target_name: str) -> list:
        """Retorna histórico de atividades de um arquivo ou pasta específico."""
        try:
            res = (sb.table("audit_log")
                     .select("action, user_name, created_at")
                     .eq("tenant_id", TENANT_ID)
                     .eq("target_name", target_name)
                     .order("created_at", desc=True)
                     .limit(50)
                     .execute())
            return res.data or []
        except Exception:
            return []

    # ── Usuários ──────────────────────────────────────────────────────────────
    def get_users(self) -> list:
        try:
            users = (sb.table("users")
                       .select("id, name, email, created_at")
                       .eq("tenant_id", TENANT_ID)
                       .order("name")
                       .execute()).data or []
            result = []
            for u in users:
                ug = (sb.table("user_groups")
                        .select("group_id, groups(name)")
                        .eq("user_id", u["id"])
                        .execute())
                group_name = ug.data[0]["groups"]["name"] if ug.data else "Sem grupo"
                group_id   = ug.data[0]["group_id"]       if ug.data else None
                result.append({**u, "group_name": group_name, "group_id": group_id})
            return result
        except Exception as e:
            return []

    def create_user(self, name: str, email: str, password: str, group_id: str) -> dict:
        try:
            res = sb.table("users").insert({
                "name": name, "email": email,
                "password": _hash_password(password),
                "tenant_id": TENANT_ID,
            }).execute()
            user = res.data[0]
            sb.table("user_groups").insert({"user_id": user["id"], "group_id": group_id}).execute()
            _audit("criou", "usuário", name)
            return {"ok": True, "user": user}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_user(self, user_id: str, name: str, email: str,
                    password: str, group_id: str) -> dict:
        try:
            data: dict = {}
            if name:     data["name"]  = name
            if email:    data["email"] = email
            if password: data["password"] = _hash_password(password)
            if data:
                sb.table("users").update(data).eq("id", user_id).execute()
            if group_id:
                sb.table("user_groups").delete().eq("user_id", user_id).execute()
                sb.table("user_groups").insert({"user_id": user_id, "group_id": group_id}).execute()
            _audit("editou", "usuário", name or user_id)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_user(self, user_id: str) -> dict:
        try:
            res = sb.table("users").select("name").eq("id", user_id).execute()
            uname = res.data[0]["name"] if res.data else user_id
            sb.table("users").delete().eq("id", user_id).execute()
            _audit("excluiu", "usuário", uname)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Grupos ────────────────────────────────────────────────────────────────
    def get_groups(self) -> list:
        try:
            res = (sb.table("groups")
                     .select("*")
                     .eq("tenant_id", TENANT_ID)
                     .order("name")
                     .execute())
            return res.data or []
        except Exception:
            return []

    def create_group(self, name: str, can_view: bool, can_create: bool,
                     can_edit: bool, can_delete: bool, is_admin: bool) -> dict:
        try:
            res = sb.table("groups").insert({
                "name": name, "tenant_id": TENANT_ID,
                "can_view": can_view, "can_create": can_create,
                "can_edit": can_edit, "can_delete": can_delete, "is_admin": is_admin,
            }).execute()
            _audit("criou", "grupo", name)
            return {"ok": True, "group": res.data[0]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_group(self, group_id: str, name: str, can_view: bool, can_create: bool,
                     can_edit: bool, can_delete: bool, is_admin: bool) -> dict:
        try:
            sb.table("groups").update({
                "name": name, "can_view": can_view, "can_create": can_create,
                "can_edit": can_edit, "can_delete": can_delete, "is_admin": is_admin,
            }).eq("id", group_id).eq("tenant_id", TENANT_ID).execute()
            _audit("editou", "grupo", name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_group(self, group_id: str) -> dict:
        try:
            res = sb.table("groups").select("name").eq("id", group_id).execute()
            gname = res.data[0]["name"] if res.data else group_id
            sb.table("groups").delete().eq("id", group_id).eq("tenant_id", TENANT_ID).execute()
            _audit("excluiu", "grupo", gname)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Compartilhar (link temporário pré-assinado do R2) ────────────────────
    def share_file(self, storage_path: str, filename: str, expires_hours: int = 24) -> dict:
        try:
            import mimetypes
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            url = _r2().generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": CF_BUCKET,
                    "Key":    storage_path,
                    "ResponseContentType":        mime,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=expires_hours * 3600,
            )
            return {"ok": True, "url": url, "expires_hours": expires_hours}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Ping ──────────────────────────────────────────────────────────────────
    def ping(self) -> dict:
        return {"ok": True}


# ── Abre a janela ─────────────────────────────────────────────────────────────
def open_window():
    api   = Api()
    index = os.path.join(_ui_dir(), "index.html").replace(os.sep, "/")
    window = webview.create_window(
        "Zynor Docs",
        url=f"file:///{index}",
        js_api=api,
        width=1280,
        height=800,
        min_size=(900, 600),
    )
    webview.start(lambda: window.maximize(), debug=False)

if __name__ == "__main__":
    open_window()
