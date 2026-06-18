"""
Nova interface Zynor Docs — pywebview
Processo separado; recebe tenant/user via env vars do app.py (CTk).
"""
import os, sys, json
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

# ── Sessão recebida do processo pai (ou carregada do config) ─────────────────
TENANT_ID    = os.environ.get("ZYNOR_TENANT_ID", "")
CURRENT_USER = json.loads(os.environ.get("ZYNOR_USER", "{}"))

# Se rodando standalone (sem env do pai), carrega tenant do config.json
if not TENANT_ID:
    import json as _json
    _appdata = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZynorDocs")
    _cfg_path = os.path.join(_appdata, "config.json")
    if os.path.exists(_cfg_path):
        with open(_cfg_path, encoding="utf-8") as _f:
            TENANT_ID = _json.load(_f).get("tenant_id", "")

# ── Cloudflare R2 ────────────────────────────────────────────────────────────
CF_ACCOUNT_ID = "0527279a58ca34c6f7759899a64d07e3"
CF_ACCESS_KEY = "7a3ac7882e63a79d2192d547e7b03f1d"
CF_SECRET_KEY = "17f05bbe4c37afe9dfbb368fce4cf74af7e219ea65c5183607b6f241015e6656"
CF_BUCKET     = "centraldocs"
CF_ENDPOINT   = f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com"

# ── Utilitários ──────────────────────────────────────────────────────────────
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

# ── API exposta ao JavaScript ────────────────────────────────────────────────
class Api:

    # ── login (mesma lógica do app.py) ──────────────────────────────────────
    def login(self, email: str, password: str):
        global TENANT_ID, CURRENT_USER
        try:
            # 1. valida licença antes de qualquer coisa
            lic = self._license_validate()
            if not lic["ok"]:
                return {"ok": False, "error": lic["error"]}

            # 2. valida credenciais
            import hashlib
            pw_hash = hashlib.sha256(password.encode()).hexdigest()
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
            return {
                "ok":                   True,
                "must_change_password": user.get("must_change_password", False),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── histórico de e-mails ─────────────────────────────────────────────────
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

    def _license_validate(self) -> dict:
        """Idêntico ao license_validate() do app.py."""
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

    # ── troca de senha ───────────────────────────────────────────────────────
    def change_password(self, new_password: str):
        try:
            import hashlib
            pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
            sb.table("users").update({
                "password":             pw_hash,
                "must_change_password": False,
            }).eq("id", CURRENT_USER["id"]).execute()
            CURRENT_USER["must_change_password"] = False
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── info da sessão ───────────────────────────────────────────────────────
    def get_session(self):
        return {"tenant_id": TENANT_ID, "user": CURRENT_USER}

    # ── pastas raiz (sidebar) ────────────────────────────────────────────────
    def get_root_folders(self):
        if not TENANT_ID:
            return []
        res = (sb.table("folders")
                 .select("id, name, storage_path, parent_path")
                 .eq("tenant_id", TENANT_ID)
                 .eq("parent_path", "")
                 .order("name")
                 .execute())
        return res.data or []

    # ── subpastas de um caminho (sidebar) ───────────────────────────────────
    def get_subfolders(self, parent_path: str):
        if not TENANT_ID:
            return []
        res = (sb.table("folders")
                 .select("id, name, storage_path, parent_path")
                 .eq("tenant_id", TENANT_ID)
                 .eq("parent_path", parent_path)
                 .order("name")
                 .execute())
        return res.data or []

    # ── conteúdo de um caminho (pastas + arquivos) ───────────────────────────
    def get_children(self, storage_path: str):
        if not TENANT_ID:
            return []
        folders = (sb.table("folders")
                     .select("id, name, storage_path, parent_path")
                     .eq("tenant_id", TENANT_ID)
                     .eq("parent_path", storage_path)
                     .order("name")
                     .execute()).data or []
        files   = (sb.table("files")
                     .select("id, name, storage_path, size, created_at")
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
            "size":         _fmt_size(f.get("size")),
            "updated_at":   f.get("created_at") or "",
        } for f in files]
        return result

    # ── stats de uma pasta ───────────────────────────────────────────────────
    def get_folder_stats(self, storage_path: str):
        if not TENANT_ID:
            return {}
        files = (sb.table("files")
                   .select("size")
                   .eq("tenant_id", TENANT_ID)
                   .eq("parent_path", storage_path)
                   .execute()).data or []
        folders = (sb.table("folders")
                     .select("id")
                     .eq("tenant_id", TENANT_ID)
                     .eq("parent_path", storage_path)
                     .execute()).data or []
        total_size = sum(int(f.get("size") or 0) for f in files)
        return {
            "file_count":   len(files),
            "folder_count": len(folders),
            "total_size":   _fmt_size(total_size),
        }

    # ── criar pasta ─────────────────────────────────────────────────────────
    def create_folder(self, name: str, parent_path: str):
        existing = (sb.table("folders")
                      .select("id")
                      .eq("tenant_id", TENANT_ID)
                      .eq("parent_path", parent_path)
                      .eq("name", name)
                      .execute()).data
        if existing:
            raise Exception(f'Já existe uma pasta chamada "{name}" aqui.')
        storage_path = f"{parent_path}/{name}" if parent_path else name
        sb.table("folders").insert({
            "tenant_id":    TENANT_ID,
            "name":         name,
            "storage_path": storage_path,
            "parent_path":  parent_path,
        }).execute()
        return {"ok": True}

    # ── criar arquivo (texto vazio) ──────────────────────────────────────────
    def create_file(self, name: str, parent_path: str):
        existing = (sb.table("files")
                      .select("id")
                      .eq("tenant_id", TENANT_ID)
                      .eq("parent_path", parent_path)
                      .eq("name", name)
                      .execute()).data
        if existing:
            raise Exception(f'Já existe um arquivo chamado "{name}" aqui.')
        storage_path = f"{parent_path}/{name}" if parent_path else name
        sb.table("files").insert({
            "tenant_id":    TENANT_ID,
            "name":         name,
            "storage_path": storage_path,
            "parent_path":  parent_path,
            "size":         0,
        }).execute()
        return {"ok": True}

    # ── upload de arquivo (base64 → Cloudflare R2 + registro no banco) ──────
    def upload_file(self, filename: str, b64_data: str, parent_path: str):
        import base64, os as _os
        data = base64.b64decode(b64_data)
        storage_path = f"{parent_path}/{filename}" if parent_path else filename

        # verifica duplicata
        existing = (sb.table("files")
                      .select("id")
                      .eq("tenant_id", TENANT_ID)
                      .eq("parent_path", parent_path)
                      .eq("name", filename)
                      .execute()).data
        if existing:
            raise Exception(f'"{filename}" já existe nesta pasta.')

        # envia ao R2
        import boto3
        from botocore.config import Config
        s3 = boto3.client(
            "s3",
            endpoint_url=CF_ENDPOINT,
            aws_access_key_id=CF_ACCESS_KEY,
            aws_secret_access_key=CF_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        s3.put_object(Bucket=CF_BUCKET, Key=storage_path, Body=data)

        # registra no banco
        sb.table("files").insert({
            "tenant_id":    TENANT_ID,
            "name":         filename,
            "storage_path": storage_path,
            "parent_path":  parent_path,
            "size":         len(data),
        }).execute()
        return {"ok": True}

    # ── abrir arquivo (baixa do R2 e abre com programa padrão) ─────────────
    def open_file(self, storage_path: str, filename: str):
        import boto3, tempfile
        from botocore.config import Config
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=CF_ENDPOINT,
                aws_access_key_id=CF_ACCESS_KEY,
                aws_secret_access_key=CF_SECRET_KEY,
                config=Config(signature_version="s3v4"),
                region_name="auto",
            )
            r2_key = storage_path
            ext    = os.path.splitext(filename)[1]
            tmp    = tempfile.NamedTemporaryFile(delete=False, suffix=ext,
                                                 prefix="zynor_", dir=tempfile.gettempdir())
            s3.download_fileobj(CF_BUCKET, r2_key, tmp)
            tmp.close()
            os.startfile(tmp.name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── excluir pasta ou arquivo ─────────────────────────────────────────────
    def delete_item(self, item_type: str, item_id: str, storage_path: str):
        try:
            if item_type == "folder":
                # remove subpastas e arquivos recursivamente
                all_folders = (sb.table("folders")
                                 .select("id, storage_path")
                                 .eq("tenant_id", TENANT_ID)
                                 .execute()).data or []
                all_files = (sb.table("files")
                               .select("id, storage_path")
                               .eq("tenant_id", TENANT_ID)
                               .execute()).data or []
                prefix = storage_path.rstrip("/") + "/"
                for f in all_files:
                    if f["storage_path"].startswith(prefix) or f["storage_path"] == storage_path:
                        sb.table("files").delete().eq("id", f["id"]).execute()
                for f in all_folders:
                    if f["storage_path"].startswith(prefix):
                        sb.table("folders").delete().eq("id", f["id"]).execute()
                sb.table("folders").delete().eq("id", item_id).execute()
            else:
                sb.table("files").delete().eq("id", item_id).execute()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ping(self):
        return {"ok": True}

# ── Abre a janela ────────────────────────────────────────────────────────────
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
