"""
Nova interface Zynor Docs — pywebview
Ponto de entrada separado; a UI legada (app.py) não é afetada.
"""
import os, sys, json, threading
import webview

# ── Resolve caminhos dentro ou fora do .exe ──────────────────────────────────
def _ui_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "ui")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

def _ui_file(name: str) -> str:
    return os.path.join(_ui_dir(), name)

# ── API exposta ao JavaScript ────────────────────────────────────────────────
class Api:
    """
    Métodos aqui viram window.pywebview.api.xxx() no JS.
    Retornam sempre dict/list serializáveis — pywebview converte para JS automaticamente.
    """

    def ping(self):
        return {"ok": True, "msg": "Python conectado!"}

    # À medida que formos avançando, adicionamos:
    # get_folders(), get_files(), create_folder(), upload_file(), etc.

# ── Abre a janela ────────────────────────────────────────────────────────────
def open_window(title="Zynor Docs", width=1280, height=800):
    api = Api()
    index = _ui_file("index.html")
    window = webview.create_window(
        title,
        url=f"file:///{index.replace(os.sep, '/')}",
        js_api=api,
        width=width,
        height=height,
        min_size=(900, 600),
        frameless=False,
    )
    webview.start(debug=False)

if __name__ == "__main__":
    open_window()
