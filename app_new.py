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

def _storage_move(old_path: str, new_path: str):
    """Renomeia arquivo: copia local + R2 para novo caminho e apaga o antigo."""
    old_local = _local_path(old_path)
    new_local = _local_path(new_path)
    if os.path.exists(old_local):
        os.makedirs(os.path.dirname(new_local), exist_ok=True)
        try: shutil.copy2(old_local, new_local)
        except Exception: pass
        try: os.remove(old_local)
        except Exception: pass
    try:
        _r2().copy_object(
            Bucket=CF_BUCKET,
            CopySource={"Bucket": CF_BUCKET, "Key": old_path},
            Key=new_path,
        )
        _r2().delete_object(Bucket=CF_BUCKET, Key=old_path)
    except Exception as e:
        print(f"[R2] move falhou (offline?): {e}")

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
    def _get_trashed_paths(self) -> set:
        """Retorna conjunto de storage_paths que estão na lixeira."""
        try:
            items = self.get_trash()
            return {i["storage_path"] for i in items if "storage_path" in i}
        except Exception:
            return set()

    def get_root_folders(self) -> list:
        if not TENANT_ID: return []
        res = (sb.table("folders")
                 .select("id, name, storage_path, parent_path")
                 .eq("tenant_id", TENANT_ID)
                 .eq("parent_path", "")
                 .order("name")
                 .execute())
        trashed = self._get_trashed_paths()
        return [f for f in (res.data or []) if f["storage_path"] not in trashed]

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
        trashed = self._get_trashed_paths()
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

        result = [{"type": "folder", **f} for f in folders if f["storage_path"] not in trashed]
        result += [{
            "type":         "file",
            "id":           f["id"],
            "name":         f["name"],
            "storage_path": f["storage_path"],
            "size":         _fmt_size(self._real_size(f["id"], f["storage_path"], f.get("size"))),
            "updated_at":   f.get("created_at") or "",
            "locked_by":    f.get("locked_by"),
            "locked_name":  f.get("locked_name"),
        } for f in files if f["storage_path"] not in trashed]
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
        files   = (sb.table("files").select("id, storage_path, size, created_at")
                     .eq("tenant_id", TENANT_ID).eq("parent_path", storage_path)
                     .execute()).data or []
        folders = (sb.table("folders").select("id")
                     .eq("tenant_id", TENANT_ID).eq("parent_path", storage_path)
                     .execute()).data or []
        total = sum(self._real_size(f["id"], f["storage_path"], f.get("size")) for f in files)

        # data da última alteração: arquivo mais recente na pasta
        last_change = None
        if files:
            dates = [f.get("created_at") for f in files if f.get("created_at")]
            if dates:
                last_change = max(dates)

        return {
            "file_count":   len(files),
            "folder_count": len(folders),
            "total_size":   _fmt_size(total),
            "last_change":  last_change,
        }

    def get_tenant_stats(self) -> dict:
        """Resumo global do tenant: total de arquivos, pastas, tamanho e última alteração."""
        if not TENANT_ID: return {}
        trashed = self._get_trashed_paths()
        files   = (sb.table("files").select("id, storage_path, size, created_at")
                     .eq("tenant_id", TENANT_ID).execute()).data or []
        folders = (sb.table("folders").select("id")
                     .eq("tenant_id", TENANT_ID).execute()).data or []
        files   = [f for f in files   if f["storage_path"] not in trashed]
        total   = sum(f.get("size") or 0 for f in files)
        last_change = None
        if files:
            dates = [f.get("created_at") for f in files if f.get("created_at")]
            if dates:
                last_change = max(dates)
        return {
            "file_count":   len(files),
            "folder_count": len(folders),
            "total_size":   _fmt_size(total),
            "last_change":  last_change,
        }

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
            # atualiza storage_path de todos os filhos (pastas e arquivos)
            old_prefix = old["storage_path"].rstrip("/") + "/"
            new_prefix = new_storage.rstrip("/") + "/"
            child_folders = (sb.table("folders").select("id, storage_path, parent_path")
                               .eq("tenant_id", TENANT_ID).execute()).data or []
            child_files   = (sb.table("files").select("id, storage_path, parent_path")
                               .eq("tenant_id", TENANT_ID).execute()).data or []
            for cf in child_folders:
                if cf["storage_path"].startswith(old_prefix):
                    new_sp = new_prefix + cf["storage_path"][len(old_prefix):]
                    new_pp = new_prefix + cf["parent_path"][len(old_prefix):] if cf["parent_path"].startswith(old_prefix) else new_storage
                    sb.table("folders").update({"storage_path": new_sp, "parent_path": new_pp}).eq("id", cf["id"]).execute()
            for cf in child_files:
                if cf["storage_path"].startswith(old_prefix):
                    new_sp = new_prefix + cf["storage_path"][len(old_prefix):]
                    new_pp = new_prefix + cf["parent_path"][len(old_prefix):] if cf["parent_path"].startswith(old_prefix) else new_storage
                    _storage_move(cf["storage_path"], new_sp)
                    sb.table("files").update({"storage_path": new_sp, "parent_path": new_pp}).eq("id", cf["id"]).execute()
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
        """Verifica trava, baixa do R2, abre com programa padrão e monitora para re-upload."""
        import threading, time
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

            # busca o id do arquivo para trava
            res = (sb.table("files").select("id").eq("tenant_id", TENANT_ID)
                     .eq("storage_path", storage_path).execute())
            file_id = res.data[0]["id"] if res.data else None
            if file_id:
                self.lock_file(file_id)

            os.startfile(local)
            _audit("abriu", "arquivo", filename)

            # thread de monitoramento: quando o editor fechar, faz upload e libera trava
            def _watch(fid, local_path, sp):
                directory = os.path.dirname(local_path)
                fname     = os.path.basename(local_path)
                lo_lock   = os.path.join(directory, f".~lock.{fname}#")
                word_lock = os.path.join(directory, f"~${fname[2:]}")

                def _is_open():
                    if os.path.exists(lo_lock):   return True
                    if os.path.exists(word_lock):  return True
                    try:
                        with open(local_path, "r+b"): pass
                        return False
                    except (IOError, PermissionError):
                        return True

                time.sleep(5)  # aguarda editor abrir e criar lock file
                while True:
                    time.sleep(3)
                    if not _is_open():
                        time.sleep(5)
                        if not _is_open():
                            # arquivo fechado — sincroniza com R2
                            try:
                                _r2().upload_file(local_path, CF_BUCKET, sp)
                                # atualiza tamanho no banco
                                sz = os.path.getsize(local_path)
                                if fid:
                                    sb.table("files").update({"size": sz}).eq("id", fid).execute()
                                print(f"[R2] Sincronizado: {sp}")
                            except Exception as e:
                                print(f"[R2] Erro ao sincronizar: {e}")
                            if fid:
                                self.unlock_file(fid)
                            break

            threading.Thread(target=_watch, args=(file_id, local, storage_path), daemon=True).start()
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
            _storage_move(old["storage_path"], new_storage)
            sb.table("files").update({"name": new_name, "storage_path": new_storage}).eq("id", file_id).execute()
            _audit("renomeou", "arquivo", f"{old['name']} → {new_name}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_item(self, item_type: str, item_id: str, storage_path: str) -> dict:
        """Move o item para a lixeira (soft delete). A exclusão real ocorre ao esvaziar a lixeira."""
        try:
            perms = self.get_permissions()
            if not perms.get("can_delete") and not perms.get("is_admin"):
                return {"ok": False, "error": "Sem permissão para excluir."}

            if item_type == "folder":
                fn_res = sb.table("folders").select("name").eq("id", item_id).execute()
                folder_name = fn_res.data[0]["name"] if fn_res.data else storage_path
                # Coleta todos os filhos para registrar na lixeira junto com a pasta raiz
                all_files = (sb.table("files").select("id, storage_path, name")
                               .eq("tenant_id", TENANT_ID).execute()).data or []
                prefix = storage_path.rstrip("/") + "/"
                children = [{"type": "file", "id": f["id"], "storage_path": f["storage_path"], "name": f["name"]}
                            for f in all_files if f["storage_path"].startswith(prefix)]
                self._add_to_trash({
                    "type": "folder", "id": item_id, "storage_path": storage_path,
                    "name": folder_name, "children": children,
                })
                _audit("excluiu", "pasta", folder_name)
            else:
                res = sb.table("files").select("name").eq("id", item_id).execute()
                fname = res.data[0]["name"] if res.data else storage_path
                self._add_to_trash({"type": "file", "id": item_id, "storage_path": storage_path, "name": fname})
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

    def get_notifications(self, limit: int = 15) -> list:
        """Últimas ações no tenant para o sino de notificações."""
        try:
            res = (sb.table("audit_log")
                     .select("action, target_type, target_name, user_name, created_at")
                     .eq("tenant_id", TENANT_ID)
                     .order("created_at", desc=True)
                     .limit(limit)
                     .execute())
            return res.data or []
        except Exception:
            return []

    def logout(self) -> dict:
        """Limpa sessão do usuário atual."""
        global CURRENT_USER
        try:
            self.unlock_all()
        except Exception:
            pass
        CURRENT_USER = {}
        return {"ok": True}

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

    # ── Recentes ─────────────────────────────────────────────────────────────
    def get_recent_files(self) -> list:
        """Últimos 30 arquivos abertos ou criados pelo usuário atual."""
        try:
            res = (sb.table("audit_log")
                     .select("target_name, created_at, action")
                     .eq("tenant_id", TENANT_ID)
                     .eq("user_id", CURRENT_USER.get("id"))
                     .in_("action", ["abriu", "criou", "fez upload"])
                     .order("created_at", desc=True)
                     .limit(50)
                     .execute())
            seen = set()
            result = []
            for row in (res.data or []):
                name = row.get("target_name")
                if name and name not in seen:
                    seen.add(name)
                    f = (sb.table("files").select("id, name, storage_path, size, created_at")
                           .eq("tenant_id", TENANT_ID).eq("name", name).limit(1).execute()).data
                    if f:
                        result.append({
                            "type": "file",
                            "id": f[0]["id"],
                            "name": f[0]["name"],
                            "storage_path": f[0]["storage_path"],
                            "size": _fmt_size(f[0].get("size")),
                            "updated_at": f[0].get("created_at") or "",
                            "last_action": row["action"],
                            "last_action_at": row["created_at"],
                        })
                    if len(result) >= 30:
                        break
            return result
        except Exception as e:
            print(f"[recentes] {e}")
            return []

    # ── Favoritos ────────────────────────────────────────────────────────────
    def _favorites_file(self) -> str:
        path = os.path.join(os.path.expanduser("~"), "Zynor Docs", TENANT_ID)
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, f".favorites_{CURRENT_USER.get('id','')}.json")

    def get_favorites(self) -> list:
        try:
            with open(self._favorites_file(), "r", encoding="utf-8") as f:
                paths = json.load(f)
            result = []
            for sp in paths:
                row = (sb.table("folders").select("id, name, storage_path, parent_path")
                         .eq("tenant_id", TENANT_ID).eq("storage_path", sp).limit(1).execute()).data
                if row:
                    result.append({"type": "folder", **row[0]})
                    continue
                row = (sb.table("files").select("id, name, storage_path, size, created_at")
                         .eq("tenant_id", TENANT_ID).eq("storage_path", sp).limit(1).execute()).data
                if row:
                    result.append({
                        "type": "file", "id": row[0]["id"], "name": row[0]["name"],
                        "storage_path": row[0]["storage_path"],
                        "size": _fmt_size(row[0].get("size")),
                        "updated_at": row[0].get("created_at") or "",
                    })
            return result
        except Exception:
            return []

    def toggle_favorite(self, storage_path: str) -> dict:
        try:
            fpath = self._favorites_file()
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    favs = json.load(f)
            except Exception:
                favs = []
            if storage_path in favs:
                favs.remove(storage_path)
                is_fav = False
            else:
                favs.insert(0, storage_path)
                is_fav = True
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(favs, f)
            return {"ok": True, "is_favorite": is_fav}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def is_favorite(self, storage_path: str) -> bool:
        try:
            with open(self._favorites_file(), "r", encoding="utf-8") as f:
                return storage_path in json.load(f)
        except Exception:
            return False

    # ── Compartilhados ───────────────────────────────────────────────────────
    def get_shared_files(self) -> list:
        """Arquivos cujo link de compartilhamento foi gerado por qualquer usuário do tenant."""
        try:
            res = (sb.table("audit_log")
                     .select("target_name, user_name, created_at")
                     .eq("tenant_id", TENANT_ID)
                     .eq("action", "compartilhou")
                     .order("created_at", desc=True)
                     .limit(50)
                     .execute())
            seen = set()
            result = []
            for row in (res.data or []):
                name = row.get("target_name")
                if name and name not in seen:
                    seen.add(name)
                    f = (sb.table("files").select("id, name, storage_path, size, created_at")
                           .eq("tenant_id", TENANT_ID).eq("name", name).limit(1).execute()).data
                    if f:
                        result.append({
                            "type": "file",
                            "id": f[0]["id"],
                            "name": f[0]["name"],
                            "storage_path": f[0]["storage_path"],
                            "size": _fmt_size(f[0].get("size")),
                            "updated_at": f[0].get("created_at") or "",
                            "shared_by": row["user_name"],
                            "shared_at": row["created_at"],
                        })
            return result
        except Exception as e:
            print(f"[compartilhados] {e}")
            return []

    # ── Lixeira ──────────────────────────────────────────────────────────────
    def _trash_file(self) -> str:
        path = os.path.join(os.path.expanduser("~"), "Zynor Docs", TENANT_ID)
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, ".trash.json")

    def get_trash(self) -> list:
        try:
            with open(self._trash_file(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _add_to_trash(self, item: dict):
        try:
            from datetime import datetime
            items = self.get_trash()
            item["deleted_at"] = datetime.now().isoformat()
            items.insert(0, item)
            with open(self._trash_file(), "w", encoding="utf-8") as f:
                json.dump(items[:200], f, ensure_ascii=False)
        except Exception:
            pass

    def restore_from_trash(self, storage_path: str) -> dict:
        try:
            items = self.get_trash()
            items = [i for i in items if i.get("storage_path") != storage_path]
            with open(self._trash_file(), "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def empty_trash(self) -> dict:
        """Exclui permanentemente todos os itens da lixeira do banco e do R2."""
        try:
            items = self.get_trash()
            for item in items:
                try:
                    if item["type"] == "file":
                        _storage_delete(item["storage_path"])
                        sb.table("files").delete().eq("id", item["id"]).execute()
                    elif item["type"] == "folder":
                        # exclui filhos primeiro
                        for child in item.get("children", []):
                            try:
                                _storage_delete(child["storage_path"])
                                sb.table("files").delete().eq("id", child["id"]).execute()
                            except Exception:
                                pass
                        # exclui subpastas e a pasta raiz
                        all_folders = (sb.table("folders").select("id, storage_path")
                                         .eq("tenant_id", TENANT_ID).execute()).data or []
                        prefix = item["storage_path"].rstrip("/") + "/"
                        for f in all_folders:
                            if f["storage_path"].startswith(prefix):
                                sb.table("folders").delete().eq("id", f["id"]).execute()
                        sb.table("folders").delete().eq("id", item["id"]).execute()
                except Exception:
                    pass
            with open(self._trash_file(), "w", encoding="utf-8") as f:
                json.dump([], f)
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
            _audit("compartilhou", "arquivo", filename)
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
