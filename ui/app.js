// Aguarda pywebview estar pronto antes de qualquer chamada à API Python
async function pyReady() {
  return new Promise(resolve => {
    if (window.pywebview) return resolve();
    window.addEventListener("pywebviewready", resolve, { once: true });
  });
}

async function init() {
  await pyReady();

  // Teste de conexão
  try {
    const res = await window.pywebview.api.ping();
    console.log("API:", res.msg);
  } catch (e) {
    console.warn("Rodando sem pywebview (modo browser):", e.message);
  }
}

document.addEventListener("DOMContentLoaded", init);
