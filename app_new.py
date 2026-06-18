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

# ── Sessão recebida do processo pai ──────────────────────────────────────────
TENANT_ID   = os.environ.get("ZYNOR_TENANT_ID", "")
CURRENT_USER = json.loads(os.environ.get("ZYNOR_USER", "{}"))

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
        CF_ACCOUNT  = _os.environ.get("CF_ACCOUNT_ID", "")
        CF_KEY_ID   = _os.environ.get("CF_ACCESS_KEY_ID", "")
        CF_SECRET   = _os.environ.get("CF_SECRET_ACCESS_KEY", "")
        CF_BUCKET   = _os.environ.get("CF_BUCKET", "")

        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{CF_ACCOUNT}.r2.cloudflarestorage.com",
            aws_access_key_id=CF_KEY_ID,
            aws_secret_access_key=CF_SECRET,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        r2_key = f"{TENANT_ID}/{storage_path}"
        s3.put_object(Bucket=CF_BUCKET, Key=r2_key, Body=data)

        # registra no banco
        sb.table("files").insert({
            "tenant_id":    TENANT_ID,
            "name":         filename,
            "storage_path": storage_path,
            "parent_path":  parent_path,
            "size":         len(data),
        }).execute()
        return {"ok": True}

    def ping(self):
        return {"ok": True}

# ── Abre a janela ────────────────────────────────────────────────────────────
def open_window():
    api   = Api()
    index = os.path.join(_ui_dir(), "index.html").replace(os.sep, "/")
    webview.create_window(
        "Zynor Docs",
        url=f"file:///{index}",
        js_api=api,
        width=1280,
        height=800,
        min_size=(900, 600),
    )
    webview.start(debug=False)

if __name__ == "__main__":
    open_window()
